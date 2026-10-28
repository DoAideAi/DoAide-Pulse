"""Image upload and serving for cover images and marketing galleries."""
from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path as FilePath

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import settings
from app.deps import get_current_user
from app.models.user import User
from app.ratelimit import account_key, limiter
from app.schemas.errors import AUTHENTICATED, errors

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"])

UPLOAD_LIMIT = "120/hour"

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


class UploadOut(BaseModel):
    url: str
    filename: str
    size: int


def _upload_dir() -> FilePath:
    base = FilePath(settings.upload_dir)
    if not base.is_absolute():
        base = FilePath(__file__).resolve().parent.parent.parent / base
    base.mkdir(parents=True, exist_ok=True)
    return base


_CHUNK = 256 * 1024
_SNIFF_BYTES = 12


def sniff_image_type(head: bytes) -> str | None:
    """The image MIME type a file's leading bytes declare, or ``None``."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def _ext_from_content_type(ct: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
    }.get(ct, "")


@router.post(
    "",
    response_model=UploadOut,
    status_code=status.HTTP_201_CREATED,
    summary="Upload an image",
    responses=errors(
        status.HTTP_400_BAD_REQUEST,
        *AUTHENTICATED,
        status.HTTP_429_TOO_MANY_REQUESTS,
    ),
)
@limiter.limit(UPLOAD_LIMIT, key_func=account_key)
async def upload_image(
    request: Request,
    response: Response,
    file: UploadFile,
    user: User = Depends(get_current_user),
) -> UploadOut:
    """Accept an image file and persist it to the upload directory.

    The type is decided by the file's own leading bytes, not by the
    ``Content-Type`` the client sent — that header is whatever the browser (or a
    script) says it is, so a renamed HTML or SVG file used to be stored and
    served back under an image extension. The body is streamed to disk in
    chunks and refused as soon as it passes the size limit, instead of being
    read whole into memory first.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. "
            f"Allowed: jpg, png, webp, gif.",
        )
    limit = settings.max_upload_bytes
    base = _upload_dir()
    tmp = base / f".upload-{uuid.uuid4().hex}.part"
    digest = hashlib.sha256()
    size = 0
    head = b""
    try:
        with tmp.open("wb") as out:
            while chunk := await file.read(_CHUNK):
                size += len(chunk)
                if size > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"File too large (max {limit // (1024 * 1024)} MB).",
                    )
                if len(head) < _SNIFF_BYTES:
                    head += chunk[: _SNIFF_BYTES - len(head)]
                digest.update(chunk)
                out.write(chunk)
        detected = sniff_image_type(head)
        if detected is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="That file is not a JPG, PNG, WebP or GIF image.",
            )
        ext = _ext_from_content_type(detected)
        filename = f"{uuid.uuid4().hex[:8]}_{digest.hexdigest()[:12]}{ext}"
        tmp.replace(base / filename)
    finally:
        tmp.unlink(missing_ok=True)
    # Absolute, because the content schema refuses relative image URLs (the
    # publishing platforms fetch them from their own servers). A relative path
    # here made every auto-save 422 once an uploaded image was in the draft.
    url = f"{settings.api_base_url}{settings.api_v1_prefix}/uploads/{filename}"
    return UploadOut(url=url, filename=filename, size=size)


@router.get(
    "/{filename}",
    summary="Serve an uploaded image",
    responses=errors(
        status.HTTP_400_BAD_REQUEST,
        status.HTTP_404_NOT_FOUND,
        status.HTTP_429_TOO_MANY_REQUESTS,
    ),
)
@limiter.limit(settings.rate_limit_public_read)
async def serve_image(
    request: Request,
    response: Response,
    filename: str = Path(max_length=255),
) -> FileResponse:
    """Return a previously uploaded image by filename."""
    if "/" in filename or "\\" in filename or ".." in filename or "\x00" in filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not contain path separators, '..', or null bytes.",
        )

    base = _upload_dir()
    path = base / filename
    if not path.resolve().parent == base.resolve():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename must not contain path separators or '..'.",
        )
    if not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Image not found."
        )

    ext = path.suffix.lower()
    media_types = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
    }
    media_type = media_types.get(ext, "application/octet-stream")

    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
