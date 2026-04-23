"""Generate the GitHub social preview image (1280x640) for the repo.

Output: docs/screenshots/social-preview.png

Upload via GitHub Repo Settings -> Social preview -> Edit (web UI only).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

REPO_ROOT = Path(__file__).resolve().parent.parent
SCREENSHOTS = REPO_ROOT / "docs" / "screenshots"
OUTPUT = SCREENSHOTS / "social-preview.png"

CANVAS = (1280, 640)
BG_TOP = (16, 18, 40)
BG_BOTTOM = (47, 25, 95)
ACCENT = (139, 92, 246)
TEXT_PRIMARY = (255, 255, 255)
TEXT_SECONDARY = (198, 198, 220)
TEXT_MUTED = (140, 140, 170)

FONT_DIRS = [
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts"),
    Path("/System/Library/Fonts"),
]
FONT_CANDIDATES = [
    "segoeuib.ttf",
    "segoeui.ttf",
    "Arial Bold.ttf",
    "arialbd.ttf",
    "DejaVuSans-Bold.ttf",
]


def find_font(bold: bool = False) -> Path | None:
    names = FONT_CANDIDATES if bold else [
        "segoeui.ttf",
        "Arial.ttf",
        "arial.ttf",
        "DejaVuSans.ttf",
    ]
    for d in FONT_DIRS:
        if not d.exists():
            continue
        for name in names:
            p = d / name
            if p.exists():
                return p
    return None


def gradient_background(size: tuple[int, int]) -> Image.Image:
    w, h = size
    img = Image.new("RGB", size, BG_TOP)
    for y in range(h):
        t = y / (h - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        for x in range(w):
            img.putpixel((x, y), (r, g, b))
    return img


def gradient_fast(size: tuple[int, int]) -> Image.Image:
    """Vertical gradient using numpy-free pixel arithmetic via paste."""
    w, h = size
    base = Image.new("RGB", (1, h))
    for y in range(h):
        t = y / (h - 1)
        r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
        g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
        b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
        base.putpixel((0, y), (r, g, b))
    return base.resize((w, h))


def drop_shadow(img: Image.Image, offset=(0, 16), blur=22, opacity=140) -> Image.Image:
    w, h = img.size
    pad = blur * 2
    shadow = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
    silhouette = Image.new("RGBA", img.size, (0, 0, 0, opacity))
    if img.mode == "RGBA":
        silhouette.putalpha(img.getchannel("A"))
    shadow.paste(silhouette, (pad + offset[0], pad + offset[1]), silhouette)
    return shadow.filter(ImageFilter.GaussianBlur(blur))


def main() -> None:
    canvas = gradient_fast(CANVAS).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    font_path_bold = find_font(bold=True)
    font_path_regular = find_font(bold=False)
    if not font_path_bold or not font_path_regular:
        raise SystemExit("No suitable font found")

    title_font = ImageFont.truetype(str(font_path_bold), 128)
    subtitle_font = ImageFont.truetype(str(font_path_regular), 38)
    tag_font = ImageFont.truetype(str(font_path_regular), 26)
    url_font = ImageFont.truetype(str(font_path_regular), 22)

    left_x = 72
    draw.rectangle([left_x, 168, left_x + 10, 400], fill=ACCENT)

    text_x = left_x + 34
    draw.text((text_x, 150), "Tonado", font=title_font, fill=TEXT_PRIMARY)
    draw.text((text_x, 302), "Die Musikbox, die dir gehört.", font=subtitle_font, fill=TEXT_SECONDARY)
    draw.text((text_x, 560), "github.com/t13gazh/tonado", font=url_font, fill=TEXT_MUTED)

    player = Image.open(SCREENSHOTS / "01-player.png").convert("RGBA")
    target_h = 520
    scale = target_h / player.height
    target_w = int(player.width * scale)
    player = player.resize((target_w, target_h), Image.LANCZOS)

    shadow = drop_shadow(player)
    px = CANVAS[0] - target_w - 96
    py = (CANVAS[1] - target_h) // 2
    canvas.paste(shadow, (px - shadow.width // 2 + target_w // 2, py - shadow.height // 2 + target_h // 2), shadow)
    canvas.paste(player, (px, py), player)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.convert("RGB").save(OUTPUT, "PNG", optimize=True)
    print(f"Written: {OUTPUT}  ({OUTPUT.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
