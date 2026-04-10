"""
Demo data seeder for the Extravis Partner Portal.

Populates every module with realistic, demo-ready data:
- 6 partner companies across regions/tiers
- 12 partner users (2 per company), 3 admin / channel managers
- 24 opportunities across all statuses with AI scores
- 14 deal registrations with commissions
- 8 KB documents across categories
- 5 LMS courses with modules and enrollments at every progress stage
- 12 document requests across statuses + urgencies
- Notifications for each user
- Audit log entries
- Tier history for promoted partners
- Commission statements

Usage (from inside the backend container):
    python -m app.core.seed_demo
    python -m app.core.seed_demo --reset    # wipe demo data first

The script is idempotent: re-running without --reset is safe and will skip
already-seeded entities by their well-known emails / names.
"""
from __future__ import annotations

import argparse
import asyncio
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Sequence

from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.commission import (
    Commission,
    CommissionStatement,
    CommissionStatus,
    TierCommissionRate,
)
from app.models.company import Company, CompanyStatus, PartnerTier
from app.models.course import Course, CourseStatus
from app.models.deal_registration import DealRegistration, DealStatus
from app.models.doc_request import DocRequest, DocRequestStatus, DocRequestUrgency
from app.models.enrollment import Enrollment, EnrollmentStatus
from app.models.kb_document import KBDocument
from app.models.notification import Notification
from app.models.opportunity import Opportunity, OpportunityStatus
from app.models.partner_tier import PartnerTierHistory
from app.models.user import User, UserRole, UserStatus

# Make randomness reproducible across runs so demos look the same.
random.seed(42)
NOW = datetime.now(timezone.utc)
TODAY = date.today()
DEFAULT_PASSWORD = "Demo@1234"


# ---------------------------------------------------------------------------
# Static demo data
# ---------------------------------------------------------------------------

ADMIN_USERS = [
    {
        "email": "channel.manager@extravis.com",
        "full_name": "Sarah Mitchell",
        "job_title": "Channel Sales Manager — APAC",
        "phone": "+1 415 555 0118",
    },
    {
        "email": "ops.lead@extravis.com",
        "full_name": "Daniel Okafor",
        "job_title": "Partner Operations Lead",
        "phone": "+1 415 555 0142",
    },
]

COMPANIES = [
    {
        "name": "NorthBeam Technologies",
        "country": "United States",
        "region": "North America",
        "city": "Austin",
        "industry": "Cloud Infrastructure",
        "contact_email": "partnerships@northbeam.example",
        "tier": PartnerTier.PLATINUM,
    },
    {
        "name": "Helios Cyber Solutions",
        "country": "United Kingdom",
        "region": "EMEA",
        "city": "London",
        "industry": "Cybersecurity",
        "contact_email": "alliances@helios-cyber.example",
        "tier": PartnerTier.GOLD,
    },
    {
        "name": "Pacific Data Systems",
        "country": "Singapore",
        "region": "APAC",
        "city": "Singapore",
        "industry": "Data & Analytics",
        "contact_email": "channel@pacificdata.example",
        "tier": PartnerTier.GOLD,
    },
    {
        "name": "Andes Networks",
        "country": "Brazil",
        "region": "LATAM",
        "city": "São Paulo",
        "industry": "Network Integration",
        "contact_email": "partners@andesnet.example",
        "tier": PartnerTier.SILVER,
    },
    {
        "name": "Sahara IoT Group",
        "country": "United Arab Emirates",
        "region": "MEA",
        "city": "Dubai",
        "industry": "IoT & Smart Cities",
        "contact_email": "info@saharaiot.example",
        "tier": PartnerTier.SILVER,
    },
    {
        "name": "Nordic Cloud Hub",
        "country": "Sweden",
        "region": "EMEA",
        "city": "Stockholm",
        "industry": "Managed Services",
        "contact_email": "hello@nordiccloud.example",
        "tier": PartnerTier.PLATINUM,
    },
]

# Two named partner accounts per company. Index aligns with COMPANIES.
COMPANY_PARTNERS = [
    [("Marcus Chen", "marcus.chen@northbeam.example", "Sales Director"),
     ("Priya Raman", "priya.raman@northbeam.example", "Solutions Architect")],
    [("Olivia Hartwell", "olivia.hartwell@helios-cyber.example", "Account Executive"),
     ("Ben Kowalski", "ben.kowalski@helios-cyber.example", "Pre-Sales Engineer")],
    [("Wei Lin", "wei.lin@pacificdata.example", "Channel Manager"),
     ("Aiko Tanaka", "aiko.tanaka@pacificdata.example", "Customer Success")],
    [("Lucas Almeida", "lucas.almeida@andesnet.example", "Partner Lead"),
     ("Camila Rocha", "camila.rocha@andesnet.example", "Sales Engineer")],
    [("Yusuf Al-Rashid", "yusuf.alrashid@saharaiot.example", "Business Development"),
     ("Fatima Hassan", "fatima.hassan@saharaiot.example", "Technical Consultant")],
    [("Erik Lindqvist", "erik.lindqvist@nordiccloud.example", "VP Partnerships"),
     ("Sofia Bergström", "sofia.bergstrom@nordiccloud.example", "Solution Specialist")],
]

CUSTOMERS = [
    "Atlas Manufacturing", "BlueWave Logistics", "CitySpark Energy",
    "Delta Health Group", "Evergreen Retail", "Fortis Banking",
    "GlobalPay Fintech", "Harbor Maritime", "Innova Pharmaceuticals",
    "Junction Media", "Kestrel Aerospace", "Lumen Insurance",
    "Meridian Telecoms", "Northstar Auto", "Oasis Hospitality",
    "Polar Foods", "Quantum Robotics", "Riverbend Utilities",
    "Stellar Education", "Titan Construction",
]

OPPORTUNITY_REQUIREMENTS = [
    "Deploy a multi-region Kubernetes platform with disaster recovery and 99.99% SLA.",
    "Implement zero-trust network access for 3,500 employees across 12 offices.",
    "Build a real-time analytics pipeline ingesting 80M events/day from IoT sensors.",
    "Migrate legacy Oracle workloads to a managed cloud database with minimal downtime.",
    "Set up SOC2-compliant logging and SIEM integration across hybrid infrastructure.",
    "Replace on-prem VPN with SD-WAN spanning 8 retail regions and 2 data centres.",
    "Stand up a customer data platform with consent management and GDPR controls.",
    "Roll out endpoint detection & response across a 12,000-device fleet.",
    "Modernise contact-centre stack with omnichannel AI agent assist.",
    "Deliver an AI-powered fraud detection model with sub-100ms latency.",
]

KB_DOCS = [
    ("Partner Onboarding Handbook 2026", "Onboarding",
     "Complete walkthrough of the partner activation process, contracts, and success-team contacts."),
    ("Deal Registration Best Practices", "Sales Playbook",
     "How to qualify, register, and protect deals to maximise approval rate and exclusivity windows."),
    ("Tier Promotion Criteria & Benefits", "Programs",
     "Detailed scoring rubric for Silver → Gold → Platinum promotions, including financial and training thresholds."),
    ("Solution Brief: Cloud Migration", "Solution Briefs",
     "Two-page customer-facing brief outlining the cloud migration offering, target verticals, and pricing tiers."),
    ("Co-Marketing Funds Request Form", "Marketing",
     "Template for requesting MDF funds with reporting and ROI guidelines."),
    ("Competitive Battlecard: Hyperscaler X", "Battlecards",
     "Talking points, weaknesses, and positioning vs the leading hyperscaler in the cloud category."),
    ("Pricing Guide: Managed Services Q2 2026", "Pricing",
     "Quarterly price list, discount tiers, and bundle SKUs for the managed services portfolio."),
    ("Technical Reference: API Integration", "Technical",
     "REST API reference, sample payloads, and rate limits for the platform integration."),
]

COURSES = [
    {
        "title": "Extravis Foundations",
        "description": "Core concepts, value proposition, and partner program structure. Required for all new partner reps.",
        "duration_hours": 3,
        "modules": [
            {"id": 1, "title": "Welcome & Program Overview", "content": "Introduction to Extravis and the partner ecosystem.", "duration_minutes": 25},
            {"id": 2, "title": "Solution Pillars", "content": "Cloud, Security, Data — the three solution pillars explained.", "duration_minutes": 35},
            {"id": 3, "title": "Engagement Model", "content": "How partners engage with Extravis sales and CS teams.", "duration_minutes": 30},
            {"id": 4, "title": "Tools & Portal Tour", "content": "Walkthrough of the partner portal and supporting tools.", "duration_minutes": 25},
        ],
        "assessment": [
            {"id": 1, "question": "Which is NOT one of the three solution pillars?", "options": ["Cloud", "Security", "Data", "Hardware"], "correct": 3},
            {"id": 2, "question": "What percentage is required to pass this assessment?", "options": ["50%", "60%", "70%", "80%"], "correct": 2},
            {"id": 3, "question": "Where do you register a new opportunity?", "options": ["Email", "Partner Portal", "Phone", "Excel sheet"], "correct": 1},
        ],
    },
    {
        "title": "Selling the Cloud Platform",
        "description": "Discovery, qualification, and ROI framing for the Extravis cloud portfolio.",
        "duration_hours": 4,
        "modules": [
            {"id": 1, "title": "Discovery Questions", "content": "The 8 questions that uncover real opportunity.", "duration_minutes": 40},
            {"id": 2, "title": "ROI Framework", "content": "Calculating and presenting customer ROI.", "duration_minutes": 50},
            {"id": 3, "title": "Handling Objections", "content": "Top objections and proven responses.", "duration_minutes": 45},
        ],
        "assessment": [
            {"id": 1, "question": "How many discovery questions are in the framework?", "options": ["5", "6", "7", "8"], "correct": 3},
            {"id": 2, "question": "ROI calculations should always include?", "options": ["Hardware costs", "Total cost of ownership", "Marketing budget", "Headcount"], "correct": 1},
        ],
    },
    {
        "title": "Cybersecurity Specialist",
        "description": "Deep-dive on the security portfolio for partners targeting regulated industries.",
        "duration_hours": 6,
        "modules": [
            {"id": 1, "title": "Threat Landscape 2026", "content": "Current threats and customer pain points.", "duration_minutes": 60},
            {"id": 2, "title": "Zero-Trust Architecture", "content": "The Extravis zero-trust reference architecture.", "duration_minutes": 75},
            {"id": 3, "title": "Compliance Frameworks", "content": "Mapping the platform to SOC2, ISO 27001, HIPAA.", "duration_minutes": 60},
            {"id": 4, "title": "Customer Case Studies", "content": "Real wins and lessons learned.", "duration_minutes": 45},
        ],
        "assessment": [
            {"id": 1, "question": "Zero-trust assumes which of the following?", "options": ["The network is safe inside the firewall", "Every request must be verified", "Only external threats matter", "VPN is sufficient"], "correct": 1},
            {"id": 2, "question": "Which standard is most common for healthcare?", "options": ["PCI-DSS", "HIPAA", "FedRAMP", "GDPR"], "correct": 1},
            {"id": 3, "question": "SOC2 has how many trust principles?", "options": ["3", "4", "5", "6"], "correct": 2},
        ],
    },
    {
        "title": "Data & Analytics Bootcamp",
        "description": "Position the data platform for analytics, AI, and reporting use cases.",
        "duration_hours": 5,
        "modules": [
            {"id": 1, "title": "Data Architecture", "content": "Lakehouse vs warehouse — when to use what.", "duration_minutes": 50},
            {"id": 2, "title": "Real-time Pipelines", "content": "Streaming ingestion patterns.", "duration_minutes": 55},
            {"id": 3, "title": "AI & ML Integration", "content": "Model training and serving on the platform.", "duration_minutes": 60},
        ],
        "assessment": [
            {"id": 1, "question": "Which is best for low-latency analytics?", "options": ["Daily batch", "Streaming pipeline", "Manual export", "Email reports"], "correct": 1},
        ],
    },
    {
        "title": "Partner Sales Methodology",
        "description": "Joint go-to-market motions and how to co-sell with the Extravis field team.",
        "duration_hours": 2,
        "modules": [
            {"id": 1, "title": "Joint Account Planning", "content": "Building a 30-60-90 plan with your channel manager.", "duration_minutes": 40},
            {"id": 2, "title": "Co-selling Motions", "content": "When to invite Extravis into the deal.", "duration_minutes": 35},
        ],
        "assessment": [
            {"id": 1, "question": "When should you involve your channel manager?", "options": ["Never", "Only on contract", "From qualification onwards", "After the deal is closed"], "correct": 2},
        ],
    },
]

DOC_REQUEST_TEMPLATES = [
    ("Latest pricing sheet for managed services", "Need updated rates for an active proposal", DocRequestUrgency.HIGH),
    ("Solution architecture diagram for healthcare vertical", "Customer requested a reference architecture", DocRequestUrgency.MEDIUM),
    ("SOC 2 Type II audit report", "Procurement requires it before contract signature", DocRequestUrgency.HIGH),
    ("Co-marketing guidelines for Q2 campaign", "Planning a joint webinar in May", DocRequestUrgency.LOW),
    ("Competitive comparison vs Hyperscaler Y", "Customer is evaluating both vendors", DocRequestUrgency.MEDIUM),
    ("API rate limit specifications", "Engineering needs limits for capacity planning", DocRequestUrgency.LOW),
    ("Customer success case study: financial services", "Adding to upcoming RFP response", DocRequestUrgency.MEDIUM),
    ("Updated MSA template", "Customer legal team wants the latest version", DocRequestUrgency.HIGH),
    ("Regional support coverage map", "Customer asked about EMEA support hours", DocRequestUrgency.LOW),
    ("Carbon footprint disclosure", "RFP requires sustainability documentation", DocRequestUrgency.MEDIUM),
    ("Disaster recovery whitepaper", "BFSI customer due diligence", DocRequestUrgency.MEDIUM),
    ("Partner program tier benefits matrix", "Pitching the program to a new sub-partner", DocRequestUrgency.LOW),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rand_past(days_max: int) -> datetime:
    return NOW - timedelta(days=random.randint(1, days_max), hours=random.randint(0, 23))


def _rand_future_date(days_min: int, days_max: int) -> date:
    return TODAY + timedelta(days=random.randint(days_min, days_max))


# ---------------------------------------------------------------------------
# Main seeding logic
# ---------------------------------------------------------------------------

async def reset_demo_data(db) -> None:
    """Wipe demo entities while preserving the bootstrap superadmin and any
    real users that aren't part of the demo set."""
    print(">> Resetting demo data…")
    # Order matters for FK constraints
    await db.execute(delete(AuditLog))
    await db.execute(delete(Notification))
    await db.execute(delete(CommissionStatement))
    await db.execute(delete(Commission))
    await db.execute(delete(Enrollment))
    await db.execute(delete(Course))
    await db.execute(delete(KBDocument))
    await db.execute(delete(DocRequest))
    await db.execute(delete(DealRegistration))
    await db.execute(delete(Opportunity))
    await db.execute(delete(PartnerTierHistory))

    # Delete demo users by their *.example domain to be safe
    await db.execute(
        delete(User).where(User.email.like("%.example"))
    )
    # Delete the named admin demo users
    await db.execute(
        delete(User).where(User.email.in_([u["email"] for u in ADMIN_USERS]))
    )
    # Companies last (users that referenced them are gone)
    await db.execute(delete(Company))
    await db.commit()
    print("   reset complete")


async def get_or_create_admin(db) -> User:
    result = await db.execute(select(User).where(User.email == "admin@extravis.com"))
    user = result.scalar_one_or_none()
    if user is None:
        raise RuntimeError(
            "Bootstrap superadmin admin@extravis.com is missing — run init_db first."
        )
    return user


async def seed_admin_users(db) -> list[User]:
    created: list[User] = []
    for entry in ADMIN_USERS:
        result = await db.execute(select(User).where(User.email == entry["email"]))
        existing = result.scalar_one_or_none()
        if existing:
            created.append(existing)
            continue
        u = User(
            email=entry["email"],
            full_name=entry["full_name"],
            job_title=entry["job_title"],
            phone=entry["phone"],
            password_hash=hash_password(DEFAULT_PASSWORD),
            role=UserRole.ADMIN,
            status=UserStatus.ACTIVE,
            is_superadmin=False,
            has_completed_onboarding=True,
        )
        db.add(u)
        created.append(u)
    await db.flush()
    return created


async def seed_companies_and_partners(db, channel_managers: Sequence[User]) -> tuple[list[Company], list[User]]:
    companies: list[Company] = []
    partners: list[User] = []

    for idx, c in enumerate(COMPANIES):
        result = await db.execute(select(Company).where(Company.name == c["name"]))
        existing = result.scalar_one_or_none()
        if existing:
            companies.append(existing)
            continue

        cm = channel_managers[idx % len(channel_managers)]
        company = Company(
            name=c["name"],
            country=c["country"],
            region=c["region"],
            city=c["city"],
            industry=c["industry"],
            contact_email=c["contact_email"],
            status=CompanyStatus.ACTIVE,
            tier=c["tier"],
            channel_manager_id=cm.id,
        )
        db.add(company)
        companies.append(company)

    await db.flush()  # so company ids are populated

    for idx, company in enumerate(companies):
        partner_specs = COMPANY_PARTNERS[idx]
        for full_name, email, title in partner_specs:
            result = await db.execute(select(User).where(User.email == email))
            existing = result.scalar_one_or_none()
            if existing:
                partners.append(existing)
                continue
            user = User(
                full_name=full_name,
                email=email,
                job_title=title,
                phone=f"+1 415 555 0{random.randint(100, 999)}",
                password_hash=hash_password(DEFAULT_PASSWORD),
                role=UserRole.PARTNER,
                status=UserStatus.ACTIVE,
                company_id=company.id,
                has_completed_onboarding=True,
                last_login_at=_rand_past(15),
            )
            db.add(user)
            partners.append(user)

    await db.flush()

    # Tier history for promoted companies (Gold/Platinum had a previous tier)
    for company in companies:
        if company.tier == PartnerTier.PLATINUM:
            db.add(PartnerTierHistory(
                company_id=company.id,
                previous_tier="gold",
                new_tier="platinum",
                reason="Exceeded $1M ARR with 95% deal-approval rate over 4 quarters.",
                changed_by=channel_managers[0].id,
                changed_at=NOW - timedelta(days=random.randint(20, 90)),
            ))
        elif company.tier == PartnerTier.GOLD:
            db.add(PartnerTierHistory(
                company_id=company.id,
                previous_tier="silver",
                new_tier="gold",
                reason="Met Gold criteria: 6+ certified reps and 3 closed deals in the quarter.",
                changed_by=channel_managers[0].id,
                changed_at=NOW - timedelta(days=random.randint(30, 180)),
            ))

    await db.flush()
    return companies, partners


async def seed_opportunities(
    db, companies: list[Company], partners: list[User], admins: list[User]
) -> list[Opportunity]:
    opps: list[Opportunity] = []
    statuses = [
        OpportunityStatus.DRAFT,
        OpportunityStatus.PENDING_REVIEW,
        OpportunityStatus.UNDER_REVIEW,
        OpportunityStatus.APPROVED,
        OpportunityStatus.APPROVED,
        OpportunityStatus.APPROVED,
        OpportunityStatus.REJECTED,
        OpportunityStatus.PENDING_REVIEW,
    ]

    for i in range(24):
        company = companies[i % len(companies)]
        # find a partner that belongs to this company
        company_partners = [p for p in partners if p.company_id == company.id]
        submitter = company_partners[i % len(company_partners)] if company_partners else partners[0]
        status = statuses[i % len(statuses)]
        customer = CUSTOMERS[i % len(CUSTOMERS)]
        worth = Decimal(random.choice([45_000, 80_000, 125_000, 220_000, 350_000, 540_000, 875_000, 1_250_000]))
        ai_score = random.randint(35, 95) if status != OpportunityStatus.DRAFT else None

        submitted_at = _rand_past(60) if status != OpportunityStatus.DRAFT else None
        reviewed_at = (submitted_at + timedelta(days=random.randint(1, 5))) if submitted_at and status in (OpportunityStatus.APPROVED, OpportunityStatus.REJECTED, OpportunityStatus.UNDER_REVIEW) else None

        # Spread created_at across the last ~6 months so monthly trend
        # charts show real variation instead of one big lump on day zero.
        created_at = NOW - timedelta(days=(i + 1) * 7, hours=(i * 3) % 24)

        opp = Opportunity(
            name=f"{customer} — {OPPORTUNITY_REQUIREMENTS[i % len(OPPORTUNITY_REQUIREMENTS)].split('.')[0][:40]}",
            customer_name=customer,
            region=company.region,
            country=company.country,
            city=company.city,
            worth=worth,
            closing_date=_rand_future_date(15, 180),
            requirements=OPPORTUNITY_REQUIREMENTS[i % len(OPPORTUNITY_REQUIREMENTS)],
            status=status,
            preferred_partner=(i % 5 == 0),
            multi_partner_alert=(i % 11 == 0),
            ai_score=ai_score,
            ai_reasoning=(
                f"Strong fit: deal value ${worth:,.0f} aligns with {company.tier.value} tier average; "
                f"{company.region} region with established CSM presence; closing date is realistic."
            ) if ai_score else None,
            ai_scored_at=submitted_at,
            submitted_by=submitter.id,
            company_id=company.id,
            reviewed_by=admins[0].id if reviewed_at else None,
            submitted_at=submitted_at,
            reviewed_at=reviewed_at,
            created_at=created_at,
            rejection_reason="Customer is already covered by a preferred partner under exclusivity." if status == OpportunityStatus.REJECTED else None,
        )
        db.add(opp)
        opps.append(opp)

    await db.flush()
    return opps


async def seed_deal_registrations(
    db, companies: list[Company], partners: list[User], admins: list[User], opportunities: list[Opportunity]
) -> list[DealRegistration]:
    deals: list[DealRegistration] = []
    statuses = [DealStatus.PENDING, DealStatus.APPROVED, DealStatus.APPROVED, DealStatus.APPROVED, DealStatus.REJECTED, DealStatus.EXPIRED]

    for i in range(14):
        company = companies[i % len(companies)]
        company_partners = [p for p in partners if p.company_id == company.id]
        submitter = company_partners[0] if company_partners else partners[0]
        status = statuses[i % len(statuses)]
        value = Decimal(random.choice([60_000, 110_000, 180_000, 320_000, 480_000, 720_000, 1_100_000]))
        # Some deals are linked to existing approved opportunities
        linked_opp = None
        approved_opps = [o for o in opportunities if o.company_id == company.id and o.status == OpportunityStatus.APPROVED]
        if approved_opps and i % 2 == 0:
            linked_opp = approved_opps[i % len(approved_opps)]

        approved_at = _rand_past(45) if status == DealStatus.APPROVED else None
        excl_start = approved_at.date() if approved_at else None
        excl_end = (approved_at + timedelta(days=120)).date() if approved_at else None

        deal = DealRegistration(
            company_id=company.id,
            registered_by=submitter.id,
            opportunity_id=linked_opp.id if linked_opp else None,
            customer_name=CUSTOMERS[(i + 7) % len(CUSTOMERS)],
            deal_description=(
                f"{value:,.0f} USD opportunity for {company.industry.lower()} solution. "
                f"Engaged via {company.region} channel team. Customer evaluating against 1 competitor."
            ),
            estimated_value=value,
            expected_close_date=_rand_future_date(30, 240),
            status=status,
            exclusivity_start=excl_start,
            exclusivity_end=excl_end,
            rejection_reason="Conflicts with existing direct sales engagement." if status == DealStatus.REJECTED else None,
            approved_by=admins[0].id if approved_at else None,
            approved_at=approved_at,
        )
        db.add(deal)
        deals.append(deal)

    await db.flush()
    return deals


async def seed_commissions(db, deals: list[DealRegistration], companies: list[Company]) -> None:
    """Calculate commissions for approved deals using current tier rates."""
    # Look up active rates
    rates_result = await db.execute(select(TierCommissionRate).where(TierCommissionRate.effective_to.is_(None)))
    rates = {r.tier.value if hasattr(r.tier, "value") else r.tier: r for r in rates_result.scalars().all()}
    if not rates:
        # Fallback if migration 005 seed didn't run for some reason
        rates = {
            "silver": type("R", (), {"percentage": Decimal("5.00")})(),
            "gold": type("R", (), {"percentage": Decimal("8.00")})(),
            "platinum": type("R", (), {"percentage": Decimal("12.00")})(),
        }

    company_by_id = {c.id: c for c in companies}

    for deal in deals:
        if deal.status != DealStatus.APPROVED:
            continue
        company = company_by_id.get(deal.company_id)
        if not company:
            continue
        tier_value = company.tier.value if hasattr(company.tier, "value") else company.tier
        rate = rates.get(tier_value)
        if not rate:
            continue

        # Avoid duplicate commissions
        existing_q = await db.execute(select(Commission).where(Commission.deal_id == deal.id))
        if existing_q.scalar_one_or_none():
            continue

        amount = (Decimal(deal.estimated_value) * Decimal(rate.percentage) / Decimal(100)).quantize(Decimal("0.01"))
        # Stagger statuses across approved deals
        commission_status = random.choice([
            CommissionStatus.PENDING, CommissionStatus.APPROVED, CommissionStatus.PAID, CommissionStatus.PAID,
        ])
        approved_at = deal.approved_at
        paid_at = (approved_at + timedelta(days=random.randint(15, 45))) if commission_status == CommissionStatus.PAID and approved_at else None

        c = Commission(
            deal_id=deal.id,
            company_id=company.id,
            user_id=deal.registered_by,
            tier_at_calculation=company.tier,
            rate_percentage=Decimal(rate.percentage),
            deal_value=Decimal(deal.estimated_value),
            amount=amount,
            currency="USD",
            status=commission_status,
            calculated_at=approved_at or NOW,
            approved_at=approved_at if commission_status in (CommissionStatus.APPROVED, CommissionStatus.PAID) else None,
            paid_at=paid_at,
            notes=f"Auto-calculated from approved deal #{deal.id}",
        )
        db.add(c)

    await db.flush()


async def seed_commission_statements(db, companies: list[Company]) -> None:
    """One closed monthly statement per Gold/Platinum company for last month."""
    first_of_this = TODAY.replace(day=1)
    last_month_end = first_of_this - timedelta(days=1)
    last_month_start = last_month_end.replace(day=1)

    # Aggregate paid commissions per company in that window
    for company in companies:
        if company.tier == PartnerTier.SILVER:
            continue
        result = await db.execute(
            select(Commission).where(
                Commission.company_id == company.id,
                Commission.paid_at.is_not(None),
            )
        )
        commissions = list(result.scalars().all())
        if not commissions:
            continue
        total = sum((Decimal(c.amount) for c in commissions), Decimal("0"))
        db.add(CommissionStatement(
            company_id=company.id,
            period_start=last_month_start,
            period_end=last_month_end,
            total_amount=total,
            commission_count=len(commissions),
            generated_at=NOW - timedelta(days=2),
        ))


async def seed_kb_documents(db, admin: User) -> list[KBDocument]:
    docs: list[KBDocument] = []
    for title, category, description in KB_DOCS:
        result = await db.execute(select(KBDocument).where(KBDocument.title == title))
        if result.scalar_one_or_none():
            continue
        doc = KBDocument(
            title=title,
            category=category,
            description=description,
            file_name=f"{title.lower().replace(' ', '_').replace(':', '')[:50]}.pdf",
            file_url=f"/uploads/kb/{title.lower().replace(' ', '_').replace(':', '')[:50]}.pdf",
            file_size=random.randint(180_000, 4_500_000),
            content_type="application/pdf",
            version=1,
            uploaded_by=admin.id,
            published_at=_rand_past(120),
        )
        db.add(doc)
        docs.append(doc)
    await db.flush()
    return docs


async def seed_courses(db, admin: User) -> list[Course]:
    courses: list[Course] = []
    for spec in COURSES:
        result = await db.execute(select(Course).where(Course.title == spec["title"]))
        existing = result.scalar_one_or_none()
        if existing:
            courses.append(existing)
            continue
        course = Course(
            title=spec["title"],
            description=spec["description"],
            status=CourseStatus.PUBLISHED,
            modules_json=spec["modules"],
            assessment_json=spec["assessment"],
            passing_score=70,
            duration_hours=spec["duration_hours"],
            created_by=admin.id,
        )
        db.add(course)
        courses.append(course)
    await db.flush()
    return courses


async def seed_enrollments(db, courses: list[Course], partners: list[User]) -> None:
    if not courses or not partners:
        return
    # Each partner enrolls in 2-4 courses, with mixed progress
    for partner in partners:
        sample = random.sample(courses, k=min(random.randint(2, 4), len(courses)))
        for idx, course in enumerate(sample):
            # Skip if already enrolled (idempotent)
            existing = await db.execute(
                select(Enrollment).where(
                    Enrollment.user_id == partner.id,
                    Enrollment.course_id == course.id,
                )
            )
            if existing.scalar_one_or_none():
                continue
            modules = course.modules_json or []
            num_modules = len(modules)
            # Distribute statuses: some completed, some in progress, some just enrolled
            roll = random.random()
            if roll < 0.4 and num_modules > 0:
                completed_modules = list(range(1, num_modules + 1))
                status = EnrollmentStatus.COMPLETED
                score = random.randint(72, 98)
                completed_at = _rand_past(45)
                cert_requested = random.random() < 0.7
            elif roll < 0.8 and num_modules > 0:
                completed_modules = list(range(1, max(1, num_modules // 2 + 1)))
                status = EnrollmentStatus.IN_PROGRESS
                score = None
                completed_at = None
                cert_requested = False
            else:
                completed_modules = []
                status = EnrollmentStatus.ENROLLED
                score = None
                completed_at = None
                cert_requested = False

            db.add(Enrollment(
                user_id=partner.id,
                course_id=course.id,
                status=status,
                progress_json={"completed_modules": completed_modules, "current_module": completed_modules[-1] if completed_modules else 0},
                attempt_count=1 if score else 0,
                score=score,
                completed_at=completed_at,
                certificate_requested=cert_requested,
                certificate_requested_at=completed_at if cert_requested else None,
                certificate_issued_at=completed_at if cert_requested and random.random() < 0.6 else None,
                certificate_url="/uploads/certificates/sample.pdf" if cert_requested and random.random() < 0.6 else None,
                enrolled_at=_rand_past(90),
            ))
    await db.flush()


async def seed_doc_requests(db, companies: list[Company], partners: list[User], admins: list[User]) -> None:
    statuses_cycle = [
        DocRequestStatus.PENDING, DocRequestStatus.PENDING, DocRequestStatus.PENDING,
        DocRequestStatus.FULFILLED, DocRequestStatus.FULFILLED, DocRequestStatus.FULFILLED,
        DocRequestStatus.FULFILLED, DocRequestStatus.DECLINED,
    ]
    for i, (description, reason, urgency) in enumerate(DOC_REQUEST_TEMPLATES):
        company = companies[i % len(companies)]
        company_partners = [p for p in partners if p.company_id == company.id]
        requester = company_partners[i % len(company_partners)] if company_partners else partners[0]
        status = statuses_cycle[i % len(statuses_cycle)]
        fulfilled_at = _rand_past(20) if status == DocRequestStatus.FULFILLED else None

        db.add(DocRequest(
            company_id=company.id,
            requested_by=requester.id,
            description=description,
            reason=reason,
            urgency=urgency,
            status=status,
            fulfilled_by=admins[0].id if status == DocRequestStatus.FULFILLED else None,
            fulfilled_at=fulfilled_at,
            fulfilled_file_url="/uploads/doc_requests/sample.pdf" if status == DocRequestStatus.FULFILLED else None,
            fulfilled_file_name=f"{description[:30].replace(' ', '_')}.pdf" if status == DocRequestStatus.FULFILLED else None,
            decline_reason="Confidential — cannot be shared with external partners." if status == DocRequestStatus.DECLINED else None,
            created_at=_rand_past(30),
        ))
    await db.flush()


async def seed_notifications(db, partners: list[User], admins: list[User]) -> None:
    samples = [
        ("opportunity_approved", "Opportunity approved", "Your opportunity for Atlas Manufacturing has been approved."),
        ("deal_approved", "Deal registration approved", "Deal registration for BlueWave Logistics is now active."),
        ("course_assigned", "New training assigned", "You've been enrolled in 'Cybersecurity Specialist'."),
        ("doc_request_fulfilled", "Document request fulfilled", "Your request for the SOC 2 report has been fulfilled."),
        ("commission_paid", "Commission paid", "A commission of $14,400 has been paid to your company."),
        ("tier_promoted", "Tier promotion", "Congratulations! Your company has been promoted to Gold tier."),
    ]

    for partner in partners:
        # 3 random notifications per partner, mixed read/unread
        for sample in random.sample(samples, k=3):
            ntype, title, message = sample
            db.add(Notification(
                user_id=partner.id,
                type=ntype,
                title=title,
                message=message,
                read=random.random() < 0.5,
                entity_type="opportunity" if "opportunity" in ntype else None,
                created_at=_rand_past(20),
            ))

    # A couple of admin notifications too
    for admin in admins[:1]:
        db.add(Notification(
            user_id=admin.id,
            type="opportunity_submitted",
            title="New opportunity pending review",
            message="NorthBeam Technologies submitted a new opportunity worth $1.2M.",
            read=False,
            created_at=_rand_past(2),
        ))


async def seed_audit_logs(db, admins: list[User], partners: list[User]) -> None:
    actions = [
        ("create", "opportunity"),
        ("update", "opportunity"),
        ("approve", "deal_registration"),
        ("upload", "kb_document"),
        ("fulfill", "doc_request"),
        ("update", "company"),
    ]
    actors = (admins + partners[:4])
    for i in range(40):
        action, entity = random.choice(actions)
        actor = random.choice(actors)
        db.add(AuditLog(
            user_id=actor.id,
            action=action,
            entity_type=entity,
            entity_id=random.randint(1, 24),
            metadata_json={"source": "demo_seed"},
            ip_address=f"10.0.{random.randint(0, 5)}.{random.randint(1, 250)}",
            user_agent="Mozilla/5.0 (compatible; ExtravisDemoSeed/1.0)",
            timestamp=_rand_past(45),
        ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(reset: bool = False) -> None:
    async with async_session_factory() as db:
        if reset:
            await reset_demo_data(db)

        print(">> Loading bootstrap superadmin…")
        superadmin = await get_or_create_admin(db)

        print(">> Seeding admin users (channel managers)…")
        admins = await seed_admin_users(db)
        all_admins = [superadmin] + admins

        print(">> Seeding companies and partners…")
        companies, partners = await seed_companies_and_partners(db, all_admins)

        print(">> Seeding opportunities…")
        opportunities = await seed_opportunities(db, companies, partners, all_admins)

        print(">> Seeding deal registrations…")
        deals = await seed_deal_registrations(db, companies, partners, all_admins, opportunities)

        print(">> Seeding commissions…")
        await seed_commissions(db, deals, companies)

        print(">> Seeding commission statements…")
        await seed_commission_statements(db, companies)

        print(">> Seeding knowledge base documents…")
        await seed_kb_documents(db, superadmin)

        print(">> Seeding LMS courses…")
        courses = await seed_courses(db, superadmin)

        print(">> Seeding enrollments…")
        await seed_enrollments(db, courses, partners)

        print(">> Seeding document requests…")
        await seed_doc_requests(db, companies, partners, all_admins)

        print(">> Seeding notifications…")
        await seed_notifications(db, partners, all_admins)

        print(">> Seeding audit logs…")
        await seed_audit_logs(db, all_admins, partners)

        await db.commit()
        print("\n>> Demo seed complete.")
        print(f"   Companies: {len(companies)}")
        print(f"   Partners:  {len(partners)}")
        print(f"   Admins:    {len(all_admins)}")
        print(f"   Opportunities: {len(opportunities)}")
        print(f"   Deals: {len(deals)}")
        print(f"\n   All demo accounts use password: {DEFAULT_PASSWORD}")
        print(f"   Sample partner login: marcus.chen@northbeam.example / {DEFAULT_PASSWORD}")
        print(f"   Channel manager login: channel.manager@extravis.com / {DEFAULT_PASSWORD}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed demo data for Extravis Partner Portal")
    parser.add_argument("--reset", action="store_true", help="Wipe existing demo data first")
    args = parser.parse_args()
    asyncio.run(main(reset=args.reset))
