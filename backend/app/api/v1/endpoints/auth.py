from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import UnauthorizedException
from app.core.security import decode_token
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    RefreshResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    ActivateAccountRequest,
    ChangePasswordRequest,
    UserBasicResponse,
)
from app.schemas.common import MessageResponse
from app.services import auth_service
from app.utils.audit import write_audit_log

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        samesite="lax",
        secure=(settings.APP_ENV != "development"),
        max_age=REFRESH_COOKIE_MAX_AGE,
        path="/api/v1/auth",
    )


@router.post("/login", response_model=LoginResponse, status_code=200)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    result = await auth_service.login(db, data)
    login_response = result["login_response"]
    refresh_token = result["refresh_token"]

    await write_audit_log(
        db,
        user_id=login_response.user.id,
        action="LOGIN",
        entity_type="user",
        entity_id=login_response.user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )

    response = JSONResponse(content=login_response.model_dump())
    _set_refresh_cookie(response, refresh_token)
    return response


@router.post("/refresh", response_model=RefreshResponse, status_code=200)
async def refresh_token(request: Request):
    token = request.cookies.get("refresh_token")
    if not token:
        raise UnauthorizedException(code="MISSING_REFRESH_TOKEN", message="Refresh token cookie is missing")
    return await auth_service.refresh_access_token(token)


@router.post("/logout", response_model=MessageResponse, status_code=200)
async def logout(
    request: Request,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]

    # Extract user_id from access token before logout invalidates it
    user_id = None
    if token:
        payload = decode_token(token)
        if payload:
            user_id = int(payload.get("sub", 0)) or None

    refresh_token = request.cookies.get("refresh_token")
    await auth_service.logout(token, refresh_token)

    if user_id:
        await write_audit_log(
            db,
            user_id=user_id,
            action="LOGOUT",
            entity_type="user",
            entity_id=user_id,
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

    response = JSONResponse(content={"message": "Logged out successfully"})
    response.delete_cookie(
        key="refresh_token",
        path="/api/v1/auth",
        httponly=True,
        samesite="lax",
        secure=(settings.APP_ENV != "development"),
    )
    return response


@router.post("/forgot-password", response_model=MessageResponse, status_code=200)
async def forgot_password(data: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.forgot_password(db, data.email)
    return MessageResponse(message="If an account exists with this email, a password reset link has been sent")


@router.post("/reset-password", response_model=MessageResponse, status_code=200)
async def reset_password(data: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.reset_password(db, data.token, data.new_password)
    return MessageResponse(message="Password reset successfully")


@router.post("/activate", response_model=MessageResponse, status_code=200)
async def activate_account(data: ActivateAccountRequest, db: AsyncSession = Depends(get_db)):
    await auth_service.activate_account(db, data.token, data.password)
    return MessageResponse(message="Account activated successfully")


@router.post("/change-password", response_model=MessageResponse, status_code=200)
async def change_password(
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.change_password(db, current_user, data.current_password, data.new_password)
    return MessageResponse(message="Password changed successfully")


@router.get("/me", response_model=UserBasicResponse, status_code=200)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    company_name = None
    if current_user.company:
        company_name = current_user.company.name

    # Channel-manager flags for admin users
    managed_count = 0
    is_cm = False
    if current_user.role.value == "admin":
        from sqlalchemy import func, select
        from app.models.company import Company
        cnt_res = await db.execute(
            select(func.count(Company.id)).where(
                Company.channel_manager_id == current_user.id,
                Company.deleted_at.is_(None),
            )
        )
        managed_count = cnt_res.scalar() or 0
        is_cm = managed_count > 0

    return UserBasicResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role.value,
        status=current_user.status.value,
        company_id=current_user.company_id,
        company_name=company_name,
        is_superadmin=current_user.is_superadmin,
        is_channel_manager=is_cm,
        managed_company_count=managed_count,
        has_completed_onboarding=current_user.has_completed_onboarding,
    )
