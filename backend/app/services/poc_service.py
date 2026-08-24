"""POC and post-PO licence tracking.

Status is *derived*, never taken from the client — see derive_status /
derive_license_status. Both are pure functions so the rules stay testable and
there is exactly one definition of "running" or "expired" in the codebase.
"""
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, func, case, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    NotFoundException,
)
from app.models.customer_license import (
    CustomerLicense,
    LicenseStatus,
    EXPIRING_SOON_DAYS,
)
from app.models.opportunity import Opportunity
from app.models.poc import Poc, PocStatus, POC_STAGE_KEYS, POC_STAGE_LABELS
from app.models.poc_team import PocTeamMember
from app.models.user import User
from app.schemas.poc import (
    LicenseResponse,
    LicenseUpsertRequest,
    PocCloseRequest,
    PocResponse,
    PocStageState,
    PocStartRequest,
    PocUpdateRequest,
)
from app.services import poc_team_service
from app.utils.audit import write_audit_log


# ---------------------------------------------------------------------------
# Derivation rules
# ---------------------------------------------------------------------------

def derive_status(poc: Poc) -> PocStatus:
    """A POC's status follows from its data:

      - closed_at set  → whatever outcome it was closed with (terminal)
      - VM allocated   → running
      - otherwise      → not_started

    Completing all five stages does NOT close a POC. "The technical work is
    finished" and "the customer accepted it" are different facts, and only a
    human knows the second one.
    """
    if poc.closed_at is not None:
        # Terminal — preserve the outcome the closer recorded.
        if poc.status in (PocStatus.SUCCESSFUL, PocStatus.UNSUCCESSFUL):
            return poc.status
        return PocStatus.SUCCESSFUL
    if poc.vm_provisioning_completed_at is not None:
        return PocStatus.RUNNING
    return PocStatus.NOT_STARTED


def license_status_expr(today: Optional[date] = None):
    """`derive_license_status` expressed as SQL.

    Licence status is time-dependent: a row written today as EXPIRING_SOON is
    EXPIRED two months later with no write in between. The stored `status`
    column is therefore only ever a cache of what was true when it was last
    saved, and grouping or filtering on it directly returns stale answers.

    Every query that groups/filters by licence status must use this expression
    instead of the column, and every read path must use derive_license_status.
    Keep the two in lockstep — they encode the same rule twice, once for
    Python and once for Postgres.
    """
    today = today or datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=EXPIRING_SOON_DAYS)
    return case(
        (CustomerLicense.license_activated_at.is_(None), LicenseStatus.PENDING_ACTIVATION.value),
        (CustomerLicense.license_activated_at > today, LicenseStatus.PENDING_ACTIVATION.value),
        (CustomerLicense.license_expires_at.is_(None), LicenseStatus.ACTIVE.value),
        (CustomerLicense.license_expires_at < today, LicenseStatus.EXPIRED.value),
        # (expires - today).days <= N  <=>  expires <= today + N days
        (CustomerLicense.license_expires_at <= cutoff, LicenseStatus.EXPIRING_SOON.value),
        else_=LicenseStatus.ACTIVE.value,
    )


def derive_license_status(lic: CustomerLicense, today: Optional[date] = None) -> LicenseStatus:
    """Licence status follows from the activation/expiry dates.

    Derived on every read (see to_license_response) rather than trusted from
    the stored column, so a licence can never render as ACTIVE while its
    expiry is in the past. Mirrored in SQL by license_status_expr.
    """
    today = today or datetime.now(timezone.utc).date()

    if lic.license_activated_at is None:
        return LicenseStatus.PENDING_ACTIVATION
    if lic.license_activated_at > today:
        # Activation scheduled for the future.
        return LicenseStatus.PENDING_ACTIVATION
    if lic.license_expires_at is None:
        # Perpetual licence.
        return LicenseStatus.ACTIVE
    if lic.license_expires_at < today:
        return LicenseStatus.EXPIRED
    if (lic.license_expires_at - today).days <= EXPIRING_SOON_DAYS:
        return LicenseStatus.EXPIRING_SOON
    return LicenseStatus.ACTIVE


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _stage_states(poc: Poc) -> list[PocStageState]:
    return [
        PocStageState(
            key=key,
            label=POC_STAGE_LABELS[key],
            completed=getattr(poc, f"{key}_completed_at") is not None,
            completed_at=getattr(poc, f"{key}_completed_at"),
        )
        for key in POC_STAGE_KEYS
    ]


def to_poc_response(poc: Poc) -> PocResponse:
    """Serialise a POC. The caller must have eager-loaded .opportunity (and
    its .company / .sales_rep) and .team_members (with their .user) — we never
    lazy-load here, since an implicit async lazy-load raises MissingGreenlet
    outside the greenlet context. _poc_query() sets all of that up.
    """
    opp = poc.opportunity
    today = datetime.now(timezone.utc).date()

    days_running: Optional[int] = None
    if poc.start_date is not None:
        end = poc.end_date or today
        days_running = (end - poc.start_date).days

    # Overdue = still open, past its target date. A closed POC is never
    # overdue, however late it finished.
    is_overdue = (
        poc.closed_at is None
        and poc.target_end_date is not None
        and poc.target_end_date < today
    )

    current = poc.current_stage

    return PocResponse(
        id=poc.id,
        opportunity_id=poc.opportunity_id,
        status=poc.status.value if hasattr(poc.status, "value") else str(poc.status),
        start_date=poc.start_date,
        target_end_date=poc.target_end_date,
        end_date=poc.end_date,
        vm_provisioning_completed_at=poc.vm_provisioning_completed_at,
        deployment_completed_at=poc.deployment_completed_at,
        device_onboarding_completed_at=poc.device_onboarding_completed_at,
        dashboarding_completed_at=poc.dashboarding_completed_at,
        fine_tuning_completed_at=poc.fine_tuning_completed_at,
        closed_at=poc.closed_at,
        outcome_notes=poc.outcome_notes,
        failure_reason=poc.failure_reason,
        notes=poc.notes,
        stages=_stage_states(poc),
        completed_stage_count=poc.completed_stage_count,
        total_stage_count=len(POC_STAGE_KEYS),
        current_stage=current,
        current_stage_label=POC_STAGE_LABELS[current] if current else None,
        days_running=days_running,
        is_overdue=is_overdue,
        opportunity_name=opp.name if opp else None,
        customer_name=opp.customer_name if opp else None,
        company_name=opp.company.name if opp and opp.company else None,
        partner_name=opp.company.name if opp and opp.company else None,
        country=opp.country if opp else None,
        city=opp.city if opp else None,
        region=opp.region if opp else None,
        product=opp.product if opp else None,
        worth=opp.worth if opp else None,
        sales_rep_name=opp.sales_rep.full_name if opp and opp.sales_rep else None,
        closed_by_name=poc.closed_by_user.full_name if poc.closed_by_user else None,
        # Current roster only. Removed members stay in the relationship so the
        # history survives, but they are not on the team today and must not
        # appear as though they are; the team-history endpoint is where those
        # rows surface.
        team=[
            poc_team_service.to_team_member_response(m)
            for m in sorted(poc.team_members, key=lambda m: m.assigned_at)
            if m.removed_at is None
        ],
        created_at=poc.created_at,
        updated_at=poc.updated_at,
    )


def to_license_response(lic: CustomerLicense) -> LicenseResponse:
    opp = lic.opportunity
    return LicenseResponse(
        id=lic.id,
        opportunity_id=lic.opportunity_id,
        po_number=lic.po_number,
        po_received_date=lic.po_received_date,
        po_value=lic.po_value,
        device_count=lic.device_count,
        node_count=lic.node_count,
        license_activated_at=lic.license_activated_at,
        license_expires_at=lic.license_expires_at,
        license_key=lic.license_key,
        # Derived, never the stored column — see license_status_expr. The
        # column is a save-time cache and goes stale as dates pass.
        status=derive_license_status(lic).value,
        notes=lic.notes,
        days_until_expiry=lic.days_until_expiry,
        opportunity_name=opp.name if opp else None,
        customer_name=opp.customer_name if opp else None,
        company_name=opp.company.name if opp and opp.company else None,
        country=opp.country if opp else None,
        product=opp.product if opp else None,
        created_at=lic.created_at,
        updated_at=lic.updated_at,
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def poc_access_clause(
    scope_company_ids: Optional[list[int]],
    sales_rep_id: Optional[int],
    team_member_id: Optional[int],
):
    """The SQL for "which opportunities' POC records may this caller see", or
    None for unscoped. Constrains Opportunity, so it drops into both the POC
    list and the licence list.

    The three arguments are alternative *grounds* for access and are OR'd, not
    AND'd — a sales rep sees the POCs of opportunities assigned to them plus
    any POC they were added to the team of, and a channel-manager admin sees
    their companies' POCs plus the same. Callers pass the grounds that apply
    to one caller, never a mix meant as a narrowing filter; user-supplied
    filters (status, country, company_id) AND on top of whatever this returns.

    `scope_company_ids=[]` — a channel manager who manages nothing — must
    contribute an impossible term rather than being dropped, which is why this
    tests `is not None` rather than truthiness. It still ORs with team
    membership, so such an admin sees exactly the POCs they were put on.

    An argument left as None means "this ground does not apply to this
    caller", never "unrestricted". A caller who should see everything (a
    superadmin) passes *no* grounds and gets None back; passing them a
    team_member_id and nothing else would OR one term onto an otherwise empty
    set and narrow them to their own POCs, which is the opposite of intended.
    """
    terms = []
    if scope_company_ids is not None:
        terms.append(Opportunity.company_id.in_(scope_company_ids))
    if sales_rep_id is not None:
        terms.append(Opportunity.sales_rep_id == sales_rep_id)
    if team_member_id is not None:
        # Expressed against Opportunity rather than Poc so the same clause
        # works for the licence list, which joins Opportunity but not Poc.
        terms.append(
            Opportunity.id.in_(
                select(Poc.opportunity_id)
                .join(PocTeamMember, PocTeamMember.poc_id == Poc.id)
                .where(
                    PocTeamMember.user_id == team_member_id,
                    PocTeamMember.removed_at.is_(None),
                    Poc.deleted_at.is_(None),
                )
            )
        )
    if not terms:
        return None
    return or_(*terms)


def _poc_query():
    return select(Poc).options(
        joinedload(Poc.opportunity).joinedload(Opportunity.company),
        joinedload(Poc.opportunity).joinedload(Opportunity.sales_rep),
        joinedload(Poc.closed_by_user),
        # selectinload, not joinedload: team_members is a collection, and a
        # joined one would multiply rows under the LIMIT/OFFSET in list_pocs.
        # This is one extra IN query for the whole page.
        selectinload(Poc.team_members).joinedload(PocTeamMember.user),
        selectinload(Poc.team_members).joinedload(PocTeamMember.assigned_by_user),
    ).where(Poc.deleted_at.is_(None))


def _license_query():
    return select(CustomerLicense).options(
        joinedload(CustomerLicense.opportunity).joinedload(Opportunity.company),
    ).where(CustomerLicense.deleted_at.is_(None))


async def get_opportunity_or_404(db: AsyncSession, opp_id: int) -> Opportunity:
    result = await db.execute(
        select(Opportunity)
        .options(
            joinedload(Opportunity.company),
            joinedload(Opportunity.sales_rep),
        )
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")
    return opp


async def get_poc_by_opportunity(db: AsyncSession, opp_id: int) -> Optional[Poc]:
    result = await db.execute(_poc_query().where(Poc.opportunity_id == opp_id))
    return result.unique().scalar_one_or_none()


async def get_poc_or_404(db: AsyncSession, poc_id: int) -> Poc:
    result = await db.execute(_poc_query().where(Poc.id == poc_id))
    poc = result.unique().scalar_one_or_none()
    if not poc:
        raise NotFoundException(code="POC_NOT_FOUND", message="POC not found")
    return poc


async def list_pocs(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    country: Optional[str] = None,
    company_id: Optional[int] = None,
    search: Optional[str] = None,
    scope_company_ids: Optional[list[int]] = None,
    sales_rep_id: Optional[int] = None,
    team_member_id: Optional[int] = None,
) -> tuple[list[PocResponse], int]:
    query = _poc_query().join(Opportunity, Poc.opportunity_id == Opportunity.id)
    count_query = (
        select(func.count(Poc.id))
        .join(Opportunity, Poc.opportunity_id == Opportunity.id)
        .where(Poc.deleted_at.is_(None))
    )

    def both(clause):
        nonlocal query, count_query
        query = query.where(clause)
        count_query = count_query.where(clause)

    both(Opportunity.deleted_at.is_(None))

    if status:
        both(Poc.status == status)
    if country:
        both(Opportunity.country == country)
    if company_id:
        both(Opportunity.company_id == company_id)
    if search:
        both(Opportunity.customer_name.ilike(f"%{search}%"))
    # Who may see which POC — channel-manager scope, own assignment, and POC
    # team membership, OR'd. See poc_access_clause for why an empty scope list
    # must still produce a term.
    access = poc_access_clause(scope_company_ids, sales_rep_id, team_member_id)
    if access is not None:
        both(access)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(Poc.start_date.desc().nullslast(), Poc.created_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    pocs = result.unique().scalars().all()

    return [to_poc_response(p) for p in pocs], total


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

async def start_poc(
    db: AsyncSession, opp_id: int, data: PocStartRequest, user: User
) -> PocResponse:
    """Start a POC — i.e. record the VM allocation. Creates the record if it
    doesn't exist yet."""
    await get_opportunity_or_404(db, opp_id)

    existing = await get_poc_by_opportunity(db, opp_id)
    if existing and existing.vm_provisioning_completed_at is not None:
        raise ConflictException(
            code="POC_ALREADY_STARTED",
            message="This opportunity's POC has already been started",
        )

    if data.target_end_date and data.target_end_date < data.start_date:
        raise BadRequestException(
            code="INVALID_DATE_RANGE",
            message="Target end date cannot be before the start date",
        )

    poc = existing or Poc(opportunity_id=opp_id)
    poc.start_date = data.start_date
    # Starting the POC *is* completing VM provisioning — they're the same
    # event, so we never let the two dates drift apart.
    poc.vm_provisioning_completed_at = data.start_date
    poc.target_end_date = data.target_end_date
    if data.notes is not None:
        poc.notes = data.notes
    poc.status = derive_status(poc)

    if existing is None:
        db.add(poc)
    await db.flush()

    await write_audit_log(db, user.id, "START", "poc", poc.id, {
        "opportunity_id": opp_id, "start_date": str(data.start_date),
    })
    await db.commit()

    return to_poc_response(await get_poc_or_404(db, poc.id))


async def update_poc(
    db: AsyncSession, poc_id: int, data: PocUpdateRequest, user: User
) -> PocResponse:
    poc = await get_poc_or_404(db, poc_id)
    if poc.closed_at is not None:
        raise ConflictException(
            code="POC_CLOSED",
            message="This POC is closed and can no longer be edited",
        )

    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(poc, field, value)

    # Keep start_date and VM provisioning in lockstep — the POC starts on VM
    # allocation by definition.
    if "vm_provisioning_completed_at" in payload:
        poc.start_date = poc.vm_provisioning_completed_at

    _validate_stage_dates(poc)
    poc.status = derive_status(poc)
    await db.flush()

    await write_audit_log(db, user.id, "UPDATE", "poc", poc.id, payload_safe(payload))
    await db.commit()

    return to_poc_response(await get_poc_or_404(db, poc_id))


async def set_stage(
    db: AsyncSession, poc_id: int, stage_key: str, completed_at: Optional[date], user: User
) -> PocResponse:
    """Mark one stage complete (or clear it). Stages are independent, so
    completing #3 before #2 is allowed — real POCs do run out of order."""
    if stage_key not in POC_STAGE_KEYS:
        raise BadRequestException(
            code="UNKNOWN_STAGE",
            message=f"Unknown POC stage '{stage_key}'. Expected one of: {', '.join(POC_STAGE_KEYS)}",
        )

    poc = await get_poc_or_404(db, poc_id)
    if poc.closed_at is not None:
        raise ConflictException(
            code="POC_CLOSED",
            message="This POC is closed and can no longer be edited",
        )

    setattr(poc, f"{stage_key}_completed_at", completed_at)
    if stage_key == "vm_provisioning":
        # VM provisioning is the POC start; clearing it un-starts the POC.
        poc.start_date = completed_at

    _validate_stage_dates(poc)
    poc.status = derive_status(poc)
    await db.flush()

    await write_audit_log(db, user.id, "STAGE_UPDATE", "poc", poc.id, {
        "stage": stage_key,
        "completed_at": str(completed_at) if completed_at else None,
    })
    await db.commit()

    return to_poc_response(await get_poc_or_404(db, poc_id))


async def close_poc(
    db: AsyncSession, poc_id: int, data: PocCloseRequest, user: User
) -> PocResponse:
    poc = await get_poc_or_404(db, poc_id)

    if poc.vm_provisioning_completed_at is None:
        raise BadRequestException(
            code="POC_NOT_STARTED",
            message="Cannot close a POC that has not been started",
        )
    if poc.closed_at is not None:
        raise ConflictException(
            code="POC_ALREADY_CLOSED",
            message="This POC is already closed",
        )

    end = data.end_date or datetime.now(timezone.utc).date()
    if poc.start_date and end < poc.start_date:
        raise BadRequestException(
            code="INVALID_DATE_RANGE",
            message="End date cannot be before the POC start date",
        )

    poc.end_date = end
    poc.closed_at = datetime.now(timezone.utc)
    poc.closed_by = user.id
    poc.status = PocStatus.SUCCESSFUL if data.successful else PocStatus.UNSUCCESSFUL
    poc.outcome_notes = data.outcome_notes
    # failure_reason is meaningless on a successful POC — drop it rather than
    # persist a stale reason from a previous attempt.
    poc.failure_reason = data.failure_reason if not data.successful else None

    await db.flush()
    await write_audit_log(db, user.id, "CLOSE", "poc", poc.id, {
        "successful": data.successful, "end_date": str(end),
    })
    await db.commit()

    return to_poc_response(await get_poc_or_404(db, poc_id))


async def reopen_poc(db: AsyncSession, poc_id: int, user: User) -> PocResponse:
    """Undo a close — for when a POC was closed by mistake."""
    poc = await get_poc_or_404(db, poc_id)
    if poc.closed_at is None:
        raise ConflictException(code="POC_NOT_CLOSED", message="This POC is not closed")

    poc.closed_at = None
    poc.closed_by = None
    poc.end_date = None
    poc.outcome_notes = None
    poc.failure_reason = None
    poc.status = derive_status(poc)

    await db.flush()
    await write_audit_log(db, user.id, "REOPEN", "poc", poc.id, {})
    await db.commit()

    return to_poc_response(await get_poc_or_404(db, poc_id))


def _validate_stage_dates(poc: Poc) -> None:
    """No stage may be completed before the POC started. Stages may complete
    out of order relative to each other, so we deliberately don't enforce
    ordering between them."""
    if poc.start_date is None:
        return
    for key in POC_STAGE_KEYS:
        value = getattr(poc, f"{key}_completed_at")
        if value is not None and value < poc.start_date:
            raise BadRequestException(
                code="STAGE_BEFORE_START",
                message=(
                    f"'{POC_STAGE_LABELS[key]}' cannot be completed "
                    f"({value}) before the POC started ({poc.start_date})"
                ),
            )


def payload_safe(payload: dict) -> dict:
    """Audit payloads must be JSON-serialisable; dates are not."""
    return {k: (str(v) if isinstance(v, (date, datetime)) else v) for k, v in payload.items()}


# ---------------------------------------------------------------------------
# Licences (post-PO)
# ---------------------------------------------------------------------------

async def get_license_by_opportunity(db: AsyncSession, opp_id: int) -> Optional[CustomerLicense]:
    result = await db.execute(
        _license_query().where(CustomerLicense.opportunity_id == opp_id)
    )
    return result.unique().scalar_one_or_none()


async def upsert_license(
    db: AsyncSession, opp_id: int, data: LicenseUpsertRequest, user: User
) -> LicenseResponse:
    """Create or update the licence record for an opportunity. Upsert rather
    than separate create/update because the UI is a single form that gets
    filled in progressively as the PO, activation, and expiry land."""
    await get_opportunity_or_404(db, opp_id)

    lic = await get_license_by_opportunity(db, opp_id)
    created = lic is None
    if lic is None:
        lic = CustomerLicense(opportunity_id=opp_id)
        db.add(lic)

    payload = data.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(lic, field, value)

    if (
        lic.license_activated_at
        and lic.license_expires_at
        and lic.license_expires_at < lic.license_activated_at
    ):
        raise BadRequestException(
            code="INVALID_DATE_RANGE",
            message="Licence expiry cannot be before its activation date",
        )

    lic.status = derive_license_status(lic)
    await db.flush()

    await write_audit_log(
        db, user.id, "CREATE" if created else "UPDATE", "customer_license", lic.id,
        {"opportunity_id": opp_id, **payload_safe(payload)},
    )
    await db.commit()

    refreshed = await get_license_by_opportunity(db, opp_id)
    return to_license_response(refreshed)


async def list_licenses(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    search: Optional[str] = None,
    scope_company_ids: Optional[list[int]] = None,
    sales_rep_id: Optional[int] = None,
    team_member_id: Optional[int] = None,
) -> tuple[list[LicenseResponse], int]:
    query = _license_query().join(
        Opportunity, CustomerLicense.opportunity_id == Opportunity.id
    )
    count_query = (
        select(func.count(CustomerLicense.id))
        .join(Opportunity, CustomerLicense.opportunity_id == Opportunity.id)
        .where(CustomerLicense.deleted_at.is_(None))
    )

    def both(clause):
        nonlocal query, count_query
        query = query.where(clause)
        count_query = count_query.where(clause)

    both(Opportunity.deleted_at.is_(None))

    if status:
        # Against the derived expression, not CustomerLicense.status — the
        # column is stale for any licence whose dates have since passed.
        both(license_status_expr() == status)
    if search:
        both(Opportunity.customer_name.ilike(f"%{search}%"))
    # Same three grounds as the POC list. A team member can edit the licence
    # for their POC's opportunity (pocs.upsert_license goes through
    # assert_can_work_on_poc), so the list has to show it to them — a list
    # narrower than the per-record check is how dead ends get built.
    access = poc_access_clause(scope_company_ids, sales_rep_id, team_member_id)
    if access is not None:
        both(access)

    total = (await db.execute(count_query)).scalar() or 0

    query = query.order_by(CustomerLicense.license_expires_at.asc().nullslast())
    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    rows = result.unique().scalars().all()

    return [to_license_response(r) for r in rows], total


async def refresh_license_statuses(db: AsyncSession) -> int:
    """Re-sync the cached `status` column with today's dates.

    Not required for correctness: every read derives status via
    derive_license_status and every query groups/filters via
    license_status_expr, so nothing user-facing depends on this running.
    It exists so the raw column is sane for anyone querying the table
    directly (psql, BI tools, a future export). Runs daily via the
    _license_status_refresher background task started in app.main's lifespan.
    """
    result = await db.execute(
        select(CustomerLicense).where(CustomerLicense.deleted_at.is_(None))
    )
    changed = 0
    for lic in result.scalars().all():
        new_status = derive_license_status(lic)
        if lic.status != new_status:
            lic.status = new_status
            changed += 1
    if changed:
        await db.commit()
    return changed
