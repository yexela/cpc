#!/usr/bin/env python3
"""Rebuild the static site from the design-tool exports in src/.

The files in src/ are self-extracting bundles: a `__bundler/manifest` island
holding every asset as base64 (~2 MB for index) plus a `__bundler/template`
island holding the real HTML.  Opening one decoded the base64 in the browser,
minted blob URLs, booted React + a 69 KB design-tool runtime, and only then
painted the page.

This script turns them into ordinary static HTML:

  * assets are written out to img/ and fonts/
  * photos get resized derivatives in AVIF, WebP and progressive JPEG
  * <image-slot> (an authoring widget) becomes a responsive <picture>
  * the runtime's four features -- hover styles, click handlers, a lightbox
    and one conditional -- become plain CSS and ~20 lines of vanilla JS

React, react-dom, dc-runtime and omelette are dropped entirely; nothing on
these pages needed them.

    python3 build.py            # rebuild everything
"""
import base64, gzip, hashlib, html, json, os, re, sys
from PIL import Image

PAGES = ("index", "rules", "tournament")

# ---------------------------------------------------------------- assets ---
# content hash (sha256[:12] of the decoded bytes) -> output name
IMG_NAMES = {"27b2b7fdeb1f": "logo", "cac966d5c9ee": "hero-court",
             "23258ea28a17": "league-banner", "5a30c8a17fd8": "bbq",
             "275052673bcf": "crew"}
FONT_NAMES = {"aa530716b0d3": "dmsans-latin",       "0d0609aee778": "dmsans-latinext",
              "a0d054c4af55": "spacegrotesk-latin", "054c266fbb44": "spacegrotesk-latinext",
              "d699664b145b": "spacegrotesk-viet",  "8be0594f2238": "caprasimo-latin",
              "8cbef7cdad7b": "caprasimo-latinext", "8330490a01c6": "figtree-latin",
              "f153aa07c1b1": "figtree-latinext"}

# The tournament banner is the one asset that was never bundled -- the page
# hot-linked it from Firebase.  Kept in the repo so the site has no external
# image dependency.
REMOTE_BANNER = "tournament-banner"

def js_name(b):
    t = b[:400].decode("utf-8", "replace")
    if "@license React" in t: return "react-dom" if "react-dom" in t else "react"
    if "dc-runtime/src" in t: return "dc-runtime"
    if "omelette starter" in t: return "omelette"
    if "@ds-bundle" in t:     return "ds-bundle"
    raise SystemExit("unrecognised script: " + t[:120])

def island(src, tag):
    m = re.search(r'<script type="__bundler/%s">\s*(.*?)\s*</script>' % tag, src, re.S)
    return json.loads(m.group(1)) if m else None

def extract():
    """Write img/ + fonts/ from the bundles; return {"page|uuid": path}."""
    for d in ("img", "fonts"): os.makedirs(d, exist_ok=True)
    paths, written = {}, set()
    for page in PAGES:
        man = island(open(f"src/{page}.html", encoding="utf-8").read(), "manifest")
        for uuid, v in man.items():
            raw = base64.b64decode(v["data"])
            if v["compressed"]: raw = gzip.decompress(raw)
            h = hashlib.sha256(raw).hexdigest()[:12]
            if "javascript" in v["mime"]:
                # Mapped so the <script> tags stay matchable, but never written:
                # the rebuilt pages do not load any of this.
                paths[f"{page}|{uuid}"] = f"libs/{js_name(raw)}.js"
                continue
            if   h in IMG_NAMES:  path = f"img/{IMG_NAMES[h]}.jpg"
            elif h in FONT_NAMES: path = f"fonts/{FONT_NAMES[h]}.woff2"
            else: raise SystemExit(f"unmapped asset {h} ({v['mime']}, {len(raw)} B)")
            if path not in written:
                open(path, "wb").write(raw); written.add(path)
            paths[f"{page}|{uuid}"] = path
    return paths

# ------------------------------------------------------------ derivatives ---
WIDTHS = {"logo": [64, 128, 256], "hero-court": [640, 1050],
          "league-banner": [640, 1000, 1367], "bbq": [640, 1050],
          "crew": [640, 1050], REMOTE_BANNER: [512]}

def derivatives():
    """Resize each photo and encode AVIF / WebP / progressive JPEG."""
    out = {}
    for name, widths in WIDTHS.items():
        src = Image.open(f"img/{name}.jpg"); src.load(); src = src.convert("RGB")
        nw, nh = src.size
        out[name] = {"w": nw, "h": nh, "widths": []}
        for w in widths:
            if w > nw: continue
            im = src.resize((w, round(nh * w / nw)), Image.LANCZOS)
            im.save(f"img/{name}-{w}.jpg",  "JPEG", quality=78, progressive=True,
                    optimize=True, subsampling=1)
            im.save(f"img/{name}-{w}.webp", "WEBP", quality=74, method=6)
            im.save(f"img/{name}-{w}.avif", "AVIF", quality=52)
            out[name]["widths"].append(w)
    return out

# ------------------------------------------------------------------ pages ---
# image-slot id -> (image, alt, sizes, eager)
SLOTS = {
    "hero-photo":       ("hero-court",   "Padel court in Cascais",      "100vw", True),
    "card-tournament":  (REMOTE_BANNER,  "Beginner tournament banner",  "(max-width:760px) 100vw, 50vw", False),
    "tournament-banner":(REMOTE_BANNER,  "Beginner tournament banner",  "(max-width:900px) 100vw, 60vw", True),
    "card-league":      ("league-banner","Cascais Padel Crew league",   "(max-width:760px) 100vw, 50vw", False),
    "social-1":         ("bbq",          "Crew barbecue",               "(max-width:760px) 100vw, 50vw", False),
    "social-2":         ("crew",         "The crew after a game",       "(max-width:760px) 100vw, 50vw", False),
}
LCP = {"index": "hero-court", "tournament": REMOTE_BANNER, "rules": None}
SITE = "https://cascaispadelcrew.com"
OG_ALT = "Cascais Padel Crew - a friendly padel community in Cascais, Portugal"
DESC = {
 "index": "A friendly padel community in Cascais, Portugal. Find partners, share rides to tournaments and meet local players.",
 "rules": "Match and tournament rules for the Cascais Padel Crew.",
 "tournament": "Beginner padel tournament in Cascais - format, schedule and how to enter.",
}

LIGHTBOX_JS = """
(function () {
  var box = document.getElementById('lightbox');
  if (!box) return;
  var img = document.getElementById('lightbox-img');
  function open(src, alt) {
    img.src = src; img.alt = alt || '';
    box.hidden = false;
    document.documentElement.style.overflow = document.body.style.overflow = 'hidden';
  }
  function close() {
    box.hidden = true; img.removeAttribute('src');
    document.documentElement.style.overflow = document.body.style.overflow = '';
  }
  document.addEventListener('click', function (e) {
    var t = e.target.closest('[data-lightbox]');
    if (t) { e.preventDefault(); open(t.getAttribute('data-lightbox'), t.getAttribute('data-lightbox-alt')); return; }
    if (e.target.closest('[data-lightbox-close]')) { e.preventDefault(); close(); }
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') close(); });
})();
""".strip()


def build(page, assets, imgs):
    def srcset(n, ext): return ", ".join(f"img/{n}-{w}.{ext} {w}w" for w in imgs[n]["widths"])
    def biggest(n, ext="jpg"): return f"img/{n}-{imgs[n]['widths'][-1]}.{ext}"

    def picture(name, alt, sizes, eager, style):
        m = imgs[name]
        load = 'decoding="async" fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
        return (f'<picture style="{style}">'
                f'<source type="image/avif" srcset="{srcset(name,"avif")}" sizes="{sizes}">'
                f'<source type="image/webp" srcset="{srcset(name,"webp")}" sizes="{sizes}">'
                f'<img src="{biggest(name)}" srcset="{srcset(name,"jpg")}" sizes="{sizes}"'
                f' alt="{html.escape(alt)}" width="{m["w"]}" height="{m["h"]}" {load}'
                f' style="width:100%;height:100%;object-fit:cover;display:block"></picture>')

    src = open(f"src/{page}.html", encoding="utf-8").read()
    tpl = island(src, "template")

    # uuid -> real path (the same substitution the runtime used to do at load time)
    for key, path in assets.items():
        p, uuid = key.split("|", 1)
        if p == page: tpl = tpl.replace(uuid, path)

    # style-hover="..." -> a real CSS :hover rule
    hover = []
    def hover_attr(m):
        hover.append(m.group(1)); return f' data-hv="{len(hover)-1}"'
    tpl = re.sub(r'\s+style-hover="([^"]*)"', hover_attr, tpl)

    # <image-slot> -> <picture>
    def slot(m):
        a = m.group(1)
        sid = re.search(r'id="([^"]+)"', a).group(1)
        style = (re.search(r'style="([^"]*)"', a) or [None, ""])[1]
        if sid not in SLOTS:
            print(f"  !! unmapped image-slot #{sid}", file=sys.stderr); return m.group(0)
        name, alt, sizes, eager = SLOTS[sid]
        return picture(name, alt, sizes, eager, style)
    tpl = re.sub(r'<image-slot\s+([^>]*?)>\s*</image-slot>', slot, tpl)

    # the logo shipped at 1080px but is shown at 38px / 148px
    def logo(m):
        style = m.group("style"); small = "width:38px" in style
        px = 38 if small else 148
        load = 'decoding="async" fetchpriority="high"' if small else 'loading="lazy" decoding="async"'
        return (f'<img src="img/logo-{"128" if small else "256"}.jpg"'
                f' srcset="img/logo-128.jpg 128w, img/logo-256.jpg 256w" sizes="{px}px"'
                f' alt="Cascais Padel Crew" width="{px}" height="{px}" {load} style="{style}">')
    tpl = re.sub(r'<img src="img/logo\.jpg"[^>]*?style="(?P<style>[^"]*)"[^>]*>', logo, tpl)

    # runtime bindings -> plain HTML.  The two lightbox targets pointed at a
    # ./assets/ folder that was never in the bundle, so they were broken.
    # copy: the beginner tournament has no fixed weekly slot; dates go out
    # in the WhatsApp group.
    tpl = tpl.replace('>Every weekend<', '>Announced in the group<')

    tpl = tpl.replace('sc-camel-view-box=', 'viewBox=')
    tpl = tpl.replace('sc-camel-on-click="{{ openBbq2 }}"',
                      f'data-lightbox="{biggest("bbq")}" data-lightbox-alt="Crew barbecue"')
    tpl = tpl.replace('sc-camel-on-click="{{ openBbq3 }}"',
                      f'data-lightbox="{biggest("crew")}" data-lightbox-alt="The crew after a game"')
    tpl = tpl.replace('sc-camel-on-click="{{ closeLightbox }}"', 'data-lightbox-close')
    tpl = tpl.replace('ref="{{ imgRef }}"', 'id="lightbox-img"')
    tpl = re.sub(r'<span class="brand" sc-camel-on-click="\{\{ goIndex \}\}" style="([^"]*)">(.*?)</span>',
                 r'<a class="brand" href="index.html" style="\1;color:inherit;text-decoration:none">\2</a>',
                 tpl, flags=re.S)
    tpl = re.sub(r'<sc-if value="\{\{ lightboxOpen \}\}">\s*<div ',
                 '<div id="lightbox" hidden role="dialog" aria-modal="true" aria-label="Photo" ', tpl)
    tpl = tpl.replace('</sc-if>', '')

    # drop the runtime
    tpl = re.sub(r'<script type="text/x-dc".*?</script>', '', tpl, flags=re.S)
    tpl = re.sub(r'<script src="(libs|js)/[^"]*"></script>\s*', '', tpl)
    tpl = tpl.replace('<x-dc>', '').replace('</x-dc>', '')
    hm = re.search(r'<helmet>(.*?)</helmet>', tpl, re.S)
    helmet = hm.group(1).strip() if hm else ""
    tpl = re.sub(r'<helmet>.*?</helmet>\s*', '', tpl, flags=re.S)
    helmet = re.sub(r'<meta name="viewport"[^>]*>\s*', '', helmet)    # already in head
    helmet = re.sub(r'<link rel="preconnect"[^>]*>\s*', '', helmet)   # fonts are local now

    hv_css = "\n".join(f'[data-hv="{i}"]:hover{{{r}}}' for i, r in enumerate(hover))
    title = re.search(r'<title>(.*?)</title>', helmet, re.S).group(1).strip()
    url = SITE + ("/" if page == "index" else f"/{page}.html")
    og = [('og:type', 'website'), ('og:site_name', 'Cascais Padel Crew'),
          ('og:url', url), ('og:title', title), ('og:description', DESC[page]),
          ('og:image', f'{SITE}/img/og.jpg'), ('og:image:width', '1200'),
          ('og:image:height', '630'), ('og:image:alt', OG_ALT)]
    tw = [('twitter:card', 'summary_large_image'), ('twitter:title', title),
          ('twitter:description', DESC[page]), ('twitter:image', f'{SITE}/img/og.jpg'),
          ('twitter:image:alt', OG_ALT)]

    head = [f'<meta name="description" content="{html.escape(DESC[page])}">',
            f'<link rel="canonical" href="{url}">',
            *[f'<meta property="{k}" content="{html.escape(v)}">' for k, v in og],
            *[f'<meta name="{k}" content="{html.escape(v)}">' for k, v in tw],
            '<link rel="icon" href="img/logo-128.jpg">',
            '<link rel="preload" as="font" type="font/woff2" href="fonts/dmsans-latin.woff2" crossorigin>',
            '<link rel="preload" as="font" type="font/woff2" href="fonts/spacegrotesk-latin.woff2" crossorigin>']
    if LCP[page]:
        n = LCP[page]
        head.append(f'<link rel="preload" as="image" type="image/avif" href="{biggest(n,"avif")}"'
                    f' imagesrcset="{srcset(n,"avif")}" imagesizes="100vw" fetchpriority="high">')
    head.append(helmet)
    # `hidden` alone cannot hide the lightbox: its inline display:grid beats
    # the UA sheet's [hidden]{display:none}.
    head.append('<style>html,body{height:100%;margin:0}[hidden]{display:none!important}'
                f'picture{{display:block}}\n{hv_css}</style>')

    body = tpl[tpl.find('<body>') + 6: tpl.rfind('</body>')].strip()
    out = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
           '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
           + "\n".join(head) + "\n</head>\n<body>\n" + body
           + f"\n<script>\n{LIGHTBOX_JS}\n</script>\n</body>\n</html>\n")
    out = re.sub(r'\n{3,}', '\n\n', out)
    open(f"{page}.html", "w", encoding="utf-8").write(out)
    return len(src), len(out)


if __name__ == "__main__":
    assets = extract()
    imgs = derivatives()
    for page in PAGES:
        before, after = build(page, assets, imgs)
        print(f"{page+'.html':<17} {before:>10,} -> {after:>7,} B  ({after/before*100:4.1f}%)")
