# reel-lens

A free, local, open-source replacement for paid short-form video analysers
(the "watch this reel" and "list this account's reels with views" features).

Built for ACND HQ research: study **formats** that work, then make our own videos.

## What it does

| Command | Output |
|---|---|
| `analyze <file or URL> ...` | `report.md` + `report.json`: length, resolution, number of cuts and cuts/second, a keyframe per scene, **on-screen text per scene (OCR)**, **spoken words with timestamps (Whisper)**, tempo guess (BPM), loudness (LUFS), and a `contact_sheet.png` |
| `profile <handle> ...` | latest N reels with views, likes, comments, length, caption; the account's **median views** and each reel's **outlier multiple** (views / median). Also writes a TSV in the format `ig-viral`'s `swipe.py` reads |

Everything runs on your machine. Nothing is sent to a third-party service.

## Install

```bash
# system tools
sudo apt install ffmpeg tesseract-ocr        # macOS: brew install ffmpeg tesseract
# python packages
pip install -r requirements.txt
```

## Use

```bash
# 1) Analyse a video you already have (screen recording, export, download)
python3 reel_lens.py analyze my_clip.mp4

# 2) Analyse an Instagram reel by URL, using YOUR logged-in browser session
python3 reel_lens.py analyze "https://www.instagram.com/reel/XXXX/" --cookies-from-browser chrome

# 3) Profile stats: log in once in your own terminal (asks for your password locally, stored by instaloader)
instaloader --login your_username
python3 reel_lens.py profile theproducersclassroom igzistance --count 24 --session-user your_username
```

Output goes to `reel-lens-out/<name>/`.

## Rules we follow

- **Your own session, human pace.** Instagram requires a login for most of this. Use your own account,
  small counts (default 24 reels), and the built-in pauses. Do not run it as a crawler or loop it in the background:
  that breaks Instagram's terms and gets accounts action-blocked.
- **Never paste passwords or cookies into chats.** Log in only in your own terminal or browser.
- **Study formats, not footage.** Use the reports to learn hook shapes, cut rhythm, length and structure.
  Do not re-upload other creators' videos, audio or captions.

## Notes

- OCR reads big on-screen text well; stylised fonts and tiny labels are hit-and-miss.
- Tempo is a guess from low-end onsets; half/double-time answers happen.
- Speech uses the Whisper "base" model on CPU; the first run downloads it (~150 MB).

MIT licensed. Part of the ACND repo.
