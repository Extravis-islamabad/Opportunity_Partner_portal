from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import structlog

from app.core.config import settings
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_token,
)
from app.core.redis import redis_client
from app.core.exceptions import (
    UnauthorizedException,
    BadRequestException,
    NotFoundException,
)
from app.models.user import User, UserRole, UserStatus
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    UserBasicResponse,
)
from app.utils.email import send_template_email

logger = structlog.get_logger()


async def login(db: AsyncSession, data: LoginRequest) -> dict:
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.email == data.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user:
        raise UnauthorizedException(code="INVALID_CREDENTIALS", message="Invalid email or password")

    if user.status == UserStatus.LOCKED:
        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            raise UnauthorizedException(
                code="ACCOUNT_LOCKED",
                message=f"Account is locked. Try again after {user.locked_until.isoformat()}",
            )
        else:
            user.status = UserStatus.ACTIVE
            user.failed_login_attempts = 0
            user.locked_until = None

    if user.status == UserStatus.PENDING_ACTIVATION:
        raise UnauthorizedException(code="ACCOUNT_NOT_ACTIVATED", message="Please activate your account first")

    if user.status == UserStatus.INACTIVE:
        raise UnauthorizedException(code="ACCOUNT_INACTIVE", message="Account has been deactivated")

    if not verify_password(data.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
            user.status = UserStatus.LOCKED
            user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
            logger.warning("account_locked", user_id=user.id, email=user.email)
        await db.flush()
        raise UnauthorizedException(code="INVALID_CREDENTIALS", message="Invalid email or password")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    token_data = {"sub": str(user.id), "role": user.role.value}
    if user.company_id:
        token_data["company_id"] = user.company_id

    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    refresh_payload = decode_token(refresh_token)
    jti = refresh_payload.get("jti", "")
    ttl = settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400
    await redis_client.set(f"refresh:{jti}", str(user.id), ex=ttl)

    company_name = user.company.name if user.company else None

    # Compute channel manager flags for admin users
    managed_count = 0
    is_cm = False
    if user.role == UserRole.ADMIN:
        from app.models.company import Company
        cnt_res = await db.execute(
            select(func.count(Company.id)).where(
                Company.channel_manager_id == user.id,
                Company.deleted_at.is_(None),
            )
        )
        managed_count = cnt_res.scalar() or 0
        is_cm = managed_count > 0

    login_response = LoginResponse(
        access_token=access_token,
        user=UserBasicResponse(
            id=user.id,
            full_name=user.full_name,
            email=user.email,
            role=user.role.value,
            status=user.status.value,
            company_id=user.company_id,
            company_name=company_name,
            is_superadmin=user.is_superadmin,
            is_channel_manager=is_cm,
            managed_company_count=managed_count,
        ),
    )

    return {
        "login_response": login_response,
        "refresh_token": refresh_token,
    }


async def refresh_access_token(refresh_token: str) -> RefreshResponse:
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise UnauthorizedException(code="INVALID_REFRESH_TOKEN", message="Invalid or expired refresh token")

    jti = payload.get("jti", "")
    stored = await redis_client.get(f"refresh:{jti}")
    if not stored:
        raise UnauthorizedException(code="REFRESH_TOKEN_REVOKED", message="Refresh token has been revoked")

    token_data = {"sub": payload["sub"], "role": payload["role"]}
    if "company_id" in payload:
        token_data["company_id"] = payload["company_id"]

    new_access_token = create_access_token(token_data)
    return RefreshResponse(access_token=new_access_token)


async def logout(access_token: str, refresh_token: str | None = None) -> None:
    payload = decode_token(access_token)
    if payload:
        exp = payload.get("exp", 0)
        now = int(datetime.now(timezone.utc).timestamp())
        ttl = max(exp - now, 0)
        if ttl > 0:
            await redis_client.set(f"token:blacklist:{access_token}", "1", ex=ttl)

    if refresh_token:
        refresh_payload = decode_token(refresh_token)
        if refresh_payload:
            jti = refresh_payload.get("jti", "")
            await redis_client.delete(f"refresh:{jti}")


async def forgot_password(db: AsyncSession, email: str) -> None:
    result = await db.execute(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user:
        return

    token = generate_token()
    user.reset_token = token
    user.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS)
    await db.flush()

    await send_template_email(
        to_emails=[user.email],
        subject="Password Reset - Extravis Partner Portal",
        template_name="password_reset",
        context={
            "name": user.full_name,
            "reset_token": token,
            "expire_hours": settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS,
        },
    )


async def reset_password(db: AsyncSession, token: str, new_password: str) -> None:
    result = await db.execute(
        select(User).where(
            User.reset_token == token,
            User.reset_token_expires > datetime.now(timezone.utc),
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise BadRequestException(code="INVALID_RESET_TOKEN", message="Invalid or expired reset token")

    user.password_hash = hash_password(new_password)
    user.reset_token = None
    user.reset_token_expires = None
    user.failed_login_attempts = 0
    user.locked_until = None
    if user.status == UserStatus.LOCKED:
        user.status = UserStatus.ACTIVE
    await db.flush()


async def activate_account(db: AsyncSession, token: str, password: str) -> None:
    result = await db.execute(
        select(User).where(
            User.activation_token == token,
            User.activation_token_expires > datetime.now(timezone.utc),
            User.status == UserStatus.PENDING_ACTIVATION,
            User.deleted_at.is_(None),
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise BadRequestException(code="INVALID_ACTIVATION_TOKEN", message="Invalid or expired activation token")

    user.password_hash = hash_password(password)
    user.activation_token = None
    user.activation_token_expires = None
    user.status = UserStatus.ACTIVE
    await db.flush()


async def change_password(db: AsyncSession, user: User, current_password: str, new_password: str) -> None:
    if not verify_password(current_password, user.password_hash):
        raise BadRequestException(code="INVALID_CURRENT_PASSWORD", message="Current password is incorrect")

    user.password_hash = hash_password(new_password)
    await db.flush()
