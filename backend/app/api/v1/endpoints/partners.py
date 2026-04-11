from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user, get_admin_scope
from app.models.user import User
from app.schemas.user import (
    UserCreateRequest,
    UserUpdateRequest,
    AdminUserUpdateRequest,
    UserResponse,
)
from app.schemas.common import MessageResponse
from app.services import partner_service

router = APIRouter(prefix="/users", tags=["Users & Partners"])


@router.post("", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Channel managers can only create partner accounts for companies they
    # manage. Superadmins can create anything.
    if not admin.is_superadmin:
        if data.role == "admin":
            from app.core.exceptions import ForbiddenException
            raise ForbiddenException(message="Only superadmins can create admin accounts")
        if data.role == "partner":
            scope = await get_admin_scope(db, admin)
            if data.company_id not in (scope or []):
                from app.core.exceptions import ForbiddenException
                raise ForbiddenException(message="You can only add partners to companies you manage")
    return await partner_service.create_partner_account(db, data, admin)


@router.get("", status_code=200)
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    company_id: Optional[int] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
    role: Optional[str] = None,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Channel-manager scope: only see partner users belonging to their companies
    scope = None
    if not admin.is_superadmin:
        scope = await get_admin_scope(db, admin)

    items, total = await partner_service.get_partners(
        db, page, page_size, company_id, status, search, role,
        scope_company_ids=scope,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/admins", status_code=200)
async def list_admins(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await partner_service.get_admins_list(db)


@router.get("/{user_id}", response_model=UserResponse, status_code=200)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await partner_service.get_partner_detail(db, user_id)


@router.put("/{user_id}", response_model=UserResponse, status_code=200)
async def update_user(
    user_id: int,
    data: AdminUserUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    return await partner_service.update_partner(db, user_id, data, admin)


@router.put("/me/profile", response_model=UserResponse, status_code=200)
async def update_my_profile(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    admin_data = AdminUserUpdateRequest(
        full_name=data.full_name,
        job_title=data.job_title,
        phone=data.phone,
    )
    return await partner_service.update_partner(db, current_user.id, admin_data, current_user)


@router.post("/{user_id}/deactivate", response_model=MessageResponse, status_code=200)
async def deactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await partner_service.deactivate_partner(db, user_id, admin)
    return MessageResponse(message="User deactivated successfully")


@router.post("/{user_id}/reactivate", response_model=MessageResponse, status_code=200)
async def reactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    await partner_service.reactivate_partner(db, user_id, admin)
    return MessageResponse(message="User reactivated successfully")
