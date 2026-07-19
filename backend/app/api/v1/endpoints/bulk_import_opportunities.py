"""
Admin endpoint: bulk-import opportunities from the 2027 Target Plan workbook.

Mirrors the schema used by `app.core.seed_excel` so the same .xlsx file can
be uploaded through the admin UI instead of running a CLI script.

Endpoints:
  POST /api/v1/opportunities/bulk-import          — upload .xlsx, ingest rows
  GET  /api/v1/opportunities/bulk-import-template — download blank template
"""
import io
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, UploadFile, File
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import timedelta

from app.core.database import get_db
from app.core.deps import get_current_superadmin
from app.core.config import settings
from app.core.exceptions import BadRequestException
from app.core.security import hash_password, generate_token
from app.core.seed_excel import (
    EXTRAVIS_TEAM,
    REGION_BY_COUNTRY,
    clean,
    company_slug,
    progress_label,
    progress_to_status,
    time_frame_to_date,
)
from app.utils.bulk_import import load_xlsx_bounded, read_rows_capped
from app.models.company import Company, CompanyStatus, PartnerTier
from app.models.opportunity import Opportunity
from app.models.user import User, UserRole, UserStatus
from app.utils.audit import write_audit_log
from app.utils.customer_normalize import normalize_customer_name

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])

EXPECTED_HEADERS = [
    "S.No", "Customer", "Partner", "Extravis Team", "City", "Country",
    "Industry", "Progress", "Product", "Price", "Time Frame",
]


def _placeholder_account_fields() -> dict:
    """Fields for a user row the importer creates as a side effect.

    Created as PENDING_ACTIVATION with a random, unguessable password and an
    activation token — NOT active with a shared default password. This is the
    fix for the old behaviour where an import minted immediately-loginable
    ADMIN accounts whose password was committed in the source.
    """
    return {
        "password_hash": hash_password(generate_token()),
        "status": UserStatus.PENDING_ACTIVATION,
        "activation_token": generate_token(),
        "activation_token_expires": datetime.now(timezone.utc)
        + timedelta(hours=settings.ACTIVATION_TOKEN_EXPIRE_HOURS),
        "has_completed_onboarding": False,
    }


@router.post("/bulk-import", status_code=200)
async def bulk_import_opportunities(
    file: UploadFile = File(...),
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    # Superadmin-only: this import creates ADMIN and PARTNER user rows as a
    # side effect, so it must never be reachable by a scoped channel manager.
    ws = await load_xlsx_bounded(file, data_only=True)
    rows = read_rows_capped(ws)

    header = [clean(h) for h in rows[0]]
    missing = [h for h in EXPECTED_HEADERS if h not in header]
    if missing:
        raise BadRequestException(
            code="INVALID_HEADERS",
            message=f"Missing required column(s): {', '.join(missing)}",
        )
    idx = {name: header.index(name) for name in EXPECTED_HEADERS}

    # Caches so we don't refetch the same partner/team across rows
    company_cache: dict[str, Company] = {}
    team_cache: dict[str, User] = {}
    partner_user_cache: dict[int, User] = {}

    succeeded = 0
    failed: list[dict] = []

    for row_num, raw in enumerate(rows[1:], start=2):
        try:
            sno = raw[idx["S.No"]]
            if sno is None:
                continue  # blank / legend row
            customer = clean(raw[idx["Customer"]])
            partner_name = clean(raw[idx["Partner"]])
            team_key = clean(raw[idx["Extravis Team"]])
            if not customer or not partner_name or not team_key:
                continue

            try:
                progress = float(raw[idx["Progress"]]) if raw[idx["Progress"]] is not None else 0.1
            except (TypeError, ValueError):
                progress = 0.1
            try:
                price = Decimal(str(raw[idx["Price"]] or 0)).quantize(Decimal("0.01"))
            except Exception:
                price = Decimal("0.00")

            city = clean(raw[idx["City"]]) or "Unknown"
            country = clean(raw[idx["Country"]]).rstrip() or "Unknown"
            industry = clean(raw[idx["Industry"]]).rstrip() or "Other"
            product = clean(raw[idx["Product"]]) or "MonetX"
            time_frame = clean(raw[idx["Time Frame"]]) or "Q4 - 2027"

            # Extravis Team admin (must exist in mapping)
            spec = EXTRAVIS_TEAM.get(team_key)
            if not spec:
                raise ValueError(f"Unknown Extravis Team value: {team_key!r}")
            cm = team_cache.get(team_key)
            if not cm:
                res = await db.execute(select(User).where(User.email == spec["email"]))
                cm = res.scalar_one_or_none()
                if not cm:
                    cm = User(
                        email=spec["email"],
                        full_name=spec["full_name"],
                        job_title=spec["job_title"],
                        role=UserRole.ADMIN,
                        **_placeholder_account_fields(),
                    )
                    db.add(cm)
                    await db.flush()
                team_cache[team_key] = cm

            # Partner company
            company = company_cache.get(partner_name)
            if not company:
                res = await db.execute(select(Company).where(Company.name == partner_name))
                company = res.scalar_one_or_none()
                if not company:
                    company = Company(
                        name=partner_name,
                        country=country,
                        region=REGION_BY_COUNTRY.get(country, country),
                        city=city,
                        industry=industry or "Channel Partner",
                        contact_email=f"contact@{company_slug(partner_name)}.partner.extravis.com",
                        status=CompanyStatus.ACTIVE,
                        tier=PartnerTier.SILVER,
                        channel_manager_id=cm.id,
                    )
                    db.add(company)
                    await db.flush()
                company_cache[partner_name] = company

            # Partner submitter user (one per company)
            submitter = partner_user_cache.get(company.id)
            if not submitter:
                slug = company_slug(partner_name)
                email = f"partner@{slug}.partner.extravis.com"
                res = await db.execute(select(User).where(User.email == email))
                submitter = res.scalar_one_or_none()
                if not submitter:
                    submitter = User(
                        email=email,
                        full_name=f"{partner_name} Sales Lead",
                        job_title="Partner Sales",
                        role=UserRole.PARTNER,
                        company_id=company.id,
                        **_placeholder_account_fields(),
                    )
                    db.add(submitter)
                    await db.flush()
                partner_user_cache[company.id] = submitter

            status = progress_to_status(progress)
            opp_name = f"{customer} — {product} ({time_frame})"[:200]

            # Idempotency: skip if same name + company already exists
            dup_q = await db.execute(
                select(Opportunity).where(
                    Opportunity.name == opp_name,
                    Opportunity.company_id == company.id,
                    Opportunity.deleted_at.is_(None),
                )
            )
            if dup_q.scalar_one_or_none():
                continue

            now = datetime.now(timezone.utc)
            from app.models.opportunity import OpportunityStatus
            submitted_at = now if status != OpportunityStatus.DRAFT else None
            reviewed_at = now if status in (OpportunityStatus.UNDER_REVIEW, OpportunityStatus.APPROVED) else None

            requirements = (
                f"Product: {product}.\n"
                f"Industry: {industry}.\n"
                f"Sales rep: {cm.full_name}.\n"
                f"Stage: {progress_label(progress)} ({int(progress * 100)}%).\n"
                f"Time frame: {time_frame}."
            )

            opp = Opportunity(
                name=opp_name,
                customer_name=customer,
                customer_name_normalized=normalize_customer_name(customer),
                region=REGION_BY_COUNTRY.get(country, country),
                country=country,
                city=city,
                worth=price,
                closing_date=time_frame_to_date(time_frame),
                requirements=requirements,
                status=status,
                submitted_by=submitter.id,
                company_id=company.id,
                reviewed_by=cm.id if reviewed_at else None,
                submitted_at=submitted_at,
                reviewed_at=reviewed_at,
                internal_notes=f"Imported from 2027 Target Plan.",
                industry=industry,
                product=product,
                stage_probability=Decimal(str(progress)).quantize(Decimal("0.01")),
                time_frame=time_frame,
                sales_rep_id=cm.id,
            )
            db.add(opp)
            await db.flush()
            await write_audit_log(
                db, admin.id, "CREATE", "opportunity", opp.id,
                {"source": "bulk_import", "customer": customer, "partner": partner_name},
            )
            succeeded += 1

        except Exception as e:
            failed.append({"row": row_num, "error": str(e)})

    await db.commit()

    return {
        "processed": len(rows) - 1,
        "succeeded": succeeded,
        "failed": failed,
        "companies_touched": len(company_cache),
        "admins_touched": len(team_cache),
    }


@router.get("/bulk-import-template", status_code=200)
async def download_bulk_import_template(admin: User = Depends(get_current_superadmin)):
    wb = Workbook()
    ws = wb.active
    ws.title = "Opportunities"
    ws.append(EXPECTED_HEADERS)
    ws.append([1, "Acme Corp", "Nets-Karachi", "Owais", "Karachi", "Pakistan",
               "FSI", 1.0, "MonetX", 7000, "Q3 - 2027"])
    for col in ws.columns:
        max_len = max((len(str(c.value)) for c in col if c.value is not None), default=0)
        ws.column_dimensions[col[0].column_letter].width = max_len + 2

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=opportunities_import_template.xlsx"},
    )
