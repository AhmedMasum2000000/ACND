# ACND

The official site for **ACND** (A H Al Masum) — Bangladeshi electronic producer, DJ and composer.

A scroll-driven journey through an ASCII/pixel world that reacts to the pointer, to scroll velocity
and, if the visitor opts in, to live audio. Six acts, one continuous scroll, one animated character
grid behind all of it.

**Release kit:** reels and banners for *Down In Bossa* (ACND × Ash Army, Profi Music) are in [`press/down-in-bossa/`](press/down-in-bossa/), ready to download, and playable at https://ahmedmasum2000000.github.io/ACND/down-in-bossa/.

```
npm install
npm run dev      # http://localhost:5173
npm run build    # -> dist/
npm run preview  # serve the production build
```

---

## Editing the content

**Everything you will normally want to change lives in one file: [`src/data/acnd.ts`](src/data/acnd.ts).**

Bio, releases, playlists, socials, genres, act names, the boot sequence, the booking address and the
canonical URL are all there, typed and commented. No component reads content from anywhere else, so
you never have to touch JSX to update the site.

Placeholders are marked `// TODO`. The important ones:

| What | Where | Why it matters |
| --- | --- | --- |
| `artist.siteUrl` | top of the file | Feeds the canonical tag, Open Graph URL, sitemap and JSON-LD. Set this the moment you have a domain. |
| `socials[].url` | `socials` | Currently placeholder profile URLs. |
| `releases[].links` | `releases` | Streaming links per platform. Omit any platform you are not on. |
| `playlists[].url` | `playlists` | Playlist and DJ-set links. |
| `artist.bookingEmail` | top of the file | Appears in Act 06 and in the structured data. |

Adding a release is one object in the `releases` array. Cover art is **optional** — leave `cover`
undefined and the site generates a deterministic ASCII cover from the release id, which is what every
release currently uses.

After editing, run `npm run build`. The head tags, JSON-LD, `robots.txt`, `sitemap.xml` and the no-JS
fallback are all regenerated from that same file, so they can never drift out of sync with what a
visitor sees.

### Replacing the portrait

```
npm install --save-dev sharp        # only needed for this one script
node scripts/optimize-portrait.mjs path/to/photo.jpg
```

That writes `public/portrait-1200.webp`, `public/portrait-480.webp` and `public/og.jpg`. Commit the
outputs; `sharp` is never needed at build time or in CI.

---

## How it works

### The field

One `<canvas>`, one `requestAnimationFrame` loop, everything drawn as characters. The performance
trick that makes this viable on a phone is in [`src/engine/glyphAtlas.ts`](src/engine/glyphAtlas.ts):
every glyph is rasterised once, in every tint, into an offscreen atlas, and the hot loop does nothing
but `drawImage`. Calling `fillText` per cell would mean ~400,000 text rasterisations a second.

Each act does not get its own renderer — it gets a set of **weights**
([`src/engine/field.ts`](src/engine/field.ts)) that the renderer eases toward continuously. That is
what makes the world feel like it is transforming rather than cutting between backgrounds.

| Mode | Act | Look |
| --- | --- | --- |
| `RAIN` | 01 Signal | Falling glyph columns |
| `PORTRAIT` | 02 The Artist | The photograph, dithered, resolving as you scroll |
| `WAVE` | 03 The Spectrum | Stacked sine bands |
| `GRID` | 04 The Catalog | A breathing lattice |
| `TUNNEL` | 05 The Sets | Radial rings pulling inward |
| `NOISE` | 00 Gate / 06 Transmission | Formless static |

Guardrails, all in [`src/engine/renderer.ts`](src/engine/renderer.ts): device pixel ratio capped at
1.5, coarser cells and a 45fps budget below 768px, the loop stops entirely when the tab is hidden,
and `prefers-reduced-motion` renders a single static frame per act.

### The portrait

The photograph is decoded once and re-sampled into a luminance buffer at grid resolution whenever the
grid changes size, so it is always pixel-exact for the current viewport. Two details matter:

- **The luminance is inverted.** In the source the artist is a dark silhouette against bright neon.
  This is an additive field of glyphs on a black page, so mapping bright-to-dense would render the
  city and leave a person-shaped hole where the subject is.
- **On screens wider than 900px the portrait is confined to the right of the frame**, so the bio
  column never lands on the face.

### Audio

Opt-in, off by default, and entirely procedural — no audio files ship. The ambient bed is three
detuned oscillators through a slowly sweeping filter; interface sounds are short filtered noise
bursts. Nothing is constructed until the visitor enables sound, so no `AudioContext` is ever created
without a user gesture. An `AnalyserNode` feeds amplitude back into the field, so the visuals breathe
with the sound.

### SEO

The canvas is decorative and `aria-hidden`. **Every word that matters is real semantic HTML**, and
the built `index.html` additionally carries:

- title, description, canonical, full Open Graph and Twitter card tags
- JSON-LD: a `MusicGroup`, a `WebSite`, and a `MusicAlbum` or `MusicRecording` per release
- a complete no-JS fallback — bio, every release, every set, every link — which React removes on mount

All generated at build time by the plugin in [`vite.config.ts`](vite.config.ts) from `acnd.ts`.

### Weight

| Asset | Gzipped |
| --- | --- |
| App JS | ~15 kB |
| React | ~46 kB |
| CSS | ~5 kB |
| **Total JS + CSS** | **~66 kB** |

No animation library, no icon library, no UI framework. If you add a dependency, check the build
output — the budget is 90 kB of gzipped JS.

---

## Deploying

**GitHub Pages — already set up.** [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)
builds and publishes on every push. It enables Pages via the API on first run, so there is nothing to
click in the repository settings, and it passes the subpath to the build itself:

| Variable | Value on Pages | What it fixes |
| --- | --- | --- |
| `BASE_PATH` | `/mahiiiiiiiiiiiiii` | Asset URLs. A project site is served from a subpath, so `/portrait-1200.webp` would 404. |
| `SITE_URL` | `https://<user>.github.io/<repo>` | Canonical tag, Open Graph URL, sitemap and JSON-LD. |

Both are read at build time only — `vite.config.ts` normalises the trailing slash, and `src/lib/asset.ts`
resolves runtime asset paths against the base.

**Vercel / Netlify** — connect the repo. Build command `npm run build`, output directory `dist`.
Neither variable is needed; the defaults are root-relative.

**Any other static host** — `npm run build` and upload `dist/`.

If you move to a custom domain, set `artist.siteUrl` in `src/data/acnd.ts` and drop the two variables
from the workflow.

---

## Accessibility

Reduced motion is honoured throughout — no canvas animation, no glitch, no marquee, no scanline
drift, and text resolves instantly. Every interactive element is reachable by keyboard with a visible
focus ring, the gate is skippable and hands focus back to the main content, and the custom cursor is
suppressed on touch devices and never replaces the real one on coarse pointers.
