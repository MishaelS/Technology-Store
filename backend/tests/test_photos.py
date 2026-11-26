"""Real product photos or the placeholder (app/photos.py)."""

import json

import pytest
from sqlalchemy import select

from app import photos
from app.demo import picture
from app.models import Product


@pytest.fixture
def manifest(tmp_path, monkeypatch):
    def write(data):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(data))
        monkeypatch.setattr(photos, "MANIFEST", path)
    return write


def test_real_photos_and_placeholders(db, product, manifest):
    psu, case = product("Cougar GEX 650W"), product("NZXT H1 V2")
    web = "/resources/photos/web/cougar-gex-650w"
    manifest({"cougar-gex-650w": [f"{web}/01.webp", f"{web}/02.webp", f"{web}/03.webp"]})
    photos.apply_photos(db)
    assert psu.image_url == f"{web}/01.webp"
    assert psu.images == [f"{web}/02.webp", f"{web}/03.webp"]
    assert case.image_url == picture("NZXT H1 V2") and case.images == []  # no photos: the placeholder


def test_photo_set_by_hand_stays(db, product, manifest):
    psu = product("Cougar GEX 650W")
    psu.image_url, psu.images = "/uploads/mine.png", ["/uploads/side.png"]
    db.commit()
    manifest({"cougar-gex-650w": ["/resources/photos/web/cougar-gex-650w/01.webp"]})
    photos.apply_photos(db)
    assert psu.image_url == "/uploads/mine.png" and psu.images == ["/uploads/side.png"]


def test_running_again_follows_the_manifest(db, product, manifest):
    psu = product("Cougar GEX 650W")
    manifest({"cougar-gex-650w": ["/resources/photos/web/cougar-gex-650w/01.webp"]})
    photos.apply_photos(db)
    manifest({})  # the photos were removed
    photos.apply_photos(db)
    assert psu.image_url == picture("Cougar GEX 650W") and psu.images == []


def test_no_manifest_means_placeholders_for_all(db, manifest, monkeypatch, tmp_path):
    monkeypatch.setattr(photos, "MANIFEST", tmp_path / "missing.json")
    real, placeholder = photos.apply_photos(db)
    assert real == 0 and placeholder == len(db.scalars(select(Product)).all())
