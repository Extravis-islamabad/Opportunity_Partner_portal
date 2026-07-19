"""Short-lived signed download URLs (the S3-presigned-URL pattern).

The frontend downloads files with a plain `<a href>` / `window.open`, which
cannot carry an Authorization header. So instead of serving `/uploads` as
anonymous static files (any URL readable by anyone, forever), the API hands
back a `/api/v1/files/download?token=...` URL whose token is a signed,
short-lived capability for one specific file path.

The token is minted only inside an already-authorised response (e.g. the
opportunity detail the caller was allowed to see, or the KB download endpoint
that required auth), so possession of the URL means the API already decided
the caller could have the file — exactly like a presigned URL.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from app.core.config import settings

# A download link stays valid for this long after it's generated. Long enough
# to click through from a page that was just loaded; short enough that a
# leaked URL isn't a lasting capability.
DOWNLOAD_TOKEN_TTL_MINUTES = 30

_TOKEN_TYPE = "file_download"


def _normalise_relative_path(file_ref: str) -> str:
    """Accept either a stored '/uploads/x/y.pdf' value or a bare 'x/y.pdf'
    relative path and return the relative path ('x/y.pdf')."""
    ref = file_ref.strip()
    if ref.startswith("/uploads/"):
        ref = ref[len("/uploads/"):]
    return ref.lstrip("/")


def sign_file_path(file_ref: str, ttl_minutes: int = DOWNLOAD_TOKEN_TTL_MINUTES) -> str:
    """Return a signed token that authorises downloading exactly this path."""
    rel = _normalise_relative_path(file_ref)
    now = datetime.now(timezone.utc)
    payload = {
        "fp": rel,
        "type": _TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def verify_file_token(token: str) -> Optional[str]:
    """Return the relative path the token authorises, or None if the token is
    invalid, expired, or not a file-download token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None
    if payload.get("type") != _TOKEN_TYPE:
        return None
    rel = payload.get("fp")
    if not isinstance(rel, str) or not rel:
        return None
    return rel


def signed_file_url(file_ref: Optional[str]) -> Optional[str]:
    """Turn a stored file reference into a signed, expiring download URL.
    Returns None passthrough so callers can map nullable columns directly."""
    if not file_ref:
        return None
    return f"/api/v1/files/download?token={sign_file_path(file_ref)}"
