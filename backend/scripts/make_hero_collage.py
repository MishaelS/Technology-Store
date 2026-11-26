"""The picture of the "build your PC" slide on the home page: real parts lying together, like a PC to build.
resources/photos/products -> resources/photos/web/hero-build.webp (+ hero-build-sm.webp)

Run from the repository root (needs Pillow):
    python3 backend/scripts/make_hero_collage.py

Every part is cut out of its background (photos with transparency as they are; on a white background
only the white that touches the edges goes away, white labels on the part stay), gets a soft shadow
and is laid in layers: the case at the back in the middle, the board beside it, the rest in front.
The result has a transparent background, so it lies on the colored circle of the slide.
Without the file the slide simply keeps its icon.
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
PHOTOS = ROOT / "resources/photos/products"
OUT = ROOT / "resources/photos/web"

CANVAS = (1600, 1300)
# (photo, height in px on the canvas, center x, bottom y) — from the back to the front
LAYOUT = [
    ("asus-rog-strix-z890-a-gaming-wifi/01.png", 740, 1200, 960),             # board, right, behind
    ("nzxt-h5-flow/01.png", 1040, 760, 1090),                                  # case, middle, the biggest
    ("corsair-vengeance-rgb-32gb-2x16-ddr5-6400/01.webp", 340, 300, 1060),     # memory, left, behind the PSU
    ("corsair-hx1200i-1200w/01.webp", 330, 330, 1250),                         # power supply, front left
    ("amd-ryzen-7-7800x3d/01.png", 360, 640, 1270),                            # CPU box, front
    ("samsung-990-pro-2tb-nvme/01.jpeg", 130, 900, 1285),                      # SSD, front middle
    ("asus-tuf-radeon-rx-7900-xtx-24gb/02.png", 500, 1200, 1280),              # graphics card, angled, front right
]


def cut_out(path: Path) -> Image.Image:
    """The part on a transparent background, cropped to itself."""
    with Image.open(path) as original:
        image = original.convert("RGBA")
    if image.getchannel("A").getextrema()[0] == 255:  # no transparency: take away the white around it
        rgb = image.convert("RGB")
        marker = (255, 0, 255)
        for corner in [(0, 0), (rgb.width - 1, 0), (0, rgb.height - 1), (rgb.width - 1, rgb.height - 1)]:
            if sum(rgb.getpixel(corner)) > 3 * 235:
                ImageDraw.floodfill(rgb, corner, marker, thresh=40)
        background = ImageChops.difference(rgb, Image.new("RGB", rgb.size, marker)).convert("L").point(
            [255 if v > 0 else 0 for v in range(256)])
        image.putalpha(ImageChops.multiply(image.getchannel("A"), background).filter(ImageFilter.GaussianBlur(0.6)))
    box = image.getchannel("A").point([255 if v > 8 else 0 for v in range(256)]).getbbox()
    return image.crop(box) if box else image


def with_shadow(part: Image.Image) -> tuple[Image.Image, int]:
    """The part over a soft shadow a bit below it. Returns the image and how far the shadow reaches down."""
    pad = 40
    shadow = Image.new("RGBA", (part.width + pad * 2, part.height + pad * 2), (0, 0, 0, 0))
    silhouette = Image.new("RGBA", part.size, (10, 16, 40, 255))
    silhouette.putalpha(part.getchannel("A").point(lambda v: v * 0.45))
    shadow.alpha_composite(silhouette, (pad, pad + 18))
    shadow = shadow.filter(ImageFilter.GaussianBlur(16))
    shadow.alpha_composite(part, (pad, pad))
    return shadow, pad


def main() -> None:
    canvas = Image.new("RGBA", CANVAS, (0, 0, 0, 0))
    for name, height, center_x, bottom in LAYOUT:
        path = PHOTOS / name
        if not path.exists():
            print(f"skipped (no photo): {name}")
            continue
        part = cut_out(path)
        part = part.resize((max(1, round(part.width * height / part.height)), height), Image.Resampling.LANCZOS)
        layer, pad = with_shadow(part)
        canvas.alpha_composite(layer, (center_x - layer.width // 2, bottom - part.height - pad))
    box = canvas.getchannel("A").getbbox()
    if box:
        canvas = canvas.crop(box)
    OUT.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT / "hero-build.webp", "WEBP", quality=86, method=6)
    small = canvas.copy()
    small.thumbnail((640, 640), Image.Resampling.LANCZOS)
    small.save(OUT / "hero-build-sm.webp", "WEBP", quality=80, method=6)
    size = (OUT / "hero-build.webp").stat().st_size // 1024
    print(f"hero-build.webp {canvas.width}x{canvas.height}, {size} KB")


if __name__ == "__main__":
    main()
