"""Backups (app/backups.py, routers/backups.py)."""

import io
import json
import zipfile
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import backups
from app.config import settings
from app.models import News, Product, User


@pytest.fixture(autouse=True)
def folders(tmp_path, monkeypatch):
    """Backups and uploads of the tests live in a temporary folder."""
    monkeypatch.setattr(settings, "backup_dir", str(tmp_path / "backups"))
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path / "uploads"))
    (tmp_path / "uploads" / "avatars").mkdir(parents=True)
    (tmp_path / "uploads" / "avatars" / "me.png").write_bytes(b"\x89PNG\r\n\x1a\nphoto")
    return tmp_path


@pytest.fixture
def headers(make_user):
    return make_user("admin")[1]


def test_make_backup(client, headers, db, folders):
    response = client.post("/api/admin/backups", headers=headers)
    assert response.status_code == 201
    made = response.json()
    assert made["name"].startswith("backup-") and made["ok"] and made["uploads"] == 1
    with zipfile.ZipFile(folders / "backups" / made["name"]) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        data = json.loads(archive.read("data.json"))
        assert archive.read("uploads/avatars/me.png") == b"\x89PNG\r\n\x1a\nphoto"
    assert manifest["tables"]["products"] == db.scalar(select(func.count(Product.id)))
    assert len(data["users"]) == db.scalar(select(func.count(User.id)))
    listed = client.get("/api/admin/backups", headers=headers).json()
    assert [b["name"] for b in listed["items"]] == [made["name"]]
    assert listed["auto"]["enabled"] is False  # auto backups are off by default


def test_restore_brings_everything_back(client, headers, db, folders):
    name = client.post("/api/admin/backups", headers=headers).json()["name"]
    products = db.scalar(select(func.count(Product.id)))
    # break things: delete news, change a price, add a product, lose the pictures
    first = db.scalars(select(Product).order_by(Product.id)).first()
    price = first.price
    first.price = 1
    db.query(News).delete()
    db.commit()
    (folders / "uploads" / "avatars" / "me.png").unlink()
    (folders / "uploads" / "stray.png").write_bytes(b"x")

    response = client.post(f"/api/admin/backups/{name}/restore", headers=headers)
    assert response.status_code == 200
    db.expire_all()
    assert db.scalar(select(func.count(Product.id))) == products
    assert db.get(Product, first.id).price == price
    assert db.scalar(select(func.count(News.id))) > 0
    assert (folders / "uploads" / "avatars" / "me.png").exists()
    assert not (folders / "uploads" / "stray.png").exists()
    # new rows still get free ids after the restore
    news = News(title="После восстановления", text="Текст", type="news")
    db.add(news)
    db.commit()
    assert news.id > 0


def test_download_and_upload(client, headers, folders):
    name = client.post("/api/admin/backups", headers=headers).json()["name"]
    file = client.get(f"/api/admin/backups/{name}/download", headers=headers)
    assert file.status_code == 200 and file.headers["content-type"] == "application/zip"
    uploaded = client.post("/api/admin/backups/upload", content=file.content, headers=headers)
    assert uploaded.status_code == 201
    assert uploaded.json()["name"].startswith("upload-") and uploaded.json()["ok"]


@pytest.mark.parametrize("content", [b"", b"not a zip at all", None])
def test_bad_uploads_are_rejected(client, headers, folders, content):
    if content is None:  # a zip, but not ours
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("hello.txt", "hi")
        content = buffer.getvalue()
    response = client.post("/api/admin/backups/upload", content=content, headers=headers)
    assert response.status_code == 400
    assert "detail" in response.json()
    assert backups.list_backups() == []


def test_backup_of_another_database_version_is_not_restored(client, headers, folders):
    name = client.post("/api/admin/backups", headers=headers).json()["name"]
    path = folders / "backups" / name
    with zipfile.ZipFile(path) as archive:
        files = {n: archive.read(n) for n in archive.namelist()}
    manifest = json.loads(files["manifest.json"])
    manifest["migration"] = "0000old"
    files["manifest.json"] = json.dumps(manifest).encode()
    with zipfile.ZipFile(path, "w") as archive:
        for n, content in files.items():
            archive.writestr(n, content)
    response = client.post(f"/api/admin/backups/{name}/restore", headers=headers)
    assert response.status_code == 400
    assert "0000old" in response.json()["detail"]


@pytest.mark.parametrize("name", ["../../etc/passwd", "backup-x.zip", "auto.json", "backup-20260101-000000.zip"])
def test_unknown_names(client, headers, name):
    assert client.get(f"/api/admin/backups/{name}/download", headers=headers).status_code in (404, 405)
    assert client.delete(f"/api/admin/backups/{name}", headers=headers).status_code in (404, 405)


def test_delete(client, headers, folders):
    name = client.post("/api/admin/backups", headers=headers).json()["name"]
    assert client.delete(f"/api/admin/backups/{name}", headers=headers).status_code == 204
    assert client.get("/api/admin/backups", headers=headers).json()["items"] == []


# backups are for the admin only
@pytest.mark.parametrize("role, code", [("client", 403), ("employee", 403), ("engineer", 403), ("manager", 403),
                                        ("senior_engineer", 403), ("admin", 200)])
def test_who_can_use_backups(client, make_user, role, code):
    _, headers = make_user(role)
    assert client.get("/api/admin/backups", headers=headers).status_code == code


def test_auto_backup_is_off_until_enabled_and_keeps_the_newest(client, headers, db, folders):
    assert backups.run_auto(db) is None  # off by default: nothing happens
    changed = client.patch("/api/admin/backups/auto", json={"enabled": True, "every_hours": 6, "keep": 2}, headers=headers)
    assert changed.json() == {**changed.json(), "enabled": True, "every_hours": 6, "keep": 2}
    first = backups.run_auto(db)
    assert first is not None
    made = [first["name"]]
    assert backups.run_auto(db) is None  # not due again yet
    for _ in range(2):  # pretend the time has come
        backups.save_auto_settings({"last_run": (datetime.now(timezone.utc) - timedelta(hours=7)).isoformat()})
        again = backups.run_auto(db)
        assert again is not None
        made.append(again["name"])
    autos = [b["name"] for b in backups.list_backups() if b["kind"] == "auto"]
    assert len(autos) == 2 and made[0] not in autos  # only the newest 2 are kept
    assert client.patch("/api/admin/backups/auto", json={"keep": 0}, headers=headers).status_code == 422
