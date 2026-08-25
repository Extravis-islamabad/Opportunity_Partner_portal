"""Setting up, checking and resetting two-factor authentication."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_superadmin, get_current_user
from app.models.user import User
from app.schemas.auth import MfaConfirmRequest
from app.schemas.common import MessageResponse
from app.services import mfa_service, partner_service

router = APIRouter(prefix="/mfa", tags=["Two-factor authentication"])


@router.get("/status", status_code=200)
async def get_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Whether this account has a second factor, and whether it needs one."""
    return await mfa_service.status_for(db, current_user)


@router.post("/setup", status_code=201)
async def begin_setup(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a secret and the QR to scan.

    Nothing is protected yet — the account is only covered once a code from
    this secret has been proved, so a mistyped setup cannot lock anybody out.
    The secret is returned here and never again.
    """
    return await mfa_service.begin_enrollment(db, current_user)


@router.post("/confirm", status_code=200)
async def confirm_setup(
    data: MfaConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Prove the authenticator works, and get the recovery codes.

    The codes are shown exactly once: they are stored hashed, so nobody —
    including us — can read them back.
    """
    codes = await mfa_service.confirm_enrollment(db, current_user, data.code)
    return {"enabled": True, "recovery_codes": codes}


@router.post("/recovery-codes", status_code=200)
async def regenerate_recovery_codes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Issue a fresh set, invalidating the old ones."""
    return {"recovery_codes": await mfa_service.regenerate_recovery_codes(db, current_user)}


@router.delete("", response_model=MessageResponse, status_code=200)
async def disable_own(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Turn off your own second factor."""
    await mfa_service.disable(db, current_user, current_user)
    return MessageResponse(message="Two-factor authentication turned off")


@router.delete("/users/{user_id}", response_model=MessageResponse, status_code=200)
async def reset_for_user(
    user_id: int,
    # Superadmin only: this is the lockout escape hatch, and it removes a
    # second factor from somebody else's account.
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Reset somebody's second factor after they lose their phone and codes.

    The alternative to having this is a locked-out admin and a database edit.
    Who did it is in the audit log.
    """
    target = await partner_service.load_user_or_404(db, user_id)
    await mfa_service.disable(db, target, admin)
    return MessageResponse(
        message=f"Two-factor authentication reset for {target.full_name}"
    )
