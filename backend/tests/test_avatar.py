"""Own photo of a user (POST/DELETE /api/auth/me/avatar)."""

import pytest

from app.config import settings

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


@pytest.fixture(autouse=True)
def upload_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    return tmp_path


def files(folder):
    path = folder / "avatars"
    return sorted(p.name for p in path.iterdir()) if path.exists() else []


@pytest.mark.parametrize("role", ["client", "engineer", "admin"])
def test_anyone_signed_in_sets_a_photo(client, make_user, upload_dir, role):
    _, headers = make_user(role)
    assert client.get("/api/auth/me", headers=headers).json()["avatar_url"] is None
    response = client.post("/api/auth/me/avatar", content=PNG, headers=headers)
    assert response.status_code == 200
    url = response.json()["avatar_url"]
    assert url.startswith("/uploads/avatars/") and url.endswith(".png")
    assert client.get("/api/auth/me", headers=headers).json()["avatar_url"] == url
    assert files(upload_dir) == [url.rsplit("/", 1)[1]]


def test_new_photo_replaces_the_old_file(client, make_user, upload_dir):
    _, headers = make_user("client")
    first = client.post("/api/auth/me/avatar", content=PNG, headers=headers).json()["avatar_url"]
    second = client.post("/api/auth/me/avatar", content=JPEG, headers=headers).json()["avatar_url"]
    assert first != second and second.endswith(".jpg")
    assert files(upload_dir) == [second.rsplit("/", 1)[1]]  # the old file is gone


def test_remove_photo(client, make_user, upload_dir):
    _, headers = make_user("client")
    client.post("/api/auth/me/avatar", content=PNG, headers=headers)
    response = client.delete("/api/auth/me/avatar", headers=headers)
    assert response.status_code == 200
    assert response.json()["avatar_url"] is None
    assert files(upload_dir) == []
    # removing again is fine
    assert client.delete("/api/auth/me/avatar", headers=headers).status_code == 200


def test_not_a_picture_is_rejected(client, make_user, upload_dir):
    _, headers = make_user("client")
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"
    assert client.post("/api/auth/me/avatar", content=svg, headers=headers).status_code == 415
    assert client.get("/api/auth/me", headers=headers).json()["avatar_url"] is None
    assert files(upload_dir) == []


def test_guest_has_no_photo(client):
    assert client.post("/api/auth/me/avatar", content=PNG).status_code == 401
    assert client.delete("/api/auth/me/avatar").status_code == 401


def test_photo_can_not_be_set_through_the_profile(client, make_user):
    _, headers = make_user("client")
    client.patch("/api/auth/me", json={"name": "Иван", "avatar_url": "https://evil.example/x.png"}, headers=headers)
    assert client.get("/api/auth/me", headers=headers).json()["avatar_url"] is None
