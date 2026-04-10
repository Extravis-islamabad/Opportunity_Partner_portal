from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.database import get_db
from app.core.security import decode_token
from app.core.redis import redis_client
from app.core.exceptions import UnauthorizedException, ForbiddenException
from app.models.user import User, UserRole
from sqlalchemy import select


async def get_current_user(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedException(message="Missing or invalid authorization header")

    token = authorization.split(" ", 1)[1]

    is_blacklisted = await redis_client.get(f"token:blacklist:{token}")
    if is_blacklisted:
        raise UnauthorizedException(code="TOKEN_REVOKED", message="Token has been revoked")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise UnauthorizedException(code="INVALID_TOKEN", message="Invalid or expired access token")

    user_id = payload.get("sub")
    if not user_id:
        raise UnauthorizedException(code="INVALID_TOKEN", message="Invalid token payload")

    result = await db.execute(
        select(User).where(User.id == int(user_id), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException(code="USER_NOT_FOUND", message="User account not found")

    if user.status != "active":
        raise UnauthorizedException(code="ACCOUNT_INACTIVE", message="Account is not active")

    return user


async def get_current_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(message="Admin access required")
    return current_user


async def get_current_partner(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.PARTNER:
        raise ForbiddenException(message="Partner access required")
    return current_user


async def get_current_superadmin(
    current_user: User = Depends(get_current_admin),
) -> User:
    if not current_user.is_superadmin:
        raise ForbiddenException(message="This action requires superadmin access")
    return current_user


async def get_admin_or_channel_manager(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.ADMIN:
        raise ForbiddenException(message="Admin access required")
    return current_user
