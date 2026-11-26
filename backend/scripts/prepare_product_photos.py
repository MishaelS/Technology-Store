"""Makes web versions of the collected product photos: resources/photos/products -> resources/photos/web.

Run from the repository root (needs Pillow):
    python3 backend/scripts/prepare_product_photos.py

Every photo becomes the same shape the site shows it in (docs/PHOTOS.md):
    1600x1200 (4:3) WebP, white background, the product whole and centered with a margin,
    plus a small copy NN-sm.webp (480x360) for cards, the cart, the builder and thumbnails:
    a card shows a photo about 230 px wide, so it loads ~15 KB instead of ~80 KB.
Empty white borders of the original are trimmed first, so products of different photos look the same size.
Photos are never cut and small ones are not blown up (at most x1.5), so nothing gets blurry.
Very small pictures (references, thumbnails) are skipped.

The originals in products/ stay as they are. The result is listed in web/manifest.json:
    {"amd-ryzen-7-7800x3d": ["/resources/photos/web/amd-ryzen-7-7800x3d/01.webp", ...], ...}
`./run.sh photos` (app/photos.py) gives these photos to the products.
"""

import json
from pathlib import Path

from PIL import Image, ImageChops, ImageOps

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "resources/photos/products"
TARGET = ROOT / "resources/photos/web"
URL = "/resources/photos/web"

SIZE = (1600, 1200)
MARGIN = 0.08       # free space around the product, part of the frame
MAX_UPSCALE = 1.5   # small photos grow at most this much
MIN_SIDE = 480      # longer side smaller than this: a thumbnail, skipped
QUALITY = 82
SMALL = (480, 360)  # the copy for cards; the frontend asks for NN-sm.webp (thumbUrl() in ui.js)
SMALL_QUALITY = 78
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
NOT_WHITE = [255 if v > 18 else 0 for v in range(256)]  # pixels that differ from white enough to count


def on_white(image: Image.Image) -> Image.Image:
    """Transparent parts become white; any other mode becomes plain RGB."""
    image = ImageOps.exif_transpose(image)
    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        white = Image.new("RGBA", image.size, (255, 255, 255, 255))
        return Image.alpha_composite(white, image).convert("RGB")
    return image.convert("RGB")


def trim(image: Image.Image) -> Image.Image:
    """Cuts empty near-white borders (the product itself stays whole)."""
    background = Image.new("RGB", image.size, (255, 255, 255))
    difference = ImageChops.difference(image, background).convert("L").point(NOT_WHITE)
    box = difference.getbbox()
    return image.crop(box) if box else image


def prepare(path: Path) -> Image.Image | None:
    with Image.open(path) as original:
        image = trim(on_white(original))
    if max(image.size) < MIN_SIDE:
        return None
    inner_w, inner_h = (int(side * (1 - 2 * MARGIN)) for side in SIZE)
    scale = min(inner_w / image.width, inner_h / image.height, MAX_UPSCALE)
    image = image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))), Image.Resampling.LANCZOS)
    frame = Image.new("RGB", SIZE, (255, 255, 255))
    frame.paste(image, ((SIZE[0] - image.width) // 2, (SIZE[1] - image.height) // 2))
    return frame


def main() -> None:
    manifest: dict[str, list[str]] = {}
    skipped = 0
    for folder in sorted(p for p in SOURCE.iterdir() if p.is_dir()):
        out = TARGET / folder.name
        out.mkdir(parents=True, exist_ok=True)
        for old in out.glob("*.webp"):
            old.unlink()
        urls = []
        for path in sorted(p for p in folder.iterdir() if p.suffix.lower() in EXTENSIONS):
            frame = prepare(path)
            if frame is None:
                skipped += 1
                continue
            name = f"{len(urls) + 1:02}.webp"
            frame.save(out / name, "WEBP", quality=QUALITY, method=6)
            frame.resize(SMALL, Image.Resampling.LANCZOS).save(out / name.replace(".webp", "-sm.webp"), "WEBP", quality=SMALL_QUALITY, method=6)
            urls.append(f"{URL}/{folder.name}/{name}")
        if urls:
            manifest[folder.name] = urls
        else:
            out.rmdir()
    (TARGET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    files = sum(len(v) for v in manifest.values())
    size = sum(p.stat().st_size for p in TARGET.rglob("*.webp") if not p.name.endswith("-sm.webp")) / 1024 / 1024
    small = [p.stat().st_size for p in TARGET.rglob("*-sm.webp")]
    print(f"{files} photos for {len(manifest)} products in {TARGET.relative_to(ROOT)} ({size:.1f} MB), "
          f"small copies {sum(small) / 1024 / 1024:.1f} MB (~{sum(small) // max(1, len(small)) // 1024} KB each), "
          f"{skipped} too small skipped")


if __name__ == "__main__":
    main()
