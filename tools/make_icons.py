#!/usr/bin/env python3
"""Erzeugt das komplette Site-Icon-Set aus einem N8schicht-Logo (SVG) – für alle N8schicht-Repos nutzbar.

  python3 tools/make_icons.py <logo.svg> <zielordner> "<Titel>" "<Untertitel>" [favicon.svg]

Kleine Größen (16/32/48 px) werden aus der optionalen, vereinfachten Favicon-SVG erzeugt –
das volle Logo ist dafür zu detailreich.

Erzeugt: favicon.ico (16/32/48), favicon-16.png, favicon-32.png, apple-touch-icon.png (180, randlos),
icon-192.png, icon-512.png, icon-maskable-512.png (Safe-Zone 80 %), og-image.png (1200×630),
site.webmanifest. Benötigt: rsvg-convert (librsvg2-bin) und Pillow.
"""
import io
import json
import os
import subprocess
import sys

from PIL import Image

BG = (12, 18, 48)          # Nachthimmel aus dem Logo (#0c1230)
THEME = "#070b17"


def render(svg: str, size: int) -> Image.Image:
    png = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), svg], check=True, capture_output=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")


def on_bg(img: Image.Image, size: int, scale: float) -> Image.Image:
    bg = Image.new("RGBA", (size, size), BG + (255,))
    inner = img.resize((int(size * scale), int(size * scale)), Image.LANCZOS)
    off = (size - inner.width) // 2
    bg.alpha_composite(inner, (off, off))
    return bg


def og_image(svg: str, title: str, subtitle: str, out: str) -> None:
    w, h = 1200, 630
    esc = lambda t: t.replace("&", "&amp;").replace("<", "&lt;")  # noqa: E731
    card = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">
<defs><radialGradient id="a" cx="0.08" cy="-0.1" r="0.9"><stop offset="0" stop-color="#0a84ff" stop-opacity=".45"/><stop offset="1" stop-color="#0a84ff" stop-opacity="0"/></radialGradient>
<radialGradient id="b" cx="1" cy="0" r="0.8"><stop offset="0" stop-color="#bf5af2" stop-opacity=".35"/><stop offset="1" stop-color="#bf5af2" stop-opacity="0"/></radialGradient>
<linearGradient id="t" x1="0" x2="1"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#b4e2ff"/></linearGradient></defs>
<rect width="{w}" height="{h}" fill="#070b17"/><rect width="{w}" height="{h}" fill="url(#a)"/><rect width="{w}" height="{h}" fill="url(#b)"/>
<text x="500" y="300" font-family="Inter,'Segoe UI',Helvetica,Arial,sans-serif" font-weight="800" font-size="84" fill="url(#t)">{esc(title)}</text>
<text x="504" y="370" font-family="Inter,'Segoe UI',Helvetica,Arial,sans-serif" font-weight="600" font-size="38" fill="#9bd8ff">{esc(subtitle)}</text>
<text x="504" y="440" font-family="Inter,'Segoe UI',Helvetica,Arial,sans-serif" font-weight="600" font-size="28" fill="#8a93a8">Die N8schicht</text></svg>"""
    tmp = out + ".svg"
    with open(tmp, "w") as f:
        f.write(card)
    subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), tmp, "-o", out], check=True)
    os.remove(tmp)
    card_img = Image.open(out).convert("RGBA")
    card_img.alpha_composite(render(svg, 360), (90, 135))     # Logo einsetzen
    card_img.convert("RGB").save(out)


def main() -> None:
    svg, out, title, subtitle = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    small_svg = sys.argv[5] if len(sys.argv) > 5 else svg
    os.makedirs(out, exist_ok=True)
    big = render(svg, 1024)
    for s in (16, 32):
        render(small_svg, s * 4).resize((s, s), Image.LANCZOS).save(f"{out}/favicon-{s}.png")
    render(small_svg, 256).save(f"{out}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    on_bg(big, 180, 1.0).convert("RGB").save(f"{out}/apple-touch-icon.png")       # iOS: randlos, ohne Transparenz
    for s in (192, 512):
        big.resize((s, s), Image.LANCZOS).save(f"{out}/icon-{s}.png")
    on_bg(big, 512, 0.80).save(f"{out}/icon-maskable-512.png")                      # Android: Safe-Zone
    og_image(svg, title, subtitle, f"{out}/og-image.png")
    manifest = {
        "name": title, "short_name": title.replace("N8 ", "N8 ")[:12], "description": subtitle,
        "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": THEME, "theme_color": THEME, "lang": "de",
        "icons": [
            {"src": "/static/icons/icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
            {"src": "/static/icons/icon-maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
            {"src": "/static/n8crosslink-icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
        ],
    }
    with open(f"{out}/site.webmanifest", "w") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print("Icons erzeugt in", out, sorted(os.listdir(out)))


if __name__ == "__main__":
    main()
