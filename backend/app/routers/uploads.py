"""Picture uploads for products and news.

POST /api/admin/uploads with the file itself as the request body (no multipart form):
    Content-Type: image/png | image/jpeg | image/webp | image/gif
Answer: {"url": "/uploads/<random name>.png"} — a path on the site, ready for image_url.

The type is checked by the first bytes of the file, not by the header or the name, and SVG is not
accepted (it can carry scripts). Files go to UPLOAD_DIR; nginx serves that folder at /uploads/.
"""

import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.config import settings
from app.deps import get_current_user
from app.i18n import t
from app.models import User
from app.permissions import has_permission

router = APIRouter(prefix="/api/admin/uploads", tags=["admin"])

MAX_BYTES = 5 * 1024 * 1024
# first bytes of a file -> extension
SIGNATURES = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
}


def image_type(data: bytes) -> str | None:
    for signature, extension in SIGNATURES.items():
        if data.startswith(signature):
            return extension
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def can_upload(user: User = Depends(get_current_user)) -> User:
    """Those who edit products or news may upload pictures for them."""
    if not (has_permission(user, "products.manage") or has_permission(user, "content.manage")):
        raise HTTPException(status.HTTP_403_FORBIDDEN, t("errors.forbidden"))
    return user


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_image(request: Request, _: User = Depends(can_upload)) -> dict[str, str]:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, t("errors.upload_too_big", mb=MAX_BYTES // 1024 // 1024))
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_BYTES:  # the header can lie: count what really comes
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, t("errors.upload_too_big", mb=MAX_BYTES // 1024 // 1024))
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, t("errors.upload_empty"))
    extension = image_type(bytes(data[:16]))
    if extension is None:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, t("errors.upload_type"))

    folder = Path(settings.upload_dir)
    folder.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(12)}.{extension}"  # random name: no paths or names from the user
    (folder / name).write_bytes(data)
    return {"url": f"/uploads/{name}"}
