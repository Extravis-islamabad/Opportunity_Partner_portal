"""
Excel importer for the Extravis 2027 Target Plan.

Reads the 11-column workbook (Customer / Partner / Extravis Team / City /
Country / Industry / Progress / Product / Price / Time Frame) and creates:

  * Extravis admin users (channel managers) — one per "Extravis Team" name
  * Partner companies — one per "Partner" name
  * A generic partner user per company (so opportunities have a submitter)
  * Opportunities — one per data row

Idempotent: re-running matches existing entities by email / company name
and skips them. Safe to run after the production wipe and against an
already-seeded database.

Usage (inside the backend container):
    python -m app.core.seed_excel /app/uploads/2027_target_plan.xlsx
    python -m app.core.seed_excel /app/uploads/2027_target_plan.xlsx --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import re
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional

from openpyxl import load_workbook
from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.company import Company, CompanyStatus, CompanyType, PartnerTier
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.user import User, UserRole, UserStatus
from app.utils.audit import write_audit_log
from app.utils.customer_normalize import normalize_customer_name

DEFAULT_PASSWORD = "Demo@1234"
NOW = datetime.now(timezone.utc)

EXTRAVIS_TEAM = {
    "Owais":     {"email": "owais@extravis.com",     "full_name": "Owais Sajid",      "job_title": "Channel Sales Manager"},
    "Samikshya": {"email": "samikshya@extravis.com", "full_name": "Samikshya Rai",    "job_title": "Channel Sales Manager"},
    "Mukarram":  {"email": "mukarram@extravis.com",  "full_name": "Mukarram Hussain", "job_title": "Channel Sales Manager"},
    "Ahmed":     {"email": "ahmed@extravis.com",     "full_name": "Ahmed Raza",       "job_title": "Channel Sales Manager"},
}

# Map a Country string to the region varchar we put on companies / opps.
REGION_BY_COUNTRY = {
    "Pakistan": "MEA",
    "UAE": "MEA",
    "United Arab Emirates": "MEA",
    "Saudi Arabia": "MEA",
}

# Progress (0.1 → 1.0) → OpportunityStatus mapping. The stage descriptions
# come from the legend at the bottom of the workbook.
def progress_to_status(progress: float) -> OpportunityStatus:
    if progress <= 0.15:
        return OpportunityStatus.DRAFT
    if progress <= 0.35:
        return OpportunityStatus.PENDING_REVIEW
    if progress <= 0.65:
        return OpportunityStatus.UNDER_REVIEW
    return OpportunityStatus.APPROVED


def progress_label(progress: float) -> str:
    if progress <= 0.15: return "Raw Lead"
    if progress <= 0.35: return "POC Engaged / Tender Specs"
    if progress <= 0.65: return "POC Successful / Budget Approved"
    if progress <= 0.75: return "Price Submitted / Negotiation"
    if progress <= 0.95: return "PO Received"
    return "Payment Received"


# Quarter strings like "Q3 - 2027" → quarter-end date.
_QUARTER_RE = re.compile(r"Q\s*([1-4])\s*-\s*(\d{4})", re.IGNORECASE)
_QUARTER_END = {1: (3, 31), 2: (6, 30), 3: (9, 30), 4: (12, 31)}


def time_frame_to_date(value: object) -> date:
    if value is None:
        return date(2027, 12, 31)
    m = _QUARTER_RE.search(str(value))
    if not m:
        return date(2027, 12, 31)
    q, year = int(m.group(1)), int(m.group(2))
    mo, day = _QUARTER_END[q]
    return date(year, mo, day)


def company_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")


def clean(value: object) -> str:
    return str(value).strip() if value is not None else ""


# ---------------------------------------------------------------------------
# Workbook parsing
# ---------------------------------------------------------------------------

EXPECTED = [
    "S.No", "Customer", "Partner", "Extravis Team", "City", "Country",
    "Industry", "Progress", "Product", "Price", "Time Frame",
]


def parse_rows(path: Path) -> list[dict]:
    wb = load_workbook(filename=path, read_only=True, data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    header = [clean(h) for h in rows[0]]
    idx = {name: header.index(name) for name in EXPECTED if name in header}
    missing = [c for c in EXPECTED if c not in idx]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    out: list[dict] = []
    for raw in rows[1:]:
        sno = raw[idx["S.No"]]
        if sno is None:
            # Legend / blank rows at the bottom
            continue
        customer = clean(raw[idx["Customer"]])
        partner  = clean(raw[idx["Partner"]])
        team     = clean(raw[idx["Extravis Team"]])
        if not customer or not partner or not team:
            continue
        try:
            progress = float(raw[idx["Progress"]]) if raw[idx["Progress"]] is not None else 0.1
        except (TypeError, ValueError):
            progress = 0.1
        try:
            price = Decimal(str(raw[idx["Price"]] or 0)).quantize(Decimal("0.01"))
        except Exception:
            price = Decimal("0.00")
        out.append({
            "customer": customer,
            "partner":  partner,
            "team":     team,
            "city":     clean(raw[idx["City"]]) or "Unknown",
            "country":  clean(raw[idx["Country"]]).rstrip() or "Unknown",
            "industry": clean(raw[idx["Industry"]]).rstrip() or "Other",
            "progress": progress,
            "product":  clean(raw[idx["Product"]]) or "MonetX",
            "price":    price,
            "time_frame": clean(raw[idx["Time Frame"]]) or "Q4 - 2027",
        })
    return out


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------

async def get_superadmin(db) -> User:
    res = await db.execute(select(User).where(User.email == "admin@extravis.com"))
    user = res.scalar_one_or_none()
    if user is None:
        raise RuntimeError("Bootstrap superadmin admin@extravis.com is missing — run init_db first.")
    return user


async def ensure_team(db) -> dict[str, User]:
    """One ADMIN user per Extravis Team name. Idempotent by email."""
    out: dict[str, User] = {}
    for key, spec in EXTRAVIS_TEAM.items():
        res = await db.execute(select(User).where(User.email == spec["email"]))
        u = res.scalar_one_or_none()
        if u is None:
            u = User(
                email=spec["email"],
                full_name=spec["full_name"],
                job_title=spec["job_title"],
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=UserRole.ADMIN,
                status=UserStatus.ACTIVE,
                is_superadmin=False,
                has_completed_onboarding=True,
            )
            db.add(u)
            await db.flush()
        out[key] = u
    return out


async def ensure_companies(
    db, rows: list[dict], team: dict[str, User], superadmin: User
) -> dict[str, Company]:
    """One Company per unique 'Partner' name. Country/City/Industry/Channel
    manager are taken from the first row that mentions the partner."""
    companies: dict[str, Company] = {}
    for r in rows:
        partner = r["partner"]
        if partner in companies:
            continue
        res = await db.execute(select(Company).where(Company.name == partner))
        c = res.scalar_one_or_none()
        if c is None:
            cm = team.get(r["team"], superadmin)
            country = r["country"] or "Pakistan"
            c = Company(
                name=partner,
                country=country,
                region=REGION_BY_COUNTRY.get(country, country),
                city=r["city"] or "Unknown",
                industry=r["industry"] or "Channel Partner",
                contact_email=f"contact@{company_slug(partner)}.partner.extravis.com",
                status=CompanyStatus.ACTIVE,
                tier=PartnerTier.SILVER,
                company_type=CompanyType.PARTNER,
                channel_manager_id=cm.id,
            )
            db.add(c)
            await db.flush()
        companies[partner] = c
    return companies


async def ensure_partner_users(db, companies: dict[str, Company]) -> dict[int, User]:
    """One generic PARTNER user per company so opportunities have a submitter."""
    users: dict[int, User] = {}
    for partner_name, company in companies.items():
        slug = company_slug(partner_name)
        email = f"partner@{slug}.partner.extravis.com"
        res = await db.execute(select(User).where(User.email == email))
        u = res.scalar_one_or_none()
        if u is None:
            u = User(
                email=email,
                full_name=f"{partner_name} Sales Lead",
                job_title="Partner Sales",
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=UserRole.PARTNER,
                status=UserStatus.ACTIVE,
                company_id=company.id,
                has_completed_onboarding=True,
            )
            db.add(u)
            await db.flush()
        users[company.id] = u
    return users


async def create_opportunities(
    db, rows: list[dict], companies: dict[str, Company],
    partner_users: dict[int, User], team: dict[str, User], superadmin: User,
) -> tuple[int, int]:
    created = 0
    skipped = 0
    for r in rows:
        company = companies[r["partner"]]
        submitter = partner_users[company.id]
        country = r["country"] or company.country
        region = REGION_BY_COUNTRY.get(country, country)
        status = progress_to_status(r["progress"])
        closing = time_frame_to_date(r["time_frame"])
        opp_name = f"{r['customer']} — {r['product']} ({r['time_frame']})"[:200]

        # Idempotency guard: skip if an opp with the same name+company already exists
        existing = await db.execute(
            select(Opportunity).where(
                Opportunity.name == opp_name,
                Opportunity.company_id == company.id,
                Opportunity.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            skipped += 1
            continue

        reviewer = team.get(r["team"], superadmin)
        submitted_at = NOW if status != OpportunityStatus.DRAFT else None
        reviewed_at = NOW if status in (OpportunityStatus.UNDER_REVIEW, OpportunityStatus.APPROVED) else None

        requirements = (
            f"Product: {r['product']}.\n"
            f"Industry: {r['industry']}.\n"
            f"Sales rep: {reviewer.full_name}.\n"
            f"Stage: {progress_label(r['progress'])} ({int(r['progress'] * 100)}%).\n"
            f"Time frame: {r['time_frame']}."
        )

        opp = Opportunity(
            name=opp_name,
            customer_name=r["customer"],
            customer_name_normalized=normalize_customer_name(r["customer"]),
            region=region,
            country=country,
            city=r["city"] or company.city,
            worth=r["price"],
            closing_date=closing,
            requirements=requirements,
            status=status,
            submitted_by=submitter.id,
            company_id=company.id,
            reviewed_by=reviewer.id if reviewed_at else None,
            submitted_at=submitted_at,
            reviewed_at=reviewed_at,
            internal_notes=f"Imported from 2027 Target Plan.",
            # Excel-driven fields
            industry=r["industry"],
            product=r["product"],
            stage_probability=Decimal(str(r["progress"])).quantize(Decimal("0.01")),
            time_frame=r["time_frame"],
            sales_rep_id=reviewer.id,
        )
        db.add(opp)
        await db.flush()
        await write_audit_log(
            db, superadmin.id, "CREATE", "opportunity", opp.id,
            {"source": "seed_excel", "customer": r["customer"], "partner": r["partner"]},
        )
        created += 1
    return created, skipped


async def main(path: Path, dry_run: bool = False) -> None:
    rows = parse_rows(path)
    print(f">> Parsed {len(rows)} data rows from {path}")
    if dry_run:
        for r in rows[:5]:
            print("   sample:", r)
        return

    async with async_session_factory() as db:
        superadmin = await get_superadmin(db)

        print(">> Ensuring Extravis team admins…")
        team = await ensure_team(db)

        print(">> Ensuring partner companies…")
        companies = await ensure_companies(db, rows, team, superadmin)
        print(f"   {len(companies)} unique partners")

        print(">> Ensuring partner users…")
        partner_users = await ensure_partner_users(db, companies)

        print(">> Creating opportunities…")
        created, skipped = await create_opportunities(
            db, rows, companies, partner_users, team, superadmin
        )
        await db.commit()

        print()
        print(f">> Import complete.")
        print(f"   Companies (total existing): {len(companies)}")
        print(f"   Partner users:              {len(partner_users)}")
        print(f"   Opportunities created:      {created}")
        print(f"   Opportunities skipped:      {skipped}")
        print()
        print(f"   Default password for new users: {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Import opportunities from the 2027 Target Plan workbook")
    parser.add_argument("path", help="Path to the .xlsx file")
    parser.add_argument("--dry-run", action="store_true", help="Parse only; don't write to the DB")
    args = parser.parse_args()
    asyncio.run(main(Path(args.path), dry_run=args.dry_run))
