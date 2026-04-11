from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
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

    # Eager-load .company so any downstream endpoint that touches
    # current_user.company doesn't trigger an async lazy-load (which fails
    # outside the greenlet context with MissingGreenlet).
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.id == int(user_id), User.deleted_at.is_(None))
    )
    user = result.unique().scalar_one_or_none()

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


async def get_admin_scope(
    db: AsyncSession,
    user: User,
) -> Optional[list[int]]:
    """
    Determine which company IDs an admin is allowed to see.

    Returns:
      - None  → superadmin (no scope, sees everything globally)
      - [...] → channel manager scoped to these company ids (may be empty
                if the admin manages zero companies, in which case they see
                no operational data)

    Partners should not call this — they have their own scoping by
    submitted_by / company_id at the endpoint level.
    """
    if user.is_superadmin:
        return None
    from app.models.company import Company
    result = await db.execute(
        select(Company.id).where(
            Company.channel_manager_id == user.id,
            Company.deleted_at.is_(None),
        )
    )
    return [row[0] for row in result.all()]
