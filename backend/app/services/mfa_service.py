"""Second-factor enrolment, verification and recovery.

The rules that shape this:

  - Enrolment is two steps. A secret alone proves nothing; the account is only
    protected once the person has proved they can produce a code from it.
    Otherwise a mistyped setup locks somebody out of their own account.
  - A code is accepted once. TOTP codes live for thirty seconds, and without
    remembering the last accepted window, one observed code works repeatedly
    inside its own lifetime.
  - Recovery codes are hashed and single-use. They are credentials.
  - Enforcement has a grace window. Switching on "admins must use MFA" cannot
    lock out every admin who has not enrolled yet — they need to be able to log
    in far enough to enrol.
"""
import secrets
from datetime import datetime, timedelta, timezone

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    UnauthorizedException,
)
from app.core.security import hash_password, verify_password
from app.models.mfa import MfaEnrollment, MfaRecoveryCode
from app.models.user import User, UserRole
from app.utils.audit import write_audit_log

RECOVERY_CODE_COUNT = 10
# Two windows either side: a phone whose clock is a minute out is common, and
# refusing those codes teaches people that MFA is broken. Wider than that and
# an observed code stays useful for too long.
TOTP_VALID_WINDOW = 1


def _new_recovery_code() -> str:
    """Ten hex characters in two groups. Long enough to be unguessable, short
    enough that somebody can read it off a printout without mistakes."""
    raw = secrets.token_hex(5)
    return f"{raw[:5]}-{raw[5:]}"


async def get_enrollment(db: AsyncSession, user_id: int) -> MfaEnrollment | None:
    return (await db.execute(
        select(MfaEnrollment).where(MfaEnrollment.user_id == user_id)
    )).scalar_one_or_none()


async def is_active(db: AsyncSession, user_id: int) -> bool:
    enrollment = await get_enrollment(db, user_id)
    return enrollment is not None and enrollment.is_active


def is_required_for(user: User) -> bool:
    """Whether this account must use a second factor.

    Off unless switched on, and then only for the accounts whose blast radius
    justifies it: an admin can reach every partner's pipeline, and a superadmin
    can change what everybody is paid.
    """
    if not settings.MFA_REQUIRED_FOR_ADMINS:
        return False
    return user.role == UserRole.ADMIN


async def status_for(db: AsyncSession, user: User) -> dict:
    enrollment = await get_enrollment(db, user.id)
    remaining = 0
    if enrollment is not None:
        remaining = len([c for c in enrollment.recovery_codes if c.used_at is None])

    return {
        "enabled": enrollment is not None and enrollment.is_active,
        "required": is_required_for(user),
        "recovery_codes_remaining": remaining,
        "grace_days": settings.MFA_GRACE_DAYS,
    }


async def begin_enrollment(db: AsyncSession, user: User) -> dict:
    """Create (or replace) an unconfirmed secret and return it once.

    Replacing an unconfirmed enrolment is deliberate: somebody who abandoned
    setup halfway and started again should get a fresh secret rather than an
    error about a row they cannot see.
    """
    existing = await get_enrollment(db, user.id)
    if existing is not None and existing.is_active:
        raise ConflictException(
            code="MFA_ALREADY_ENABLED",
            message="Two-factor authentication is already on for this account",
        )
    if existing is not None:
        await db.delete(existing)
        await db.flush()

    secret = pyotp.random_base32()
    enrollment = MfaEnrollment(user_id=user.id, secret=secret)
    db.add(enrollment)
    await db.flush()

    uri = pyotp.TOTP(secret).provisioning_uri(
        name=user.email, issuer_name=settings.APP_NAME
    )
    return {
        # Shown once, at setup, and never returned again.
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg": _qr_svg(uri),
    }


def _qr_svg(uri: str) -> str:
    """The provisioning URI as an inline SVG.

    Rendered here rather than in the browser so the frontend needs no QR
    dependency, and so the secret is not handed to a third-party script.
    """
    import io

    import qrcode
    import qrcode.image.svg

    image = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage)
    buffer = io.BytesIO()
    image.save(buffer)
    return buffer.getvalue().decode()


async def confirm_enrollment(db: AsyncSession, user: User, code: str) -> list[str]:
    """Prove the authenticator works, switch MFA on, and issue recovery codes.

    The codes are returned exactly once — they are stored hashed, so this is
    the only moment anybody can read them.
    """
    enrollment = await get_enrollment(db, user.id)
    if enrollment is None:
        raise BadRequestException(
            code="MFA_NOT_STARTED",
            message="Start setting up two-factor authentication first",
        )
    if enrollment.is_active:
        raise ConflictException(
            code="MFA_ALREADY_ENABLED",
            message="Two-factor authentication is already on for this account",
        )

    if not _verify_totp(enrollment, code):
        raise BadRequestException(
            code="INVALID_MFA_CODE",
            message="That code is not right. Check your authenticator and try again.",
        )

    enrollment.confirmed_at = datetime.now(timezone.utc)
    codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code_value in codes:
        db.add(MfaRecoveryCode(
            enrollment_id=enrollment.id, code_hash=hash_password(code_value)
        ))
    await db.flush()

    await write_audit_log(
        db, user.id, "UPDATE", "user", user.id, {"action": "mfa_enabled"}
    )
    return codes


def _matched_counter(secret: str, code: str) -> int | None:
    """Which time window this code belongs to, or None if it belongs to none.

    pyotp's verify() answers yes or no; the window that matched is what has to
    be remembered. Recording "the window it is now" instead would mean the code
    shown at 10:00:00, accepted a second before the minute turns, also burns
    the one the phone shows at 10:00:30 — which the person is about to read off
    the screen and be told is wrong.
    """
    totp = pyotp.TOTP(secret)
    current = int(datetime.now(timezone.utc).timestamp()) // totp.interval
    for offset in range(-TOTP_VALID_WINDOW, TOTP_VALID_WINDOW + 1):
        candidate = current + offset
        if secrets.compare_digest(totp.at(candidate * totp.interval), code):
            return candidate
    return None


def _verify_totp(enrollment: MfaEnrollment, code: str) -> bool:
    """Check a code, and refuse one already used.

    pyotp's own verify accepts any code inside the window, including one that
    has just been used. A code observed over somebody's shoulder is good for
    its whole window unless the last accepted counter is remembered.
    """
    cleaned = (code or "").strip().replace(" ", "")
    if not cleaned.isdigit():
        return False

    counter = _matched_counter(enrollment.secret, cleaned)
    if counter is None:
        return False

    if (
        enrollment.last_used_counter is not None
        and counter <= enrollment.last_used_counter
    ):
        return False

    enrollment.last_used_counter = counter
    return True


async def verify_second_factor(db: AsyncSession, user: User, code: str) -> None:
    """Accept a TOTP code or a recovery code. Raises if neither."""
    enrollment = await get_enrollment(db, user.id)
    if enrollment is None or not enrollment.is_active:
        raise UnauthorizedException(
            code="MFA_NOT_ENABLED",
            message="Two-factor authentication is not set up for this account",
        )

    if _verify_totp(enrollment, code):
        await db.flush()
        return

    if await _consume_recovery_code(db, enrollment, code):
        await write_audit_log(
            db, user.id, "UPDATE", "user", user.id,
            {"action": "mfa_recovery_code_used"},
        )
        return

    raise UnauthorizedException(
        code="INVALID_MFA_CODE", message="That code is not right"
    )


async def _consume_recovery_code(
    db: AsyncSession, enrollment: MfaEnrollment, code: str
) -> bool:
    cleaned = (code or "").strip().lower()
    if not cleaned:
        return False

    unused = (await db.execute(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.enrollment_id == enrollment.id,
            MfaRecoveryCode.used_at.is_(None),
        )
    )).scalars().all()

    for row in unused:
        if verify_password(cleaned, row.code_hash):
            # Marked used rather than deleted: "which of my codes have I
            # burned" is a question people ask.
            row.used_at = datetime.now(timezone.utc)
            await db.flush()
            return True
    return False


async def disable(db: AsyncSession, user: User, actor: User) -> None:
    """Turn MFA off, taking the recovery codes with it.

    Allowed even where MFA is required: an admin who has lost both their phone
    and their codes has to be able to start again, and the alternative is a
    locked account and a database edit. The audit log carries who did it.
    """
    enrollment = await get_enrollment(db, user.id)
    if enrollment is None:
        return
    await db.delete(enrollment)
    await db.flush()
    await write_audit_log(
        db, actor.id, "UPDATE", "user", user.id,
        {"action": "mfa_disabled", "by_self": actor.id == user.id},
    )


async def regenerate_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    """Issue a fresh set, invalidating the old ones."""
    enrollment = await get_enrollment(db, user.id)
    if enrollment is None or not enrollment.is_active:
        raise BadRequestException(
            code="MFA_NOT_ENABLED",
            message="Two-factor authentication is not on for this account",
        )

    for row in enrollment.recovery_codes:
        await db.delete(row)
    await db.flush()

    codes = [_new_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]
    for code_value in codes:
        db.add(MfaRecoveryCode(
            enrollment_id=enrollment.id, code_hash=hash_password(code_value)
        ))
    await db.flush()

    await write_audit_log(
        db, user.id, "UPDATE", "user", user.id,
        {"action": "mfa_recovery_codes_regenerated"},
    )
    return codes


def grace_expires_at(user: User) -> datetime | None:
    """When an account required to use MFA stops being let in without it.

    Measured from when the account was created, so switching enforcement on
    does not lock out everybody who has not enrolled — but it also does not
    give a brand-new admin an open-ended pass.
    """
    if settings.MFA_GRACE_DAYS <= 0:
        return None
    created = user.created_at
    if created is None:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created + timedelta(days=settings.MFA_GRACE_DAYS)


async def assert_enrolment_not_overdue(db: AsyncSession, user: User) -> None:
    """Refuse a login from an account that had to enrol and did not.

    The grace window is the difference between rolling MFA out and locking the
    whole admin team out on the morning somebody flips the setting.
    """
    if not is_required_for(user):
        return
    if await is_active(db, user.id):
        return

    deadline = grace_expires_at(user)
    if deadline is not None and datetime.now(timezone.utc) < deadline:
        return

    raise UnauthorizedException(
        code="MFA_ENROLMENT_REQUIRED",
        message=(
            "Two-factor authentication is required for this account and the "
            "setup period has passed. Ask a superadmin to reset it for you."
        ),
    )
