"""Backups in the admin panel: make, list, download, upload, restore, delete; auto backup settings.

Everything needs the `system.backup` permission: only the admin has it. The work itself is in app/backups.py.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import backups
from app.database import get_db
from app.deps import require_permission
from app.i18n import t

router = APIRouter(prefix="/api/admin/backups", tags=["Backups"])
can_backup = require_permission("system.backup")


class AutoBackupIn(BaseModel):
    enabled: bool | None = None
    every_hours: int | None = Field(default=None, ge=1, le=24 * 30)
    keep: int | None = Field(default=None, ge=1, le=100)


def _fail(error: backups.BackupError, code: int = status.HTTP_400_BAD_REQUEST):
    if error.key == "errors.backup_not_found":
        code = status.HTTP_404_NOT_FOUND
    elif error.key == "errors.upload_too_big":
        code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    raise HTTPException(code, t(error.key, **error.params))


@router.get("", dependencies=[Depends(can_backup)])
def list_backups():
    return {"items": backups.list_backups(), "auto": backups.auto_settings()}


@router.post("", status_code=status.HTTP_201_CREATED, dependencies=[Depends(can_backup)])
def make_backup(db: Session = Depends(get_db)):
    return backups.create(db)


@router.post("/upload", status_code=status.HTTP_201_CREATED, dependencies=[Depends(can_backup)])
async def upload_backup(request: Request):
    """A backup file from the computer: the .zip itself is the request body. It is only saved here;
    restoring is a separate step."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > backups.MAX_UPLOAD_BYTES:
            break
    try:
        return backups.save_uploaded(bytes(data))
    except backups.BackupError as error:
        _fail(error)


@router.get("/{name}/download", dependencies=[Depends(can_backup)])
def download_backup(name: str):
    try:
        path = backups.path_of(name)
    except backups.BackupError as error:
        _fail(error)
    return FileResponse(path, media_type="application/zip", filename=name)


@router.post("/{name}/restore", dependencies=[Depends(can_backup)])
def restore_backup(name: str, db: Session = Depends(get_db)):
    """Replaces ALL data of the store with the backup. Make a fresh backup first if unsure."""
    try:
        return backups.restore(db, name)
    except backups.BackupError as error:
        db.rollback()
        _fail(error)


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(can_backup)])
def delete_backup(name: str):
    try:
        backups.delete(name)
    except backups.BackupError as error:
        _fail(error)


@router.patch("/auto", dependencies=[Depends(can_backup)])
def auto_backup(data: AutoBackupIn):
    """Auto backup: on/off, how often (hours) and how many auto copies to keep. Off by default."""
    return backups.save_auto_settings(data.model_dump(exclude_none=True))
