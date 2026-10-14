"""Upload validation and storage.

Two hardening rules beyond the size cap:

  1. Content type is decided by SNIFFING the file's magic bytes, not by
     trusting the client-supplied Content-Type header. Uploading `evil.html`
     with `Content-Type: image/png` used to pass, land as a servable file,
     and become stored XSS. Now the bytes must actually be a PNG.

  2. The stored extension must belong to the sniffed family's allowlist, so a
     PDF can't be stored as `.html`.

Filenames are always replaced with a uuid, so the client filename never
touches the path (no traversal via `..`).
"""
import os
import uuid
from pathlib import Path

import aiofiles
import structlog
from fastapi import UploadFile

from app.core.config import settings
from app.core.exceptions import BadRequestException

logger = structlog.get_logger()


# Magic-byte families. Each entry maps a signature to the content types and
# file extensions we accept for it. OOXML (docx/xlsx/pptx) and legacy .doc are
# zip / OLE2 containers respectively, so magic bytes identify the *family*;
# the declared content type must then be one this family allows.
_SIGNATURES: list[dict] = [
    {
        "name": "pdf",
        "magic": [b"%PDF-"],
        "content_types": {"application/pdf"},
        "extensions": {".pdf"},
    },
    {
        "name": "png",
        "magic": [b"\x89PNG\r\n\x1a\n"],
        "content_types": {"image/png"},
        "extensions": {".png"},
    },
    {
        "name": "jpeg",
        "magic": [b"\xff\xd8\xff"],
        "content_types": {"image/jpeg"},
        "extensions": {".jpg", ".jpeg"},
    },
    {
        # Zip container → modern Office formats (docx/xlsx/pptx).
        "name": "ooxml",
        "magic": [b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"],
        "content_types": {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        },
        "extensions": {".docx", ".xlsx", ".pptx"},
    },
    {
        # OLE2 compound file → legacy .doc/.xls/.ppt.
        "name": "ole",
        "magic": [b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"],
        "content_types": {"application/msword"},
        "extensions": {".doc"},
    },
]


def _match_signature(head: bytes) -> dict | None:
    for sig in _SIGNATURES:
        if any(head.startswith(m) for m in sig["magic"]):
            return sig
    return None


def _validate_bytes_and_name(content: bytes, filename: str | None, declared_ct: str | None) -> str:
    """Return the sanitised extension to store, or raise BadRequestException.

    The returned extension is drawn from the sniffed family's allowlist, not
    from the client filename, so it can't be spoofed.
    """
    sig = _match_signature(content[:16])
    if sig is None:
        raise BadRequestException(
            code="INVALID_FILE_TYPE",
            message="File contents are not an accepted type (PDF, Office document, PNG, or JPEG)",
        )

    # The sniffed family must be one the deployment allows at all.
    if not (sig["content_types"] & set(settings.ALLOWED_FILE_TYPES)):
        raise BadRequestException(
            code="INVALID_FILE_TYPE",
            message=f"File type '{sig['name']}' is not allowed",
            details={"allowed_types": settings.ALLOWED_FILE_TYPES},
        )

    # Prefer the client's extension when it's valid for the family (keeps
    # .xlsx vs .docx distinct); otherwise fall back to the family's first.
    client_ext = Path(filename or "").suffix.lower()
    if client_ext in sig["extensions"]:
        return client_ext
    return sorted(sig["extensions"])[0]


# The content type we store is derived from the sniffed extension, never the
# client's header. The header is attacker-controlled free text: a 150-char
# multipart Content-Type used to overflow the String(100) column and 500 the
# request, and even a short one could lie about what the bytes are.
_EXTENSION_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".doc": "application/msword",
}

# Every file_name column is String(500); keep well inside it so a pathological
# client filename is shortened rather than failing the INSERT with a 500.
MAX_DISPLAY_NAME_LENGTH = 255


def _display_name(filename: str | None, ext: str) -> str:
    """The client's filename, for display only (it never touches the path),
    cut to MAX_DISPLAY_NAME_LENGTH while keeping its extension so the
    downloaded file still opens with the right application."""
    name = (filename or "").strip() or f"file{ext}"
    if len(name) <= MAX_DISPLAY_NAME_LENGTH:
        return name
    suffix = Path(name).suffix
    # A "suffix" that is itself enormous is not a real extension; fall back
    # to the sniffed one rather than keep 200 chars of junk.
    if not suffix or len(suffix) > 10:
        suffix = ext
    stem = name[: len(name) - len(Path(name).suffix)] if Path(name).suffix else name
    return stem[: MAX_DISPLAY_NAME_LENGTH - len(suffix)] + suffix


def delete_upload(file_url: str | None) -> None:
    """Best-effort removal of a file save_upload wrote, for callers whose
    request fails *after* the bytes hit disk — otherwise every rejected
    upload leaves an orphan nobody references. Confined to UPLOAD_DIR the
    same way the download route is, so a bad value can't delete elsewhere."""
    if not file_url or not file_url.startswith("/uploads/"):
        return
    root = Path(settings.UPLOAD_DIR).resolve()
    candidate = (root / file_url[len("/uploads/"):]).resolve()
    if not candidate.is_relative_to(root):
        return
    try:
        candidate.unlink(missing_ok=True)
    except OSError:
        logger.warning("orphan_upload_cleanup_failed", path=str(candidate))



async def save_upload(
    file: UploadFile,
    subdirectory: str = "general",
) -> dict:
    # Read at most max+1 bytes so an oversized upload is rejected without
    # pulling the whole thing into memory.
    max_bytes = settings.max_file_size_bytes
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise BadRequestException(
            code="FILE_TOO_LARGE",
            message=f"File size exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
        )
    if not content:
        raise BadRequestException(code="EMPTY_FILE", message="Uploaded file is empty")

    ext = _validate_bytes_and_name(content, file.filename, file.content_type)

    # Guard against a hostile subdirectory value (callers build it from ids,
    # but never trust) — collapse to a safe relative segment.
    safe_subdir = os.path.normpath(subdirectory).replace("\\", "/").lstrip("./")
    if safe_subdir.startswith("..") or os.path.isabs(safe_subdir):
        safe_subdir = "general"

    upload_dir = Path(settings.UPLOAD_DIR) / safe_subdir
    upload_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = upload_dir / unique_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    relative_path = f"{safe_subdir}/{unique_name}"
    logger.info("file_uploaded", path=relative_path, size=len(content), sniffed_ext=ext)

    return {
        "file_name": _display_name(file.filename, ext),
        # Stored as the canonical relative path. Responses convert this to a
        # signed, expiring download URL via utils.file_tokens.signed_file_url.
        "file_url": f"/uploads/{relative_path}",
        "file_size": len(content),
        "content_type": _EXTENSION_CONTENT_TYPES.get(ext, "application/octet-stream"),
    }


