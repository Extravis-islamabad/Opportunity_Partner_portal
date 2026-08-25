from datetime import datetime, timedelta, timezone
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
import structlog

from app.core.config import settings
from app.core.security import (
    create_mfa_challenge_token,
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

# A precomputed bcrypt hash used to equalise timing when the email doesn't
# exist. Without it, an unknown email returns in ~1ms (no bcrypt) while a real
# one takes ~250ms — a timing oracle that enumerates valid accounts. We run a
# real verify against this dummy so both paths cost the same.
_DUMMY_PASSWORD_HASH = hash_password("timing-equaliser-not-a-real-password")

_GENERIC_LOGIN_ERROR = UnauthorizedException(
    code="INVALID_CREDENTIALS", message="Invalid email or password"
)


async def login(db: AsyncSession, data: LoginRequest) -> dict:
    result = await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.email == data.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    currently_locked = bool(
        user
        and user.status == UserStatus.LOCKED
        and user.locked_until
        and user.locked_until > now
    )

    # ALWAYS run a bcrypt verify — against the real hash if the user exists,
    # otherwise against a dummy — so response time doesn't reveal whether the
    # email is registered.
    password_ok = verify_password(
        data.password, user.password_hash if user else _DUMMY_PASSWORD_HASH
    )

    if not user or not password_ok:
        # Count the failure and lock after too many — but never while already
        # locked (so a locked account's window can't be extended forever), and
        # only for real accounts.
        if user and not currently_locked:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
                user.status = UserStatus.LOCKED
                user.locked_until = now + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                logger.warning("account_locked", user_id=user.id, email=user.email)
            await db.flush()
        # Identical response for unknown-email and wrong-password: no oracle.
        raise _GENERIC_LOGIN_ERROR

    # Password is correct. Only now is it safe to reveal account state — this
    # is not an enumeration oracle because the caller already proved they hold
    # the credentials.
    if user.status == UserStatus.LOCKED:
        if currently_locked:
            raise UnauthorizedException(
                code="ACCOUNT_LOCKED",
                message=f"Account is locked. Try again after {user.locked_until.isoformat()}",
            )
        # Lock window has passed — auto-unlock and continue.
        user.status = UserStatus.ACTIVE
        user.failed_login_attempts = 0
        user.locked_until = None

    if user.status == UserStatus.PENDING_ACTIVATION:
        raise UnauthorizedException(code="ACCOUNT_NOT_ACTIVATED", message="Please activate your account first")

    if user.status == UserStatus.INACTIVE:
        raise UnauthorizedException(code="ACCOUNT_INACTIVE", message="Account has been deactivated")

    # An account that must use a second factor and never enrolled is refused
    # once its setup period has passed — before any token is issued.
    from app.services import mfa_service

    await mfa_service.assert_enrolment_not_overdue(db, user)

    user.failed_login_attempts = 0
    user.locked_until = None

    # The password is right, but on an account with a second factor that is
    # only half the answer. No session is issued here: the caller gets a
    # short-lived challenge token and has to come back with a code. last_login
    # is deliberately not stamped yet — they have not logged in.
    if await mfa_service.is_active(db, user.id):
        await db.flush()
        return {
            "mfa_required": True,
            "challenge_token": create_mfa_challenge_token(user.id),
        }

    user.last_login_at = now
    await db.flush()

    return await _issue_session(db, user)





async def _issue_session(db: AsyncSession, user: User) -> dict:
    """Mint the tokens and build the login response.

    Shared by the plain password login and the second-factor completion, so
    the two cannot drift — a session issued after MFA has to be exactly the
    session issued without it.
    """
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
    company_type = user.company.company_type.value if user.company else None

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
            company_type=company_type,
            is_superadmin=user.is_superadmin,
            is_channel_manager=is_cm,
            managed_company_count=managed_count,
        ),
    )

    return {
        "login_response": login_response,
        "refresh_token": refresh_token,
    }


async def complete_mfa_login(db: AsyncSession, challenge_token: str, code: str) -> dict:
    """Second half of a login on an account with MFA.

    The challenge token only says "this person proved the password moments
    ago"; the code is what finishes the login. Both are required, and the
    challenge expires in minutes.
    """
    payload = decode_token(challenge_token)
    if not payload or payload.get("type") != "mfa_challenge":
        raise UnauthorizedException(
            code="INVALID_MFA_CHALLENGE",
            message="That sign-in attempt has expired. Please start again.",
        )

    user = (await db.execute(
        select(User)
        .options(joinedload(User.company))
        .where(User.id == int(payload["sub"]), User.deleted_at.is_(None))
    )).unique().scalar_one_or_none()
    if user is None or user.status != UserStatus.ACTIVE:
        raise UnauthorizedException(
            code="INVALID_MFA_CHALLENGE",
            message="That sign-in attempt is no longer valid",
        )

    from app.services import mfa_service

    await mfa_service.verify_second_factor(db, user, code)

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    return await _issue_session(db, user)


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
