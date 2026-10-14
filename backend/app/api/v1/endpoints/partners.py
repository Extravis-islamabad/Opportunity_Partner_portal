from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import math

from app.core.database import get_db
from app.core.deps import (
    get_current_admin,
    get_current_user,
    get_current_partner,
    get_admin_scope,
    assert_can_view_user,
    assert_can_manage_user,
)
from app.models.user import User
from app.schemas.user import (
    HandoverRequest,
    UserCreateRequest,
    UserUpdateRequest,
    AdminUserUpdateRequest,
    UserResponse,
    TeamMemberCreateRequest,
)
from app.schemas.common import MessageResponse
from app.services import handover_service, partner_service

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
        if data.role == "sales_rep":
            from app.core.exceptions import ForbiddenException
            raise ForbiddenException(message="Only superadmins can create sales rep accounts")
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
    # Constrained to the enum values: an unknown value reached the Postgres
    # enum comparison and came back as a 500 instead of a 422.
    status: Optional[str] = Query(None, pattern="^(active|inactive|pending_activation|locked)$"),
    search: Optional[str] = Query(None, max_length=255),
    role: Optional[str] = Query(None, pattern="^(admin|partner|sales_rep)$"),
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


@router.post("/team", response_model=UserResponse, status_code=201)
async def create_team_member(
    data: TeamMemberCreateRequest,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    """A partner adding one of their own company's employees.

    Scoped to the caller's own company — there is no company_id to pass or
    tamper with. The account is created active with a generated password
    mailed to the new employee, not an activation link: the partner adding
    them already knows who they are.
    """
    return await partner_service.create_team_member(db, data, partner)


@router.get("/team", status_code=200)
async def list_team(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    partner: User = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    """The partner's own company roster — every account under company_id,
    including ones an admin created. This is how the partner sees their own
    team; admin oversight of the same accounts is the existing company
    detail page and the superadmin Users list."""
    if not partner.company_id:
        # No company means nothing to scope the list to — never fall through
        # to get_partners with company_id=None, which would list everyone.
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "total_pages": 0}

    items, total = await partner_service.get_partners(
        db, page, page_size, company_id=partner.company_id, search=search,
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/{user_id}", response_model=UserResponse, status_code=200)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """A single user account.

    Authorised per-record: superadmins see anyone, admins see users of the
    companies they manage, everyone else sees only themselves. The list route
    above is scoped, so without this check this route was the way around it.
    """
    target = await partner_service.load_user_or_404(db, user_id)
    await assert_can_view_user(db, current_user, target)
    return partner_service.serialize_user(target)


@router.put("/{user_id}", response_model=UserResponse, status_code=200)
async def update_user(
    user_id: int,
    data: AdminUserUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # A channel manager may only edit users inside their managed companies;
    # superadmins may edit anyone. Without this a channel-manager admin could
    # deactivate a peer admin or the superadmin by id.
    # A "status" in the body is applied through the same deactivate /
    # reactivate rules as the dedicated endpoints below, so it can answer 409
    # HANDOVER_REQUIRED or ACCOUNT_NOT_ACTIVATED exactly as they do.
    target = await partner_service.load_user_or_404(db, user_id)
    await assert_can_manage_user(db, admin, target)
    return await partner_service.update_partner(db, user_id, data, admin)


@router.put("/me/profile", response_model=UserResponse, status_code=200)
async def update_my_profile(
    data: UserUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Carry over only the fields the caller actually sent. Passing every field
    # explicitly marked the unsent ones as "set to None": {"phone": "1"} then
    # tried to null full_name (a 500), and saving a job title wiped the phone
    # and department. Status is not on UserUpdateRequest, so nobody can
    # reactivate or deactivate themselves through this route.
    admin_data = AdminUserUpdateRequest(**data.model_dump(exclude_unset=True))
    return await partner_service.update_partner(db, current_user.id, admin_data, current_user)


@router.get("/{user_id}/workload", status_code=200)
async def get_workload(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """What this account still holds, and its handover history.

    Backs the confirmation screen: an admin about to switch somebody off
    should see what is going to be orphaned before they try.
    """
    target = await partner_service.load_user_or_404(db, user_id)
    await assert_can_manage_user(db, admin, target)

    work = await handover_service.outstanding_work(db, target)
    return {
        **work,
        "history": await handover_service.history(db, user_id),
    }


@router.post("/{user_id}/handover", status_code=200)
async def hand_over_work(
    user_id: int,
    data: HandoverRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Move everything this account still holds to somebody else.

    Scoped on both ends: an admin can only do this for people they manage, and
    only to people they manage — otherwise it becomes a way to push work into
    another manager's book.
    """
    leaver = await partner_service.load_user_or_404(db, user_id)
    await assert_can_manage_user(db, admin, leaver)

    successor = await handover_service.load_successor(db, data.to_user_id)
    await assert_can_manage_user(db, admin, successor)

    record = await handover_service.hand_over(
        db, leaver, successor, admin, data.notes
    )
    return {
        "id": record.id,
        "to_user_id": record.to_user_id,
        "moved": record.moved,
    }


@router.post("/{user_id}/deactivate", response_model=MessageResponse, status_code=200)
async def deactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await partner_service.load_user_or_404(db, user_id)
    await assert_can_manage_user(db, admin, target)
    await partner_service.deactivate_partner(db, user_id, admin)
    return MessageResponse(message="User deactivated successfully")


@router.post("/{user_id}/reactivate", response_model=MessageResponse, status_code=200)
async def reactivate_user(
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await partner_service.load_user_or_404(db, user_id)
    await assert_can_manage_user(db, admin, target)
    await partner_service.reactivate_partner(db, user_id, admin)
    return MessageResponse(message="User reactivated successfully")
