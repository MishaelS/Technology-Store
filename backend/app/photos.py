"""Real product photos, or a placeholder where there are none. Run: ./run.sh photos

Photos come from resources/photos/web (made by scripts/prepare_product_photos.py), listed in its manifest.json
by product: the first one becomes the main photo (image_url), the others the extra ones (images, up to 10).
A product without real photos gets the placeholder: the drawn picture with its category icon, brand and
main spec (resources/demo/products/<name>.svg) and no extra photos.

Only pictures this command or the demo set are replaced: a photo uploaded by hand in the admin panel
(/uploads/... or any other link) is never touched. Safe to run again after adding photos.
"""

import json
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.demo import picture, slug
from app.models import Product
from app.schemas import MAX_PRODUCT_IMAGES

RESOURCES = Path(settings.locales_dir).parent  # <repo>/resources locally, /resources in Docker
MANIFEST = RESOURCES / "photos" / "web" / "manifest.json"
OURS = ("/resources/demo/", "/resources/photos/")  # pictures that may be replaced


def load_manifest() -> dict[str, list[str]]:
    try:
        return json.loads(MANIFEST.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def apply_photos(db: Session, commit: bool = True) -> tuple[int, int]:
    """Gives products their photos or the placeholder. Returns (with photos, with placeholder).
    commit=False: the caller saves (the demo saves everything at once at its end)."""
    photos = load_manifest()
    real = placeholder = 0
    for product in db.scalars(select(Product)):
        if product.image_url and not product.image_url.startswith(OURS):
            continue  # uploaded or linked by hand: the admin's choice stays
        own = photos.get(slug(product.name)) or []
        if own:
            product.image_url = own[0]
            product.images = own[1:MAX_PRODUCT_IMAGES + 1]
            real += 1
        else:
            product.image_url = picture(product.name)
            product.images = []
            placeholder += 1
    if commit:
        db.commit()
    else:
        db.flush()
    return real, placeholder


def main() -> None:
    if not MANIFEST.exists():
        print("photos: no resources/photos/web/manifest.json — run: python3 backend/scripts/prepare_product_photos.py")
    with SessionLocal() as db:
        real, placeholder = apply_photos(db)
    print(f"photos: {real} products with real photos, {placeholder} with the placeholder")


if __name__ == "__main__":
    main()
