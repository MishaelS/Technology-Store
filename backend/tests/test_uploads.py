"""Picture uploads (routers/uploads.py)."""

import pytest

from app.config import settings
from app.routers.uploads import MAX_BYTES

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 64


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    """Uploads of the tests go to a temporary folder, not to the project's uploads/."""
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("data, extension", [(PNG, "png"), (JPEG, "jpg"), (WEBP, "webp"), (b"GIF89a" + b"\x00" * 16, "gif")])
def test_manager_uploads_a_picture(client, make_user, upload_dir, data, extension):
    _, headers = make_user("manager")
    response = client.post("/api/admin/uploads", content=data, headers={**headers, "Content-Type": "image/png"})
    assert response.status_code == 201
    url = response.json()["url"]
    assert url.startswith("/uploads/") and url.endswith(f".{extension}")
    assert (upload_dir / url.rsplit("/", 1)[1]).read_bytes() == data


def test_uploaded_url_is_accepted_as_product_image(client, make_user, product):
    _, headers = make_user("manager")
    url = client.post("/api/admin/uploads", content=PNG, headers=headers).json()["url"]
    item = product("Cougar GEX 650W")
    response = client.patch(f"/api/admin/products/{item.id}", json={"image_url": url}, headers=headers)
    assert response.status_code == 200
    assert response.json()["image_url"] == url


@pytest.mark.parametrize("data", [
    b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>",  # SVG can carry scripts
    b"just some text",
    b"%PDF-1.7",
])
def test_not_a_picture_is_rejected(client, make_user, upload_dir, data):
    _, headers = make_user("manager")
    response = client.post("/api/admin/uploads", content=data, headers={**headers, "Content-Type": "image/png"})
    assert response.status_code == 415
    assert "detail" in response.json()
    assert not list(upload_dir.iterdir())


def test_empty_and_too_big_files(client, make_user):
    _, headers = make_user("manager")
    assert client.post("/api/admin/uploads", content=b"", headers=headers).status_code == 400
    too_big = PNG + b"\x00" * MAX_BYTES
    assert client.post("/api/admin/uploads", content=too_big, headers=headers).status_code == 413


@pytest.mark.parametrize("role, code", [("client", 403), ("engineer", 403), ("employee", 201), ("admin", 201)])
def test_who_can_upload(client, make_user, role, code):
    _, headers = make_user(role)
    assert client.post("/api/admin/uploads", content=PNG, headers=headers).status_code == code


def test_guest_cannot_upload(client):
    assert client.post("/api/admin/uploads", content=PNG).status_code == 401
