#!/usr/bin/env python3
"""Render the social-share banner (img/og.jpg) at 1200x630.

Composed as HTML and screenshotted with headless Chromium so it reuses the
site's real fonts and hero photo -- a Pillow version would need the woff2
files decoded and would drift from the site's look.

    python3 make-og.py
"""
import base64, pathlib
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).parent

def data_uri(path, mime):
    return f"data:{mime};base64," + base64.b64encode((ROOT / path).read_bytes()).decode()

HTML = f"""
<style>
  @font-face {{ font-family:'Space Grotesk'; font-weight:700; font-display:block;
    src:url('{data_uri("fonts/spacegrotesk-latin.woff2","font/woff2")}') format('woff2'); }}
  @font-face {{ font-family:'DM Sans'; font-weight:400; font-display:block;
    src:url('{data_uri("fonts/dmsans-latin.woff2","font/woff2")}') format('woff2'); }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ width:1200px; height:630px; overflow:hidden; background:#101216; }}
  .wrap {{ position:relative; width:1200px; height:630px; }}
  .photo {{ position:absolute; inset:0; width:100%; height:100%;
            object-fit:cover; object-position:center 30%; }}
  .scrim {{ position:absolute; inset:0;
    background:linear-gradient(to top, rgba(16,18,22,0.97) 0%, rgba(16,18,22,0.80) 45%, rgba(16,18,22,0.60) 100%),
               linear-gradient(to bottom, rgba(16,18,22,0.55) 0%, rgba(16,18,22,0) 55%); }}
  .content {{ position:absolute; inset:0; padding:64px; display:flex;
              flex-direction:column; justify-content:flex-end; }}
  .eyebrow {{ display:flex; align-items:center; gap:10px; margin-bottom:22px; }}
  .dot {{ width:9px; height:9px; border-radius:50%; background:#f4c11f; }}
  .eyebrow span {{ font-family:'Space Grotesk',sans-serif; font-weight:700; font-size:16px;
                   letter-spacing:0.14em; text-transform:uppercase; color:#f3f4f1; }}
  h1 {{ font-family:'Space Grotesk',sans-serif; font-weight:700; color:#f3f4f1;
        font-size:74px; line-height:0.98; letter-spacing:-0.035em; max-width:15ch; }}
  p {{ font-family:'DM Sans',sans-serif; font-size:25px; line-height:1.5;
       color:rgba(243,244,241,0.80); margin-top:24px; max-width:40ch; }}
  .brand {{ position:absolute; top:56px; left:64px; display:flex;
            align-items:center; gap:16px; }}
  .brand img {{ width:64px; height:64px; border-radius:50%; object-fit:cover; background:#000; }}
  .brand span {{ font-family:'Space Grotesk',sans-serif; font-weight:700;
                 font-size:27px; letter-spacing:-0.01em; color:#f3f4f1; }}
</style>
<div class="wrap">
  <img class="photo" src="{data_uri("img/hero-court-1050.jpg","image/jpeg")}">
  <div class="scrim"></div>
  <div class="brand">
    <img src="{data_uri("img/logo-256.jpg","image/jpeg")}">
    <span>Cascais Padel Crew</span>
  </div>
  <div class="content">
    <div class="eyebrow"><i class="dot"></i><span>Cascais &middot; Portugal</span></div>
    <h1>A friendly padel community in Cascais.</h1>
    <p>Find a partner, share a ride to tournaments, meet the local padel community.</p>
  </div>
</div>
"""

with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
    pg.set_content(HTML, wait_until="networkidle")
    pg.wait_for_timeout(600)                     # let the webfonts settle
    pg.screenshot(path="img/og.png")
    b.close()

from PIL import Image
im = Image.open("img/og.png").convert("RGB")
im.save("img/og.jpg", "JPEG", quality=88, progressive=True, optimize=True)
pathlib.Path("img/og.png").unlink()
print(f"img/og.jpg  {im.size[0]}x{im.size[1]}  {pathlib.Path('img/og.jpg').stat().st_size:,} B")
