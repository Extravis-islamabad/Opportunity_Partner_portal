"""Authenticated file downloads.

Replaces the old anonymous `/uploads` static mount. A caller presents a
signed, short-lived token (minted by whichever authorised response handed
out the file) and we stream the one path that token authorises — after
resolving it and confirming it stays inside the upload directory, so a
crafted token can't escape via `..` or an absolute path.
"""
from pathlib import Path

from fastapi import APIRouter, Query
from fastapi.responses import FileResponse

from app.core.config import settings
from app.core.exceptions import NotFoundException, UnauthorizedException
from app.utils.file_tokens import verify_file_token

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/download")
async def download_file(token: str = Query(..., description="Signed download token")):
    rel = verify_file_token(token)
    if rel is None:
        raise UnauthorizedException(
            code="INVALID_DOWNLOAD_TOKEN",
            message="This download link is invalid or has expired",
        )

    upload_root = Path(settings.UPLOAD_DIR).resolve()
    # Resolve the candidate and confirm it stays within the upload root — a
    # token carrying '../../etc/passwd' or a leading '/' resolves outside and
    # is rejected. is_relative_to (3.9+) is the explicit containment check.
    candidate = (upload_root / rel).resolve()
    if not candidate.is_relative_to(upload_root):
        raise UnauthorizedException(
            code="INVALID_DOWNLOAD_TOKEN",
            message="This download link is invalid or has expired",
        )
    if not candidate.is_file():
        raise NotFoundException(code="FILE_NOT_FOUND", message="File not found")

    # attachment (not inline): even though uploads are validated on the way
    # in, forcing download rather than render is defence-in-depth against a
    # file that slips through as something browser-executable.
    return FileResponse(
        path=str(candidate),
        filename=candidate.name,
        content_disposition_type="attachment",
    )
