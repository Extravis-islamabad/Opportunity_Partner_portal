from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
import secrets

from app.core.config import settings
from app.core.redis import redis_client

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire, "type": "refresh", "jti": secrets.token_urlsafe(32)})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


MFA_CHALLENGE_TTL_SECONDS = 300


def create_mfa_challenge_token(user_id: int) -> str:
    """A short-lived token proving the password step passed, nothing more.

    Typed `mfa_challenge` so it cannot be presented as an access token: the
    dependency that authenticates requests checks the type, and a token that
    only survives the second-factor step is worth far less to an attacker who
    intercepts it.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=MFA_CHALLENGE_TTL_SECONDS // 60)
    return jwt.encode(
        {
            "sub": str(user_id),
            "exp": expire,
            "type": "mfa_challenge",
            # Identifies this challenge so it can be spent exactly once — see
            # spend_mfa_challenge.
            "jti": secrets.token_urlsafe(16),
        },
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        return {}


async def spend_mfa_challenge(payload: Dict[str, Any]) -> bool:
    """Mark an MFA challenge as used. False if it already was (or has no id).

    Without this a challenge was good for its whole five minutes: anybody who
    saw one go past could pair it with the next code and sign in again, or
    keep guessing codes against the same challenge after the real login. SET
    NX makes the check-and-mark atomic, so two requests racing with the same
    challenge cannot both win. The key only has to outlive the token itself.
    """
    jti = payload.get("jti")
    if not jti:
        return False
    return bool(await redis_client.set(
        f"mfa_challenge_used:{jti}", "1", nx=True, ex=MFA_CHALLENGE_TTL_SECONDS
    ))


async def mfa_challenge_spent(payload: Dict[str, Any]) -> bool:
    jti = payload.get("jti")
    if not jti:
        return True
    return bool(await redis_client.exists(f"mfa_challenge_used:{jti}"))


# ---------------------------------------------------------------------------
# Session versions
#
# Access tokens are stateless JWTs, so changing a password used to leave every
# token already issued working until it expired, and every refresh cookie
# working for a week. Each user has a session version in Redis; tokens carry
# the version they were minted under (claim "sv"), and bumping the version on
# a password change or reset makes every older token stale at once.
#
# A missing key reads as 0 and so does a token without the claim, so tokens
# minted before this existed (and test fixtures) keep working until the first
# bump. If Redis is ever flushed, a token carrying sv>=1 stops matching — the
# failure mode is "sign in again", never "an old session comes back".
# ---------------------------------------------------------------------------

def _session_version_key(user_id: int) -> str:
    return f"session_version:{user_id}"


async def get_session_version(user_id: int) -> int:
    value = await redis_client.get(_session_version_key(user_id))
    return int(value) if value else 0


async def bump_session_version(user_id: int) -> int:
    """Invalidate every access token issued to this user so far."""
    return int(await redis_client.incr(_session_version_key(user_id)))


async def access_token_is_current(payload: Dict[str, Any]) -> bool:
    """Whether a decoded access token was minted under the user's current
    session version. get_current_user calls this after decoding."""
    try:
        user_id = int(payload.get("sub") or 0)
        token_version = int(payload.get("sv", 0))
    except (TypeError, ValueError):
        return False
    return token_version == await get_session_version(user_id)


async def revoke_refresh_tokens(user_id: int) -> int:
    """Delete every refresh token this user holds. Returns how many.

    Refresh tokens are stored as refresh:<jti> -> user id, with no per-user
    index, so this scans. Fine at this portal's size and only run on a
    password change or reset; an index would have to be kept in step with
    expiry for no real gain.
    """
    owner = str(user_id)
    doomed = []
    async for key in redis_client.scan_iter(match="refresh:*", count=500):
        if await redis_client.get(key) == owner:
            doomed.append(key)
    if doomed:
        await redis_client.delete(*doomed)
    return len(doomed)


def generate_token() -> str:
    return secrets.token_urlsafe(64)


def generate_temp_password(length: int = 12) -> str:
    """A random real password for an account provisioned with credentials up
    front (a partner adding a team member), as opposed to the activation-link
    flow where the person sets their own.

    Guarantees at least one lowercase, one uppercase, one digit and one
    symbol so it clears typical password policies, rather than leaving that
    to chance.
    """
    import string

    alphabet = string.ascii_letters + string.digits
    symbols = "!@#$%^&*"
    required = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
        secrets.choice(symbols),
    ]
    rest = [secrets.choice(alphabet + symbols) for _ in range(max(length - len(required), 0))]
    chars = required + rest
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
