# Cascais Padel Crew

Static site — three pages, no framework, no build step to serve.

```
index.html  rules.html  tournament.html
img/        photos: AVIF + WebP + progressive JPEG, several widths each
fonts/      self-hosted woff2 (DM Sans, Space Grotesk)
src/        the original design-tool exports (see below)
build.py    regenerates the three pages from src/
```

Serve the repo root as-is:

```sh
python3 -m http.server 8000
```

## Where this came from

The pages in `src/` are self-extracting bundles produced by a design tool.
Each one carries every asset base64-encoded inside a `__bundler/manifest`
script tag, plus the real HTML in a `__bundler/template` tag. Opening one
made the browser decode ~2 MB of base64, mint blob URLs, boot React and a
69 KB design-tool runtime, and only then paint.

`build.py` unpacks that into ordinary static files:

| | before | after |
|---|---|---|
| `index.html` | 2,647,361 B | 41,203 B |
| `rules.html` | 627,349 B | 33,203 B |
| `tournament.html` | 631,758 B | 37,850 B |
| JS shipped | 277 KB (React, react-dom, dc-runtime, omelette) | ~1 KB inline |
| LCP (local, cold) | 256 / 84 / 512 ms | 28 / 48 / 52 ms |

The runtime only ever provided four things, all replaced with plain CSS and
about twenty lines of vanilla JS:

- `style-hover="..."` → real CSS `:hover` rules
- `sc-camel-on-click="{{ ... }}"` → one delegated `click` listener
- `<sc-if value="{{ lightboxOpen }}">` → a `hidden` dialog
- `<image-slot>` → `<picture>` (it was a drag-and-drop *authoring* widget,
  of no use on a published page)

Images are served as AVIF → WebP → progressive JPEG via `<picture>`, at the
width actually needed, with `loading="lazy"`, `decoding="async"` and
intrinsic `width`/`height` to avoid layout shift. The LCP image is
preloaded and marked `fetchpriority="high"` instead.

Two fixes fell out of the conversion: the lightbox pointed at an
`./assets/` folder that was never in the bundle (so it was broken), and the
tournament banner was hot-linked from Firebase — it now lives in `img/`.

Rendering is unchanged: a headless-Chromium screenshot diff against the
originals shows differences only inside image regions (re-encoding), with
identical page heights and identical text layout.

## Rebuilding

```sh
python3 build.py     # needs Pillow with AVIF + WebP support
```
