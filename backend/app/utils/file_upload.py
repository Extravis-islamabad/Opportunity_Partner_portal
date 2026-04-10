import os
import uuid
import aiofiles
from pathlib import Path
from fastapi import UploadFile
from typing import Optional
import structlog

from app.core.config import settings
from app.core.exceptions import BadRequestException

logger = structlog.get_logger()


def validate_file(file: UploadFile) -> None:
    if file.content_type not in settings.ALLOWED_FILE_TYPES:
        raise BadRequestException(
            code="INVALID_FILE_TYPE",
            message=f"File type '{file.content_type}' is not allowed",
            details={"allowed_types": settings.ALLOWED_FILE_TYPES},
        )


async def save_upload(
    file: UploadFile,
    subdirectory: str = "general",
) -> dict:
    validate_file(file)

    content = await file.read()
    if len(content) > settings.max_file_size_bytes:
        raise BadRequestException(
            code="FILE_TOO_LARGE",
            message=f"File size exceeds {settings.MAX_FILE_SIZE_MB}MB limit",
        )

    upload_dir = Path(settings.UPLOAD_DIR) / subdirectory
    upload_dir.mkdir(parents=True, exist_ok=True)

    ext = Path(file.filename or "file").suffix
    unique_name = f"{uuid.uuid4().hex}{ext}"
    file_path = upload_dir / unique_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    relative_path = f"{subdirectory}/{unique_name}"
    logger.info("file_uploaded", path=relative_path, size=len(content), content_type=file.content_type)

    return {
        "file_name": file.filename or "file",
        "file_url": f"/uploads/{relative_path}",
        "file_size": len(content),
        "content_type": file.content_type,
    }


async def delete_upload(file_url: str) -> bool:
    if not file_url.startswith("/uploads/"):
        return False
    relative_path = file_url.replace("/uploads/", "")
    file_path = Path(settings.UPLOAD_DIR) / relative_path
    if file_path.exists():
        os.remove(file_path)
        logger.info("file_deleted", path=relative_path)
        return True
    return False
