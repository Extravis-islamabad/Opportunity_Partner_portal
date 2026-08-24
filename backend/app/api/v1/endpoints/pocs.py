"""POC and post-PO customer licence endpoints.

Reads are open to admins, sales reps, and partners (each scoped to what they
own). Writes are admin + sales rep only — partners see POC progress on their
opportunities but don't drive it, and are never eligible for the team.

Every handler that touches a single record calls assert_can_work_on_poc
against the *parent opportunity*, because that's where ownership lives: a POC
has no company_id or sales_rep_id of its own. That check is the strict
per-record one plus the POC's own team roster, so an assigned solution
architect or deployment engineer can do the work they were put on the POC to
do without being the opportunity's named sales rep.
"""
import math
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import (
    assert_can_access_opportunity,
    assert_can_work_on_poc,
    get_admin_scope,
    get_current_admin,
    get_current_user,
    get_partner_pipeline_scope,
    get_poc_editor,
)
from app.models.poc_team import POC_TEAM_ROLE_LABELS, PocTeamRole
from app.models.user import User, UserRole
from app.schemas.common import MessageResponse
from app.schemas.poc import (
    LicenseResponse,
    LicenseUpsertRequest,
    PocCloseRequest,
    PocResponse,
    PocStageOwnerRequest,
    PocStageUpdateRequest,
    PocStartRequest,
    PocUpdateRequest,
)
from app.schemas.sales_activity import PocActivityFeed
from app.schemas.poc_team import (
    PocTeamMemberCreateRequest,
    PocTeamMemberResponse,
    PocTeamRoleOption,
    PocTeamRoleUpdateRequest,
)
from app.services import poc_service, poc_team_service, sales_activity_service

router = APIRouter(prefix="/pocs", tags=["POC"])


async def _list_scope(db: AsyncSession, user: User) -> dict:
    """Translate the caller's role into list-query filters.

    Returns kwargs for poc_service.list_pocs / list_licenses. Partners are
    scoped to their company plus any resellers underneath it; sales reps by
    assignment; channel-manager admins by managed companies; superadmins
    unscoped.

    Extravis staff also get every POC they are on the team of, OR'd with the
    above — that is what puts an assigned POC in the list of a solution
    architect who is not the opportunity's named rep. Partners are never on a
    team, so the parameter is meaningless for them.
    """
    if user.role == UserRole.PARTNER:
        # A partner with no company sees nothing (empty list, not everything),
        # which get_partner_pipeline_scope returns as [].
        return {"scope_company_ids": await get_partner_pipeline_scope(db, user)}
    if user.role == UserRole.SALES_REP:
        return {"sales_rep_id": user.id, "team_member_id": user.id}

    scope = await get_admin_scope(db, user)
    if scope is None:
        # Superadmin. Returning no grounds at all is what means "everything" —
        # passing team_member_id here would OR a term onto nothing and
        # *narrow* them to their own POCs.
        return {}
    return {"scope_company_ids": scope, "team_member_id": user.id}


# ---------------------------------------------------------------------------
# POC — list & read
# ---------------------------------------------------------------------------

@router.get("", status_code=200)
async def list_pocs(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(not_started|running|successful|unsuccessful)$"),
    country: Optional[str] = None,
    company_id: Optional[int] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await poc_service.list_pocs(
        db,
        viewer=current_user,
        page=page,
        page_size=page_size,
        status=status,
        country=country,
        company_id=company_id,
        search=search,
        **await _list_scope(db, current_user),
    )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/by-opportunity/{opp_id}", response_model=Optional[PocResponse], status_code=200)
async def get_poc_for_opportunity(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """The POC for an opportunity, or null if one hasn't started yet. Null is
    a normal state (most opportunities never reach POC), so this returns 200
    with a null body rather than 404."""
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_work_on_poc(db, current_user, opp)

    poc = await poc_service.get_poc_by_opportunity(db, opp_id)
    return poc_service.to_poc_response(poc, viewer=current_user) if poc else None


@router.get("/{poc_id}", response_model=PocResponse, status_code=200)
async def get_poc(
    poc_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, current_user, poc.opportunity)
    return poc_service.to_poc_response(poc, viewer=current_user)


# ---------------------------------------------------------------------------
# POC — writes
# ---------------------------------------------------------------------------

@router.post("/by-opportunity/{opp_id}/start", response_model=PocResponse, status_code=201)
async def start_poc(
    opp_id: int,
    data: PocStartRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Start the POC by recording the VM allocation."""
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_work_on_poc(db, user, opp)
    return await poc_service.start_poc(db, opp_id, data, user)


@router.put("/{poc_id}", response_model=PocResponse, status_code=200)
async def update_poc(
    poc_id: int,
    data: PocUpdateRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, user, poc.opportunity)
    return await poc_service.update_poc(db, poc_id, data, user)


@router.put("/{poc_id}/stages/{stage_key}", response_model=PocResponse, status_code=200)
async def set_poc_stage(
    poc_id: int,
    stage_key: str,
    data: PocStageUpdateRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Tick a stage complete, or clear it by sending completed_at: null."""
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, user, poc.opportunity)
    return await poc_service.set_stage(db, poc_id, stage_key, data.completed_at, user)


@router.put(
    "/{poc_id}/stages/{stage_key}/owner",
    response_model=PocResponse,
    status_code=200,
)
async def set_poc_stage_owner(
    poc_id: int,
    stage_key: str,
    data: PocStageOwnerRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Name who is responsible for a stage, or send owner_user_id: null to
    clear it. The person must already be on the POC team."""
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, user, poc.opportunity)
    return await poc_service.set_stage_owner(
        db, poc_id, stage_key, data.owner_user_id, user
    )


@router.get("/{poc_id}/activities", response_model=PocActivityFeed, status_code=200)
async def get_poc_activities(
    poc_id: int,
    # get_poc_editor, not get_current_user: this is the internal record of who
    # did what. A partner sees the team roster and their roles, not the work
    # log behind it.
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    """Every activity logged against this POC, with a total per person."""
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, user, poc.opportunity)
    return await sales_activity_service.get_poc_activity_feed(db, poc)


@router.post("/{poc_id}/close", response_model=PocResponse, status_code=200)
async def close_poc(
    poc_id: int,
    data: PocCloseRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, user, poc.opportunity)
    return await poc_service.close_poc(db, poc_id, data, user)


@router.post("/{poc_id}/reopen", response_model=PocResponse, status_code=200)
async def reopen_poc(
    poc_id: int,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, user, poc.opportunity)
    return await poc_service.reopen_poc(db, poc_id, user)


# ---------------------------------------------------------------------------
# POC team
# ---------------------------------------------------------------------------
#
# Reading the roster follows the POC's own access rules — if you can see the
# POC you can see who is on it. Changing it is admin-only: staffing a POC is a
# management decision, and membership grants access, so it must not be
# self-service.

@router.get("/team/roles", response_model=list[PocTeamRoleOption], status_code=200)
async def list_team_roles(
    _user: User = Depends(get_poc_editor),
):
    """The selectable roles, so the picker doesn't hardcode them."""
    return [
        PocTeamRoleOption(value=role.value, label=label)
        for role, label in POC_TEAM_ROLE_LABELS.items()
    ]


@router.get("/team/assignable-users", status_code=200)
async def list_assignable_users(
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Everyone eligible for a POC team: active Extravis admins and sales
    reps. Admin-only because it enumerates staff accounts."""
    return await poc_team_service.get_assignable_users(db)


@router.get("/{poc_id}/team", response_model=list[PocTeamMemberResponse], status_code=200)
async def get_poc_team(
    poc_id: int,
    include_removed: bool = Query(
        False, description="Include people who have left the team."
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_work_on_poc(db, current_user, poc.opportunity)
    return await poc_team_service.get_team(
        db, poc_id, include_removed=include_removed
    )


@router.post("/{poc_id}/team", response_model=PocTeamMemberResponse, status_code=201)
async def add_poc_team_member(
    poc_id: int,
    data: PocTeamMemberCreateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Add someone to the POC team. They are notified, and they can work on
    the POC from that moment."""
    poc = await poc_service.get_poc_or_404(db, poc_id)
    # The strict check, not assert_can_work_on_poc: being on a team must not
    # let you enlarge that team. A channel-manager admin can only staff POCs
    # for the companies they manage.
    await assert_can_access_opportunity(db, admin, poc.opportunity)
    return await poc_team_service.add_member(
        db, poc_id, data.user_id, PocTeamRole(data.role), admin
    )


@router.put(
    "/{poc_id}/team/{user_id}",
    response_model=PocTeamMemberResponse,
    status_code=200,
)
async def change_poc_team_role(
    poc_id: int,
    user_id: int,
    data: PocTeamRoleUpdateRequest,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, admin, poc.opportunity)
    return await poc_team_service.change_role(
        db, poc_id, user_id, PocTeamRole(data.role), admin
    )


@router.delete("/{poc_id}/team/{user_id}", response_model=MessageResponse, status_code=200)
async def remove_poc_team_member(
    poc_id: int,
    user_id: int,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Take someone off the team. Their access ends immediately; the roster
    keeps the record that they were on it."""
    poc = await poc_service.get_poc_or_404(db, poc_id)
    await assert_can_access_opportunity(db, admin, poc.opportunity)
    await poc_team_service.remove_member(db, poc_id, user_id, admin)
    return MessageResponse(message="Removed from the POC team")


# ---------------------------------------------------------------------------
# Customer licences (post-PO)
# ---------------------------------------------------------------------------

@router.get("/licenses/list", status_code=200)
async def list_licenses(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None, pattern="^(pending_activation|active|expiring_soon|expired)$"),
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    items, total = await poc_service.list_licenses(
        db,
        page=page,
        page_size=page_size,
        status=status,
        search=search,
        **await _list_scope(db, current_user),
    )
    return {
        "items": [item.model_dump(mode="json") for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": math.ceil(total / page_size) if total > 0 else 0,
    }


@router.get("/licenses/by-opportunity/{opp_id}", response_model=Optional[LicenseResponse], status_code=200)
async def get_license_for_opportunity(
    opp_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Null when no PO has landed yet — the normal case for pipeline opps."""
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_work_on_poc(db, current_user, opp)

    lic = await poc_service.get_license_by_opportunity(db, opp_id)
    return poc_service.to_license_response(lic) if lic else None


@router.put("/licenses/by-opportunity/{opp_id}", response_model=LicenseResponse, status_code=200)
async def upsert_license(
    opp_id: int,
    data: LicenseUpsertRequest,
    user: User = Depends(get_poc_editor),
    db: AsyncSession = Depends(get_db),
):
    opp = await poc_service.get_opportunity_or_404(db, opp_id)
    await assert_can_work_on_poc(db, user, opp)
    return await poc_service.upsert_license(db, opp_id, data, user)
