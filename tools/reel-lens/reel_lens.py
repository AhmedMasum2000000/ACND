#!/usr/bin/env python3
"""reel-lens: a free, local replacement for paid short-form video analysers.

Two jobs:
  analyze  <video file or URL>   scene-by-scene breakdown: cuts, keyframes, on-screen text (OCR),
                                 spoken words (Whisper), tempo, loudness. Writes report.md + contact sheet.
  profile  <instagram handle>    latest N reels with views, the account's median, and each reel's
                                 outlier multiple (views / median). Writes a TSV that ig-viral's swipe.py reads.

Everything runs on your machine. Nothing is uploaded anywhere.
Instagram needs a logged-in session for both downloading and profile stats: pass YOUR OWN browser
cookies (--cookies-from-browser chrome, or --cookies cookies.txt). Keep volume human: the defaults
are small and requests are spaced out on purpose. Respect Instagram's terms and creators' rights:
study formats, do not re-upload other people's videos.
"""
import argparse, json, math, os, re, shutil, statistics, subprocess, sys, tempfile, time
from pathlib import Path

def run(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)

def need(binary):
    if not shutil.which(binary):
        sys.exit(f"missing dependency: {binary} (see README)")

# ---------------------------------------------------------------- download
def fetch(url, outdir, cookies=None, cookies_from_browser=None):
    """Download one video with yt-dlp. Returns the local path."""
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        sys.exit("pip install yt-dlp  (needed to download from a URL; or pass a local file)")
    cmd = [sys.executable, "-m", "yt_dlp", "-q", "--no-warnings", "-f", "mp4/best", "-o", str(Path(outdir) / "%(id)s.%(ext)s"), "--print", "after_move:filepath"]
    if cookies:
        cmd += ["--cookies", cookies]
    if cookies_from_browser:
        cmd += ["--cookies-from-browser", cookies_from_browser]
    cmd.append(url)
    try:
        out = run(cmd).stdout.strip().splitlines()
    except subprocess.CalledProcessError as e:
        msg = e.stderr.strip()
        if "login" in msg.lower() or "rate-limit" in msg.lower():
            sys.exit("Instagram asked for a login. Re-run with --cookies-from-browser chrome (logged in as you) "
                     "or download the reel yourself and pass the file path.\n" + msg)
        sys.exit(msg)
    return out[-1]

# ---------------------------------------------------------------- probes
def probe(path):
    j = json.loads(run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path]).stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), {})
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    num, den = (v.get("r_frame_rate", "30/1").split("/") + ["1"])[:2]
    return {"duration": float(j["format"]["duration"]), "width": v.get("width"), "height": v.get("height"),
            "fps": round(float(num) / float(den or 1), 2), "has_audio": a is not None}

def scene_cuts(path, threshold=0.27):
    """Times (s) where the picture changes hard."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-vf", f"select='gt(scene,{threshold})',showinfo", "-f", "null", "-"],
                       capture_output=True, text=True)
    return [round(float(t), 2) for t in re.findall(r"pts_time:([0-9.]+)", r.stderr)]

def grab(path, t, out, width=540):
    run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", f"scale={width}:-2", out])
    return out

def ocr(img):
    try:
        import pytesseract
        from PIL import Image, ImageOps
    except ImportError:
        return ""
    im = Image.open(img).convert("L")
    im = im.resize((im.width * 2, im.height * 2))
    texts = []
    for variant in (im, ImageOps.invert(im)):  # catch light-on-dark and dark-on-light
        t = pytesseract.image_to_string(variant, config="--psm 11")
        texts += [w.strip() for w in t.splitlines() if len(w.strip()) > 2 and sum(c.isalpha() for c in w) >= 2]
    seen, out = set(), []
    for w in texts:
        k = w.lower()
        if k not in seen:
            seen.add(k)
            out.append(w)
    return " | ".join(out)

def transcribe(path):
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    import numpy as np
    # decode with ffmpeg ourselves (avoids PyAV version mismatches inside faster-whisper)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-"], capture_output=True).stdout
    audio = np.frombuffer(raw, np.float32)
    if audio.size < 16000:
        return []
    try:
        model = WhisperModel("base", device="cpu", compute_type="int8")
        segs, _ = model.transcribe(audio, vad_filter=True, word_timestamps=False)
        return [(round(s.start, 2), round(s.end, 2), s.text.strip()) for s in segs]
    except Exception as e:  # speech is optional; never fail the whole report
        print(f"(speech skipped: {e})", file=sys.stderr)
        return []

def audio_stats(path):
    """Tempo guess from low-end onsets + loudness."""
    try:
        import numpy as np
    except ImportError:
        return {}
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-ac", "1", "-ar", "8000", "-af", "lowpass=f=200", "-f", "f32le", "-"],
                         capture_output=True).stdout
    a = np.frombuffer(raw, np.float32)
    if len(a) < 16000:
        return {}
    h = 80  # 10 ms
    env = np.array([np.abs(a[i:i + h]).mean() for i in range(0, len(a) - h, h)])
    onset = np.maximum(np.diff(env), 0)
    onset -= onset.mean()
    ac = np.correlate(onset, onset, "full")[len(onset) - 1:]
    lags = np.arange(len(ac))
    bpm = 6000 / np.maximum(lags, 1)
    m = (bpm >= 70) & (bpm <= 200)
    best = 6000 / lags[m][int(np.argmax(ac[m]))]
    lufs = None
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", path, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True)
    mm = re.findall(r"I:\s+(-?[0-9.]+) LUFS", r.stderr)
    if mm:
        lufs = float(mm[-1])
    return {"tempo_guess_bpm": round(float(best), 1), "integrated_lufs": lufs}

def contact_sheet(frames, out, cols=4):
    from PIL import Image, ImageDraw
    ims = [Image.open(f) for f, _ in frames]
    if not ims:
        return None
    w, h = ims[0].size
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * w, rows * (h + 34)), "black")
    d = ImageDraw.Draw(sheet)
    for i, (im, (_, t)) in enumerate(zip(ims, frames)):
        x, y = (i % cols) * w, (i // cols) * (h + 34)
        sheet.paste(im.resize((w, h)), (x, y + 34))
        d.text((x + 8, y + 8), f"{t:6.2f}s", fill=(242, 255, 0))
    sheet.save(out)
    return out

# ---------------------------------------------------------------- analyze
def analyze(src, outroot, cookies=None, cookies_from_browser=None, no_speech=False, max_scenes=24):
    need("ffmpeg"); need("ffprobe")
    outroot = Path(outroot)
    outroot.mkdir(parents=True, exist_ok=True)
    path = src if os.path.exists(src) else fetch(src, outroot, cookies, cookies_from_browser)
    name = Path(path).stem
    out = outroot / name
    (out / "frames").mkdir(parents=True, exist_ok=True)
    info = probe(path)
    cuts = scene_cuts(path)
    bounds = [0.0] + [c for c in cuts if 0.15 < c < info["duration"] - 0.15] + [info["duration"]]
    # keep at most max_scenes, merging the shortest
    while len(bounds) - 1 > max_scenes:
        gaps = [bounds[i + 1] - bounds[i] for i in range(len(bounds) - 1)]
        i = gaps.index(min(gaps))
        del bounds[i + 1 if i + 1 < len(bounds) - 1 else i]
    scenes, frames = [], []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        t = a + min(0.5, (b - a) / 2) if b - a > 0.3 else (a + b) / 2
        f = grab(path, t, str(out / "frames" / f"scene_{i + 1:02d}.png"))
        frames.append((f, t))
        scenes.append({"scene": i + 1, "start": round(a, 2), "end": round(b, 2), "frame": os.path.relpath(f, out), "on_screen_text": ocr(f)})
    speech = [] if (no_speech or not info["has_audio"]) else transcribe(path)
    audio = audio_stats(path) if info["has_audio"] else {}
    sheet = contact_sheet(frames, str(out / "contact_sheet.png"))
    first = scenes[0]["on_screen_text"] if scenes else ""
    cut_rate = round((len(bounds) - 1) / info["duration"], 2) if info["duration"] else 0
    report = {"source": src, "file": path, **info, "cuts": len(bounds) - 2, "cuts_per_second": cut_rate,
              "hook_text_0_3s": first, "scenes": scenes, "speech": speech, "audio": audio}
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    md = [f"# reel-lens report: {name}", "", f"- source: {src}", f"- length: {info['duration']:.1f}s · {info['width']}x{info['height']} · {info['fps']} fps",
          f"- cuts: {len(bounds) - 2} ({cut_rate}/s) · audio: {'yes' if info['has_audio'] else 'no'}",
          f"- tempo guess: {audio.get('tempo_guess_bpm', '-')} BPM · loudness: {audio.get('integrated_lufs', '-')} LUFS",
          f"- hook text (first scene): {first or '-'}", "", "## Scenes", "", "| # | time | on-screen text |", "|---|---|---|"]
    for s in scenes:
        md.append(f"| {s['scene']} | {s['start']:.2f}–{s['end']:.2f}s | {s['on_screen_text'].replace('|', '/') or '-'} |")
    if speech:
        md += ["", "## Spoken", ""] + [f"- {a:.1f}–{b:.1f}s: {t}" for a, b, t in speech]
    md += ["", f"Contact sheet: contact_sheet.png · frames in frames/"]
    (out / "report.md").write_text("\n".join(md))
    print(out / "report.md")
    return report

# ---------------------------------------------------------------- profile
def profile(handle, count, outroot, session_user=None, sessionfile=None, pause=4.0):
    try:
        import instaloader
    except ImportError:
        sys.exit("pip install instaloader")
    L = instaloader.Instaloader(download_pictures=False, download_videos=False, save_metadata=False, quiet=True)
    if session_user:
        try:
            L.load_session_from_file(session_user, sessionfile)
        except FileNotFoundError:
            sys.exit(f"No saved session for {session_user}. Run once:  instaloader --login {session_user}  (asks for your password in YOUR terminal)")
    prof = instaloader.Profile.from_username(L.context, handle.lstrip("@"))
    rows = []
    for post in prof.get_posts():
        if not post.is_video:
            continue
        rows.append({"shortcode": post.shortcode, "url": f"https://www.instagram.com/reel/{post.shortcode}/",
                     "date": post.date_utc.strftime("%Y-%m-%d"), "views": post.video_view_count or 0,
                     "likes": post.likes, "comments": post.comments, "seconds": round(post.video_duration or 0, 1),
                     "caption": (post.caption or "").replace("\n", " ").replace("\t", " ")[:300]})
        if len(rows) >= count:
            break
        time.sleep(pause)  # human pace on purpose
    if not rows:
        sys.exit("No reels found (private account, or Instagram wants a login: use --session-user).")
    med = statistics.median(r["views"] for r in rows) or 1
    for r in rows:
        r["outlier_x"] = round(r["views"] / med, 1)
    outroot = Path(outroot); outroot.mkdir(parents=True, exist_ok=True)
    tsv = outroot / f"{prof.username}.tsv"
    with open(tsv, "w") as f:  # same columns as ig-viral's swipe.py
        f.write("account\tfollowers\tmedian\tviews\thook\n")
        for r in rows:
            f.write(f"@{prof.username}\t{prof.followers}\t{int(med)}\t{r['views']}\t{r['caption'][:120]}\n")
    (outroot / f"{prof.username}.json").write_text(json.dumps({"handle": prof.username, "followers": prof.followers, "median_views": med, "reels": rows}, indent=2, ensure_ascii=False))
    print(f"@{prof.username}: {prof.followers} followers · median {int(med)} views over {len(rows)} reels")
    for r in sorted(rows, key=lambda r: -r["outlier_x"])[:10]:
        print(f"  {r['outlier_x']:>6}x  {r['views']:>9}  {r['seconds']:>5}s  {r['url']}  {r['caption'][:60]}")
    print(tsv)

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("analyze", help="scene-by-scene breakdown of a video file or URL")
    a.add_argument("src", nargs="+")
    a.add_argument("--out", default="reel-lens-out")
    a.add_argument("--cookies"); a.add_argument("--cookies-from-browser")
    a.add_argument("--no-speech", action="store_true")
    b = sub.add_parser("profile", help="latest reels of an Instagram account with outlier multiples")
    b.add_argument("handle", nargs="+")
    b.add_argument("--count", type=int, default=24)
    b.add_argument("--out", default="reel-lens-out")
    b.add_argument("--session-user", help="your Instagram username with a saved instaloader session")
    b.add_argument("--sessionfile")
    args = p.parse_args()
    if args.cmd == "analyze":
        for s in args.src:
            analyze(s, args.out, args.cookies, args.cookies_from_browser, args.no_speech)
    else:
        for h in args.handle:
            profile(h, args.count, args.out, args.session_user, args.sessionfile)
            time.sleep(10)

if __name__ == "__main__":
    main()
