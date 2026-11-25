"""Backups of the store: the whole database and the uploaded pictures in one .zip file.

Inside a backup:
    manifest.json   what it is: app version, database migration, when, how many rows per table
    data.json       every table as a list of rows (in an order where foreign keys come first)
    uploads/...     pictures uploaded in the admin panel and avatars

A backup is plain JSON, so it doesn't need pg_dump in the container and can be read by a person.
It can be restored only into a database with the same migration (the same set of tables and columns).

Backups are kept in BACKUP_DIR. Auto backups (off by default) are made by a background task in main.py
with the settings from auto.json in the same folder (changed in the admin panel).
"""

import json
import re
import shutil
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import DateTime, Date, Integer, select, text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (all tables must be known to Base.metadata)
from app.config import settings
from app.database import Base

APP_ID = "technology-store"
NAME = re.compile(r"^(backup|auto|upload)-\d{8}-\d{6}(-\d+)?\.zip$")
MAX_UPLOAD_BYTES = 500 * 1024 * 1024
AUTO_DEFAULTS = {"enabled": False, "every_hours": 24, "keep": 7, "last_run": None}


class BackupError(ValueError):
    """A backup can't be made or restored; the message is a translation key."""

    def __init__(self, key: str, **params):
        super().__init__(key)
        self.key = key
        self.params = params


def folder() -> Path:
    path = Path(settings.backup_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def path_of(name: str) -> Path:
    """Path of a backup by its name; only names made by this module, so no "../" tricks."""
    if not NAME.match(name):
        raise BackupError("errors.backup_not_found")
    path = folder() / name
    if not path.is_file():
        raise BackupError("errors.backup_not_found")
    return path


def new_name(kind: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    name, n = f"{kind}-{stamp}.zip", 1
    while (folder() / name).exists():  # two backups in the same second
        n += 1
        name = f"{kind}-{stamp}-{n}.zip"
    return name


def current_migration(db: Session) -> str | None:
    return db.scalar(text("SELECT version_num FROM alembic_version"))


# ---------- making a backup ----------

def _to_json(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"can't save {type(value).__name__}")


def create(db: Session, kind: str = "backup") -> dict:
    """Writes a new backup file and returns its description (like list_backups() items)."""
    tables = Base.metadata.sorted_tables
    data = {table.name: [dict(row) for row in db.execute(select(table)).mappings()] for table in tables}
    uploads = Path(settings.upload_dir)
    upload_files = [p for p in uploads.rglob("*") if p.is_file()] if uploads.exists() else []
    manifest = {
        "app": APP_ID,
        "migration": current_migration(db),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": kind,
        "tables": {name: len(rows) for name, rows in data.items()},
        "uploads": len(upload_files),
    }
    name = new_name(kind)
    target = folder() / name
    partial = target.with_suffix(".part")  # a half-written file never looks like a backup
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("data.json", json.dumps(data, ensure_ascii=False, default=_to_json))
        for file in upload_files:
            archive.write(file, f"uploads/{file.relative_to(uploads).as_posix()}")
    partial.rename(target)
    return describe(target)


# ---------- reading ----------

def read_manifest(path: Path) -> dict:
    try:
        with zipfile.ZipFile(path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            archive.getinfo("data.json")
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, OSError):
        raise BackupError("errors.backup_broken")
    if not isinstance(manifest, dict) or manifest.get("app") != APP_ID:
        raise BackupError("errors.backup_broken")
    return manifest


def describe(path: Path) -> dict:
    try:
        manifest = read_manifest(path)
    except BackupError:
        manifest = {}
    return {
        "name": path.name,
        "size": path.stat().st_size,
        "created_at": manifest.get("created_at") or datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        "kind": path.name.split("-", 1)[0],
        "migration": manifest.get("migration"),
        "rows": sum((manifest.get("tables") or {}).values()),
        "uploads": manifest.get("uploads", 0),
        "ok": bool(manifest),
    }


def list_backups() -> list[dict]:
    files = [p for p in folder().iterdir() if p.is_file() and NAME.match(p.name)]
    return sorted((describe(p) for p in files), key=lambda b: b["created_at"], reverse=True)


def save_uploaded(data: bytes) -> dict:
    """Keeps a backup file sent by the user (checked first) under a new name."""
    if not data:
        raise BackupError("errors.upload_empty")
    if len(data) > MAX_UPLOAD_BYTES:
        raise BackupError("errors.upload_too_big", mb=MAX_UPLOAD_BYTES // 1024 // 1024)
    target = folder() / new_name("upload")
    partial = target.with_suffix(".part")
    partial.write_bytes(data)
    try:
        read_manifest(partial)
    except BackupError:
        partial.unlink(missing_ok=True)
        raise
    partial.rename(target)
    return describe(target)


def delete(name: str) -> None:
    path_of(name).unlink()


# ---------- restoring ----------

def _from_json(column, value):
    if value is None:
        return None
    if isinstance(column.type, DateTime):
        return datetime.fromisoformat(value)
    if isinstance(column.type, Date):
        return date.fromisoformat(value)
    return value


def restore(db: Session, name: str) -> dict:
    """Replaces everything in the database (and the uploaded pictures) with the backup.

    All in one transaction: if anything goes wrong, the database stays as it was.
    """
    path = path_of(name)
    manifest = read_manifest(path)
    if manifest.get("migration") != current_migration(db):
        raise BackupError("errors.backup_other_version", backup=manifest.get("migration") or "?",
                          current=current_migration(db) or "?")
    with zipfile.ZipFile(path) as archive:
        data = json.loads(archive.read("data.json"))
        upload_entries = [i for i in archive.infolist() if i.filename.startswith("uploads/") and not i.is_dir()]
        for info in upload_entries:  # paths inside the zip must stay inside uploads/
            relative = Path(info.filename[len("uploads/"):])
            if relative.is_absolute() or ".." in relative.parts:
                raise BackupError("errors.backup_broken")
        uploads = {info.filename[len("uploads/"):]: archive.read(info) for info in upload_entries}

    tables = Base.metadata.sorted_tables
    db.execute(text("TRUNCATE TABLE " + ", ".join(f'"{t.name}"' for t in tables) + " RESTART IDENTITY CASCADE"))
    for table in tables:
        rows = data.get(table.name) or []
        known = {c.name: c for c in table.columns}
        clean = [{key: _from_json(known[key], value) for key, value in row.items() if key in known} for row in rows]
        if clean:
            db.execute(table.insert(), clean)
        # the next new row gets the next free id
        id_column = known.get("id")
        if id_column is not None and isinstance(id_column.type, Integer):
            db.execute(text(
                f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{table.name}\"), 1), "
                f"(SELECT COUNT(*) FROM \"{table.name}\") > 0)"
            ))
    db.commit()

    # pictures: the folder becomes exactly what the backup had
    target = Path(settings.upload_dir)
    if target.exists():
        for child in target.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    for relative, content in uploads.items():
        file = target / relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
    return {"name": name, "rows": sum(len(v or []) for v in data.values()), "uploads": len(uploads)}


# ---------- auto backups ----------

def auto_settings() -> dict:
    try:
        stored = json.loads((folder() / "auto.json").read_text())
    except (OSError, json.JSONDecodeError):
        stored = {}
    return {**AUTO_DEFAULTS, **{k: v for k, v in stored.items() if k in AUTO_DEFAULTS}}


def save_auto_settings(changes: dict) -> dict:
    current = {**auto_settings(), **changes}
    (folder() / "auto.json").write_text(json.dumps(current, indent=2))
    return current


def auto_due(now: datetime | None = None) -> bool:
    config = auto_settings()
    if not config["enabled"]:
        return False
    if not config["last_run"]:
        return True
    now = now or datetime.now(timezone.utc)
    return (now - datetime.fromisoformat(config["last_run"])).total_seconds() >= config["every_hours"] * 3600


def run_auto(db: Session) -> dict | None:
    """Makes an auto backup if it's time, and keeps only the newest `keep` of them."""
    if not auto_due():
        return None
    made = create(db, "auto")
    save_auto_settings({"last_run": made["created_at"]})
    keep = auto_settings()["keep"]
    autos = [b for b in list_backups() if b["kind"] == "auto"]
    for old in autos[keep:]:
        (folder() / old["name"]).unlink(missing_ok=True)
    return made
