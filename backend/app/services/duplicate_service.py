"""
Duplicate detection service for opportunities.

Responsibilities:
  - find_duplicates(...)  → main entrypoint, returns a structured report
  - get_review_queue(...) → list opportunities flagged as duplicates for
                            admin/channel-manager review
  - resolve_duplicate(...) → admin marks one of a pair as primary

The detection runs in 4 layers and combines their findings:
  1. EXACT match on (customer_name_normalized, country) — strong signal
  2. FUZZY match via pg_trgm similarity > 0.55 — catches typos / suffixes
  3. EXCLUSIVITY block — customer is in an active deal-registration
                          exclusivity window owned by another company
  4. OWNERSHIP block — customer is in customer_ownership pointing at a
                       different company

Severity levels:
  - "block"   → hard 409 Conflict on submission (exclusivity / ownership)
  - "warn"    → soft warning, flagged as multi_partner_alert (exact / fuzzy)
  - "info"    → AI-detected possible match (lower confidence)
"""
from datetime import date
from typing import Optional, List
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.customer_ownership import CustomerOwnership
from app.models.company import Company
from app.utils.customer_normalize import normalize_customer_name


# ---------------------------------------------------------------------------
# Result shapes (plain dicts so they serialize cleanly through FastAPI)
# ---------------------------------------------------------------------------

def _opp_summary(o: Opportunity, *, similarity: Optional[float] = None) -> dict:
    return {
        "id": o.id,
        "name": o.name,
        "customer_name": o.customer_name,
        "country": o.country,
        "city": o.city,
        "company_id": o.company_id,
        "company_name": o.company.name if o.company else None,
        "status": o.status.value if hasattr(o.status, "value") else o.status,
        "worth": str(o.worth) if o.worth is not None else None,
        "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "similarity": round(similarity, 3) if similarity is not None else None,
    }


# ---------------------------------------------------------------------------
# find_duplicates — main entrypoint
# ---------------------------------------------------------------------------

async def find_duplicates(
    db: AsyncSession,
    *,
    customer_name: str,
    country: str,
    city: Optional[str] = None,
    submitting_company_id: Optional[int] = None,
    customer_domain: Optional[str] = None,
    exclude_opportunity_id: Optional[int] = None,
    fuzzy_threshold: float = 0.55,
) -> dict:
    """
    Detect duplicates for a proposed opportunity.

    Returns a dict:
      {
        "severity": "block" | "warn" | "info" | "clear",
        "messages": [str, ...],
        "exact_matches":      [opp_summary, ...],
        "fuzzy_matches":      [opp_summary (with similarity), ...],
        "exclusivity_blocks": [{...}, ...],
        "ownership_blocks":   [{...}, ...],
        "domain_matches":     [opp_summary, ...],
      }

    Severity rules:
      - block if any exclusivity_blocks or ownership_blocks
      - warn  if any exact_matches or fuzzy_matches OR domain_matches
        from a DIFFERENT submitting_company
      - clear otherwise
    """
    normalized = normalize_customer_name(customer_name)
    if not normalized:
        return {
            "severity": "clear",
            "messages": [],
            "exact_matches": [],
            "fuzzy_matches": [],
            "exclusivity_blocks": [],
            "ownership_blocks": [],
            "domain_matches": [],
        }

    # Active opportunities to compare against
    base_filters = [
        Opportunity.deleted_at.is_(None),
        Opportunity.status.notin_([OpportunityStatus.REMOVED, OpportunityStatus.REJECTED]),
    ]
    if exclude_opportunity_id is not None:
        base_filters.append(Opportunity.id != exclude_opportunity_id)

    # ---- Layer 1: EXACT match -------------------------------------------
    exact_query = (
        select(Opportunity)
        .options(joinedload(Opportunity.company))
        .where(
            *base_filters,
            Opportunity.customer_name_normalized == normalized,
            Opportunity.country == country,
        )
        .order_by(Opportunity.created_at.desc())
        .limit(10)
    )
    exact_rows = (await db.execute(exact_query)).unique().scalars().all()
    exact_matches = [_opp_summary(o) for o in exact_rows]

    # ---- Layer 2: FUZZY match via pg_trgm similarity ---------------------
    # Only look in same country to keep it tight. Excludes anything already
    # in exact_matches.
    sim_col = func.similarity(Opportunity.customer_name_normalized, normalized)
    fuzzy_query = (
        select(Opportunity, sim_col.label("sim"))
        .options(joinedload(Opportunity.company))
        .where(
            *base_filters,
            Opportunity.country == country,
            Opportunity.customer_name_normalized.is_not(None),
            Opportunity.customer_name_normalized != normalized,  # exclude exact
            sim_col >= fuzzy_threshold,
        )
        .order_by(sim_col.desc())
        .limit(10)
    )
    fuzzy_rows = (await db.execute(fuzzy_query)).unique().all()
    fuzzy_matches = [_opp_summary(o, similarity=float(s)) for o, s in fuzzy_rows]

    # ---- Layer 3: DOMAIN matches ---------------------------------------
    domain_matches: List[dict] = []
    if customer_domain:
        domain_query = (
            select(Opportunity)
            .options(joinedload(Opportunity.company))
            .where(
                *base_filters,
                Opportunity.customer_domain == customer_domain.lower(),
            )
            .order_by(Opportunity.created_at.desc())
            .limit(10)
        )
        domain_rows = (await db.execute(domain_query)).unique().scalars().all()
        # Filter out anything we already saw
        seen_ids = {m["id"] for m in exact_matches} | {m["id"] for m in fuzzy_matches}
        domain_matches = [_opp_summary(o) for o in domain_rows if o.id not in seen_ids]

    # ---- Layer 4: EXCLUSIVITY block (active deal exclusivity windows) ---
    today = date.today()
    excl_query = (
        select(DealRegistration)
        .options(joinedload(DealRegistration.company))
        .where(
            DealRegistration.deleted_at.is_(None),
            DealRegistration.status == DealStatus.APPROVED,
            DealRegistration.exclusivity_start.is_not(None),
            DealRegistration.exclusivity_end.is_not(None),
            DealRegistration.exclusivity_start <= today,
            DealRegistration.exclusivity_end >= today,
        )
    )
    excl_rows = (await db.execute(excl_query)).unique().scalars().all()
    exclusivity_blocks = []
    for d in excl_rows:
        d_norm = normalize_customer_name(d.customer_name or "")
        if not d_norm:
            continue
        # block when name matches AND it's a DIFFERENT company submitting
        if d_norm == normalized and (
            submitting_company_id is None or submitting_company_id != d.company_id
        ):
            exclusivity_blocks.append({
                "deal_id": d.id,
                "company_id": d.company_id,
                "company_name": d.company.name if d.company else None,
                "customer_name": d.customer_name,
                "exclusivity_start": str(d.exclusivity_start),
                "exclusivity_end": str(d.exclusivity_end),
            })

    # ---- Layer 5: OWNERSHIP block (customer_ownership table) ------------
    ownership_query = (
        select(CustomerOwnership)
        .options(joinedload(CustomerOwnership.company))
        .where(
            CustomerOwnership.is_active.is_(True),
            CustomerOwnership.customer_name_normalized == normalized,
            CustomerOwnership.country == country,
        )
    )
    own_rows = (await db.execute(ownership_query)).unique().scalars().all()
    ownership_blocks = []
    for o in own_rows:
        # block when ownership belongs to a DIFFERENT company
        if submitting_company_id is None or submitting_company_id != o.company_id:
            # Skip expired
            if o.valid_until and o.valid_until < today:
                continue
            ownership_blocks.append({
                "ownership_id": o.id,
                "company_id": o.company_id,
                "company_name": o.company.name if o.company else None,
                "valid_from": str(o.valid_from),
                "valid_until": str(o.valid_until) if o.valid_until else None,
            })

    # ---- Compute severity + human-readable messages ---------------------
    messages: list[str] = []
    if exclusivity_blocks:
        for b in exclusivity_blocks:
            messages.append(
                f"⛔ {b['company_name']} has an exclusive deal registration on "
                f"\"{b['customer_name']}\" until {b['exclusivity_end']}."
            )
    if ownership_blocks:
        for b in ownership_blocks:
            messages.append(
                f"⛔ This customer is currently owned by {b['company_name']} "
                f"(valid until {b['valid_until'] or 'indefinitely'})."
            )
    if exact_matches:
        partner_owned = [m for m in exact_matches if m["company_id"] != submitting_company_id]
        if partner_owned:
            for m in partner_owned[:3]:
                messages.append(
                    f"⚠ {m['company_name']} already has \"{m['customer_name']}\" "
                    f"in {m['status'].replace('_', ' ')} status."
                )
    if fuzzy_matches:
        partner_owned_fuzzy = [m for m in fuzzy_matches if m["company_id"] != submitting_company_id]
        for m in partner_owned_fuzzy[:3]:
            messages.append(
                f"⚠ Similar customer \"{m['customer_name']}\" registered by "
                f"{m['company_name']} (similarity: {int(m['similarity'] * 100)}%)"
            )
    if domain_matches:
        for m in domain_matches[:2]:
            if m["company_id"] != submitting_company_id:
                messages.append(
                    f"⚠ Domain match: {m['company_name']} has an opportunity for "
                    f"the same customer domain (\"{m['customer_name']}\")"
                )

    severity = "clear"
    if exclusivity_blocks or ownership_blocks:
        severity = "block"
    elif (
        any(m["company_id"] != submitting_company_id for m in exact_matches)
        or any(m["company_id"] != submitting_company_id for m in fuzzy_matches)
        or any(m["company_id"] != submitting_company_id for m in domain_matches)
    ):
        severity = "warn"

    return {
        "severity": severity,
        "messages": messages,
        "exact_matches": exact_matches,
        "fuzzy_matches": fuzzy_matches,
        "exclusivity_blocks": exclusivity_blocks,
        "ownership_blocks": ownership_blocks,
        "domain_matches": domain_matches,
    }


# ---------------------------------------------------------------------------
# Customer ownership lifecycle
# ---------------------------------------------------------------------------

async def upsert_ownership_from_deal(
    db: AsyncSession,
    deal: DealRegistration,
) -> None:
    """Insert / refresh a CustomerOwnership row when a deal is approved.

    Idempotent: if an active row already exists for the same
    (normalized name, country, company), it just extends valid_until.
    """
    if not deal.exclusivity_end:
        return
    normalized = normalize_customer_name(deal.customer_name or "")
    if not normalized:
        return

    existing_q = select(CustomerOwnership).where(
        CustomerOwnership.customer_name_normalized == normalized,
        CustomerOwnership.country == "",  # we'll fill below
        CustomerOwnership.company_id == deal.company_id,
        CustomerOwnership.is_active.is_(True),
    )
    # Country comes from the company since deal_registration doesn't store it
    company = (await db.execute(select(Company).where(Company.id == deal.company_id))).scalar_one_or_none()
    country = company.country if company else "Unknown"

    existing = (await db.execute(
        select(CustomerOwnership).where(
            CustomerOwnership.customer_name_normalized == normalized,
            CustomerOwnership.country == country,
            CustomerOwnership.company_id == deal.company_id,
            CustomerOwnership.is_active.is_(True),
        )
    )).scalar_one_or_none()

    if existing:
        # Extend if the new deal pushes valid_until further out
        if deal.exclusivity_end > (existing.valid_until or date.min):
            existing.valid_until = deal.exclusivity_end
            existing.source_deal_id = deal.id
        await db.flush()
        return

    db.add(CustomerOwnership(
        customer_name_normalized=normalized,
        country=country,
        company_id=deal.company_id,
        source_deal_id=deal.id,
        valid_from=deal.exclusivity_start or date.today(),
        valid_until=deal.exclusivity_end,
        is_active=True,
    ))
    await db.flush()


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------

async def get_review_queue(
    db: AsyncSession,
    *,
    scope_company_ids: Optional[list[int]] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int]:
    """Return opportunities flagged as possible duplicates that need admin
    review. An opportunity is in the queue if either:
      - multi_partner_alert = True (set by find_duplicates at submission)
      - ai_duplicate_of_id IS NOT NULL (set by the AI background task)

    Channel-manager scope filters to opportunities for managed companies.
    """
    filters = [
        Opportunity.deleted_at.is_(None),
        Opportunity.status.notin_([OpportunityStatus.REMOVED, OpportunityStatus.REJECTED]),
        or_(
            Opportunity.multi_partner_alert.is_(True),
            Opportunity.ai_duplicate_of_id.is_not(None),
        ),
    ]
    if scope_company_ids is not None:
        filters.append(Opportunity.company_id.in_(scope_company_ids))

    count_q = select(func.count(Opportunity.id)).where(*filters)
    total = (await db.execute(count_q)).scalar() or 0

    query = (
        select(Opportunity)
        .options(joinedload(Opportunity.company))
        .where(*filters)
        .order_by(Opportunity.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(query)).unique().scalars().all()

    items = []
    for o in rows:
        # Find the matched-against opportunity (either AI link or top exact match)
        matched: Optional[dict] = None
        if o.ai_duplicate_of_id:
            other = (await db.execute(
                select(Opportunity)
                .options(joinedload(Opportunity.company))
                .where(Opportunity.id == o.ai_duplicate_of_id)
            )).unique().scalar_one_or_none()
            if other:
                matched = _opp_summary(other)
        if not matched and o.customer_name_normalized:
            other = (await db.execute(
                select(Opportunity)
                .options(joinedload(Opportunity.company))
                .where(
                    Opportunity.id != o.id,
                    Opportunity.customer_name_normalized == o.customer_name_normalized,
                    Opportunity.country == o.country,
                    Opportunity.deleted_at.is_(None),
                    Opportunity.status.notin_([OpportunityStatus.REMOVED, OpportunityStatus.REJECTED]),
                )
                .limit(1)
            )).unique().scalar_one_or_none()
            if other:
                matched = _opp_summary(other)

        items.append({
            "opportunity": _opp_summary(o),
            "matched_against": matched,
            "flagged_by": (
                "ai" if o.ai_duplicate_of_id else "system"
            ),
        })

    return items, total
