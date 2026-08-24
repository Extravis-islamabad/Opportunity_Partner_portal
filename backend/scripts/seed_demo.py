"""Seed realistic demo data across every module of the partner portal.

Run inside the backend container:
    docker compose exec backend python scripts/seed_demo.py

Idempotent: aborts if the sentinel company already exists. Passwords for all
seeded users are 'Extravis@2026'. The superadmin from init_db is untouched.
"""
import asyncio
import random
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

sys.path.insert(0, "/app")

from sqlalchemy import select

from app.core.database import async_session_factory
from app.core.security import hash_password
from app.models import (
    AuditLog, Commission, CommissionStatement, Company, Course, CustomerLicense,
    CustomerOwnership, DealRegistration, DocRequest, Enrollment, KBDocument,
    KBDownloadLog, Notification, OppDocument, Opportunity, PartnerTierHistory,
    Poc, SalesActivity, TierCommissionRate, User,
)
from app.models.sales_activity import ActivityType
from app.utils.customer_normalize import normalize_customer_name

random.seed(20260801)

NOW = datetime.now(timezone.utc)
TODAY = date.today()
SENTINEL_COMPANY = "TechVantage Solutions"
DEMO_PASSWORD = "Extravis@2026"

# One bcrypt hash reused for every demo account (hashing is slow).
PW_HASH = hash_password(DEMO_PASSWORD)

MINIMAL_PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj\n"
    b"4 0 obj<</Length 62>>stream\nBT /F1 18 Tf 72 720 Td (Extravis Demo Document) Tj ET\nendstream endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


def _write_upload(rel_path: str) -> str:
    """Write a tiny valid PDF under UPLOAD_DIR and return its /uploads URL."""
    import os
    from app.core.config import settings

    full = os.path.join(settings.UPLOAD_DIR, rel_path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as f:
        f.write(MINIMAL_PDF)
    return f"/uploads/{rel_path}"


def days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def weekdays_between(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


async def main() -> None:
    async with async_session_factory() as db:
        exists = await db.execute(select(Company.id).where(Company.name == SENTINEL_COMPANY))
        if exists.scalar_one_or_none() is not None:
            print("Seed data already present (sentinel company found) — nothing to do.")
            return

        sa_result = await db.execute(select(User).where(User.is_superadmin.is_(True)))
        superadmin = sa_result.scalars().first()
        if superadmin is None:
            print("ERROR: no superadmin found — run init_db first.")
            return

        # ------------------------------------------------------------------
        # Channel managers (admins) and sales reps
        # ------------------------------------------------------------------
        def make_user(name, email, role, title, phone, company=None, superadmin_flag=False):
            return User(
                full_name=name, email=email, password_hash=PW_HASH, role=role,
                status="active", job_title=title, phone=phone,
                company_id=company.id if company else None,
                is_superadmin=superadmin_flag, has_completed_onboarding=True,
                last_login_at=days_ago(random.randint(0, 3)),
            )

        cm_ahmed = make_user("Ahmed Raza", "ahmed.raza@extravis.com", "admin",
                             "Channel Manager — GCC", "+971-50-114-2201")
        cm_sara = make_user("Sara Iqbal", "sara.iqbal@extravis.com", "admin",
                            "Channel Manager — South Asia", "+92-300-842-7743")
        db.add_all([cm_ahmed, cm_sara])
        await db.flush()

        rep_bilal = make_user("Bilal Hussain", "bilal.hussain@extravis.com", "sales_rep",
                              "Solutions Engineer", "+92-321-556-9034")
        rep_fatima = make_user("Fatima Noor", "fatima.noor@extravis.com", "sales_rep",
                               "Senior Sales Engineer", "+971-52-889-1276")
        rep_usman = make_user("Usman Tariq", "usman.tariq@extravis.com", "sales_rep",
                              "Deployment Lead", "+92-333-410-6688")
        db.add_all([rep_bilal, rep_fatima, rep_usman])
        await db.flush()
        reps = [rep_bilal, rep_fatima, rep_usman]

        # ------------------------------------------------------------------
        # Partner companies + partner users
        # ------------------------------------------------------------------
        companies_spec = [
            (SENTINEL_COMPANY, "United Arab Emirates", "Middle East", "Dubai",
             "IT Services & System Integration", "info@techvantage.ae", "gold", cm_ahmed),
            ("NetSphere Systems", "Saudi Arabia", "Middle East", "Riyadh",
             "Telecommunications", "contact@netsphere.sa", "platinum", cm_ahmed),
            ("Gulf Digital Networks", "Qatar", "Middle East", "Doha",
             "Managed Network Services", "hello@gulfdigital.qa", "silver", cm_ahmed),
            ("Alpha ICT", "Pakistan", "South Asia", "Karachi",
             "Enterprise IT Distribution", "sales@alphaict.pk", "gold", cm_sara),
            ("Orion Telecom Integrators", "Pakistan", "South Asia", "Lahore",
             "Telecom Infrastructure", "info@oriontelecom.pk", "silver", cm_sara),
            ("FutureLink IT", "United Arab Emirates", "Middle East", "Abu Dhabi",
             "Cybersecurity & Networking", "team@futurelink.ae", "silver", cm_sara),
        ]
        companies = []
        for name, country, region, city, industry, email, tier, cm in companies_spec:
            c = Company(name=name, country=country, region=region, city=city,
                        industry=industry, contact_email=email, status="active",
                        tier=tier, channel_manager_id=cm.id,
                        # Demo companies are channel partners; the customer
                        # classification is exercised by app.core.seed_demo.
                        company_type="partner")
            companies.append(c)
        db.add_all(companies)
        await db.flush()
        c_tech, c_net, c_gulf, c_alpha, c_orion, c_future = companies

        partners_spec = [
            ("Omar Al-Farsi", "omar.alfarsi@techvantage.ae", "Business Development Manager", "+971-50-223-8890", c_tech),
            ("Layla Haddad", "layla.haddad@techvantage.ae", "Presales Consultant", "+971-55-661-2043", c_tech),
            ("Khalid Al-Otaibi", "khalid.otaibi@netsphere.sa", "Sales Director", "+966-55-301-7742", c_net),
            ("Noura Al-Zahrani", "noura.zahrani@netsphere.sa", "Account Manager", "+966-50-118-3356", c_net),
            ("Hassan Jassim", "hassan.jassim@gulfdigital.qa", "Managing Partner", "+974-3341-2287", c_gulf),
            ("Imran Sheikh", "imran.sheikh@alphaict.pk", "Head of Enterprise Sales", "+92-321-224-5511", c_alpha),
            ("Ayesha Malik", "ayesha.malik@alphaict.pk", "Solutions Architect", "+92-300-119-8472", c_alpha),
            ("Danish Qureshi", "danish.qureshi@oriontelecom.pk", "Director Sales", "+92-333-702-1198", c_orion),
            ("Mariam Saeed", "mariam.saeed@futurelink.ae", "Channel Sales Manager", "+971-56-410-9923", c_future),
        ]
        partners = [make_user(n, e, "partner", t, p, company=c) for n, e, t, p, c in partners_spec]
        db.add_all(partners)
        await db.flush()
        (p_omar, p_layla, p_khalid, p_noura, p_hassan,
         p_imran, p_ayesha, p_danish, p_mariam) = partners

        # ------------------------------------------------------------------
        # Tier commission rates
        # ------------------------------------------------------------------
        db.add_all([
            TierCommissionRate(tier="silver", percentage=Decimal("3.00"), effective_from=date(2025, 1, 1)),
            TierCommissionRate(tier="gold", percentage=Decimal("5.00"), effective_from=date(2025, 1, 1)),
            TierCommissionRate(tier="platinum", percentage=Decimal("7.00"), effective_from=date(2025, 1, 1)),
        ])

        # Tier history
        db.add_all([
            PartnerTierHistory(company_id=c_tech.id, previous_tier="silver", new_tier="gold",
                               reason="Exceeded $500k annual registered pipeline", changed_by=superadmin.id,
                               changed_at=days_ago(140)),
            PartnerTierHistory(company_id=c_net.id, previous_tier="gold", new_tier="platinum",
                               reason="Three consecutive quarters above quota; certified deployment team",
                               changed_by=superadmin.id, changed_at=days_ago(75)),
        ])

        # ------------------------------------------------------------------
        # Opportunities (all statuses; one multi-partner conflict pair)
        # ------------------------------------------------------------------
        def opp(name, customer, company, submitter, *, worth, status, country=None,
                city=None, region=None, industry, product, prob, tf, req,
                rep=None, reviewed_by=None, days_old=30, rejection=None,
                notes=None, alert=False, dup_of=None, ai_score=None):
            country = country or company.country
            region = region or company.region
            city = city or company.city
            submitted = days_ago(days_old) if status != "draft" else None
            reviewed = (days_ago(max(days_old - 3, 1))
                        if status in ("approved", "rejected", "under_review") else None)
            return Opportunity(
                name=name, customer_name=customer,
                customer_name_normalized=normalize_customer_name(customer),
                region=region, country=country, city=city,
                worth=Decimal(worth), closing_date=TODAY + timedelta(days=random.randint(45, 240)),
                requirements=req, industry=industry, product=product,
                stage_probability=Decimal(prob), time_frame=tf,
                sales_rep_id=rep.id if rep else None,
                status=status, preferred_partner=(status == "approved" and random.random() < 0.4),
                multi_partner_alert=alert, rejection_reason=rejection,
                internal_notes=notes, ai_score=ai_score,
                ai_reasoning=("Strong fit: large device estate, defined budget and an executive sponsor."
                              if ai_score else None),
                ai_scored_at=days_ago(days_old - 1) if ai_score else None,
                ai_duplicate_of_id=dup_of,
                submitted_by=submitter.id, company_id=company.id,
                reviewed_by=reviewed_by.id if reviewed_by else None,
                submitted_at=submitted, reviewed_at=reviewed,
            )

        o1 = opp("HBL Core Network Observability", "HBL Bank", c_alpha, p_imran,
                 worth="240000.00", status="approved", industry="Banking",
                 product="Extravis NPM Suite", prob="0.80", tf="Q1 2027",
                 req="End-to-end network performance monitoring for 4 data centres, ~3,800 devices. "
                     "Needs NetFlow analytics, config compliance and SLA dashboards for the NOC.",
                 rep=rep_bilal, reviewed_by=cm_sara, days_old=95, ai_score=88)
        o2 = opp("Etisalat Metro Ring Monitoring", "Etisalat", c_tech, p_omar,
                 worth="410000.00", status="approved", industry="Telecommunications",
                 product="Extravis NPM Suite", prob="0.70", tf="Q4 2026",
                 req="Carrier-grade monitoring for metro Ethernet rings across Dubai and Sharjah; "
                     "5,000+ nodes, multi-tenant dashboards for wholesale customers.",
                 rep=rep_fatima, reviewed_by=cm_ahmed, days_old=80, ai_score=91)
        o3 = opp("QNB Branch Network Refresh", "Qatar National Bank", c_gulf, p_hassan,
                 worth="185000.00", status="approved", industry="Banking",
                 product="Extravis Observability Core", prob="0.60", tf="H1 2027",
                 req="Monitoring stack for 220 branches post SD-WAN refresh. Emphasis on circuit "
                     "utilisation, voice quality metrics and automated incident tickets.",
                 rep=rep_usman, reviewed_by=cm_ahmed, days_old=60, ai_score=76)
        o4 = opp("K-Electric Grid Telemetry", "K-Electric", c_alpha, p_ayesha,
                 worth="320000.00", status="approved", industry="Utilities",
                 product="Extravis IoT Monitor", prob="0.65", tf="Q2 2027",
                 req="OT/IT converged monitoring for grid substations — 1,200 RTUs, SCADA-adjacent "
                     "polling with strict read-only access and air-gapped reporting node.",
                 rep=rep_bilal, reviewed_by=cm_sara, days_old=50, ai_score=82)
        o5 = opp("Emirates NBD SOC Visibility", "Emirates NBD", c_future, p_mariam,
                 worth="150000.00", status="under_review", industry="Banking",
                 product="Extravis Observability Core", prob="0.50", tf="Q1 2027",
                 req="Network telemetry feed into the SOC SIEM; packet-broker integration and "
                     "east-west traffic visibility for two DCs.",
                 reviewed_by=cm_sara, days_old=12, ai_score=74)
        o6 = opp("Zong LTE Backhaul Assurance", "Zong CMPak", c_orion, p_danish,
                 worth="275000.00", status="pending_review", industry="Telecommunications",
                 product="Extravis NPM Suite", prob="0.45", tf="H2 2027",
                 req="Backhaul assurance for 8,000 LTE sites; microwave link quality KPIs, "
                     "threshold alerting into existing OSS.",
                 days_old=4, ai_score=79)
        o7 = opp("PTCL Exchange Modernisation", "PTCL", c_orion, p_danish,
                 worth="95000.00", status="rejected", industry="Telecommunications",
                 product="Extravis Observability Core", prob="0.30", tf="Q4 2026",
                 req="Monitoring for 40 modernised exchanges.",
                 reviewed_by=cm_sara, days_old=70,
                 rejection="Deal size below engagement threshold for this quarter and the customer "
                           "already runs a competing platform under contract until mid-2027.")
        o8 = opp("Meezan Bank DR Site Monitoring", "Meezan Bank", c_alpha, p_imran,
                 worth="60000.00", status="draft", industry="Banking",
                 product="Extravis Observability Core", prob="0.25", tf="H1 2027",
                 req="DR data centre monitoring scoped to 300 devices; draft pending internal signoff.",
                 days_old=2)
        # Multi-partner conflict pair: same customer, same country, two partners.
        o9 = opp("ADNOC Downstream Network Monitoring", "ADNOC", c_tech, p_layla,
                 worth="500000.00", status="under_review", industry="Oil & Gas",
                 product="Extravis NPM Suite", prob="0.55", tf="Q2 2027",
                 req="Refinery campus network monitoring — 6 sites, 4,500 devices, redundant pollers.",
                 reviewed_by=cm_ahmed, days_old=20, alert=True, ai_score=85,
                 notes="Multi-partner conflict with FutureLink submission — awaiting customer LOA.")
        o10 = opp("ADNOC Refining Network Visibility", "ADNOC", c_future, p_mariam,
                  worth="465000.00", status="multi_partner_flagged", industry="Oil & Gas",
                  product="Extravis NPM Suite", prob="0.40", tf="Q2 2027",
                  req="Network visibility programme for refining division; overlaps ADNOC campus scope.",
                  days_old=15, alert=True)
        o11 = opp("Ooredoo Fibre Rollout QoS", "Ooredoo", c_gulf, p_hassan,
                  worth="210000.00", status="pending_review", industry="Telecommunications",
                  product="Extravis NPM Suite", prob="0.40", tf="H2 2027",
                  req="QoS assurance for FTTH rollout, 600k homes passed; PON OLT/ONT telemetry.",
                  days_old=6)
        o12 = opp("Habib Bank Limited — NOC Consolidation", "HBL", c_orion, p_danish,
                  worth="230000.00", status="pending_review", industry="Banking",
                  product="Extravis NPM Suite", prob="0.35", tf="Q1 2027",
                  req="NOC tooling consolidation; likely the same initiative as the HBL core network "
                      "observability programme registered earlier.",
                  days_old=3)
        opps = [o1, o2, o3, o4, o5, o6, o7, o8, o9, o10, o11, o12]
        db.add_all(opps)
        await db.flush()
        # AI flagged o12 as a probable duplicate of o1 (same normalized customer).
        o12.ai_duplicate_of_id = o1.id

        db.add_all([
            OppDocument(opportunity_id=o1.id, file_name="HBL_BoQ_v3.pdf",
                        file_url=_write_upload("opportunities/hbl_boq_v3.pdf"),
                        file_size=len(MINIMAL_PDF), content_type="application/pdf",
                        uploaded_at=days_ago(90)),
            OppDocument(opportunity_id=o2.id, file_name="Etisalat_HLD_draft.pdf",
                        file_url=_write_upload("opportunities/etisalat_hld_draft.pdf"),
                        file_size=len(MINIMAL_PDF), content_type="application/pdf",
                        uploaded_at=days_ago(70)),
        ])

        # ------------------------------------------------------------------
        # POCs + customer licenses
        # ------------------------------------------------------------------
        db.add_all([
            # Successful, fully closed POC → active license
            Poc(opportunity_id=o1.id, status="successful",
                start_date=TODAY - timedelta(days=85), target_end_date=TODAY - timedelta(days=40),
                end_date=TODAY - timedelta(days=42),
                vm_provisioning_completed_at=TODAY - timedelta(days=80),
                deployment_completed_at=TODAY - timedelta(days=72),
                device_onboarding_completed_at=TODAY - timedelta(days=60),
                dashboarding_completed_at=TODAY - timedelta(days=50),
                fine_tuning_completed_at=TODAY - timedelta(days=44),
                closed_at=days_ago(42), closed_by=rep_bilal.id,
                outcome_notes="All 3,800 devices onboarded; NOC signed off SLA dashboards. "
                              "PO issued within three weeks of closure."),
            # Running POC, mid-flight
            Poc(opportunity_id=o2.id, status="running",
                start_date=TODAY - timedelta(days=30), target_end_date=TODAY + timedelta(days=15),
                vm_provisioning_completed_at=TODAY - timedelta(days=26),
                deployment_completed_at=TODAY - timedelta(days=18),
                device_onboarding_completed_at=TODAY - timedelta(days=6),
                notes="Dashboarding workshop scheduled with the wholesale team next week."),
            # Not started yet
            Poc(opportunity_id=o3.id, status="not_started",
                target_end_date=TODAY + timedelta(days=60),
                notes="Awaiting VPN access approvals from QNB security."),
            # Unsuccessful POC
            Poc(opportunity_id=o4.id, status="unsuccessful",
                start_date=TODAY - timedelta(days=70), target_end_date=TODAY - timedelta(days=20),
                end_date=TODAY - timedelta(days=25),
                vm_provisioning_completed_at=TODAY - timedelta(days=65),
                deployment_completed_at=TODAY - timedelta(days=55),
                closed_at=days_ago(25), closed_by=rep_bilal.id,
                failure_reason="OT security policy blocked SNMP polling on substation RTUs",
                outcome_notes="Revisit after the customer's OT segmentation project completes in 2027."),
        ])

        db.add_all([
            CustomerLicense(opportunity_id=o1.id, po_number="HBL-PO-2026-0447",
                            po_received_date=TODAY - timedelta(days=35),
                            po_value=Decimal("240000.00"), device_count=3800, node_count=6,
                            license_activated_at=TODAY - timedelta(days=28),
                            license_expires_at=TODAY + timedelta(days=337),
                            license_key="EXTV-HBL-9F27-A1C4-2026", status="active",
                            notes="12-month subscription incl. premium support."),
            CustomerLicense(opportunity_id=o3.id, po_number="QNB-PO-2026-1180",
                            po_received_date=TODAY - timedelta(days=10),
                            po_value=Decimal("185000.00"), device_count=1400, node_count=3,
                            status="pending_activation",
                            notes="PO received ahead of POC — activation blocked on security review."),
            CustomerLicense(opportunity_id=o2.id, po_number="ETIS-TRIAL-2026-071",
                            po_received_date=TODAY - timedelta(days=380),
                            po_value=Decimal("38000.00"), device_count=500, node_count=1,
                            license_activated_at=TODAY - timedelta(days=370),
                            license_expires_at=TODAY + timedelta(days=18),
                            license_key="EXTV-ETIS-4B11-77D0-2025", status="expiring_soon",
                            notes="Pilot ring license — renewal wrapped into the metro ring deal."),
        ])

        # ------------------------------------------------------------------
        # Deal registrations, ownership, commissions
        # ------------------------------------------------------------------
        d1 = DealRegistration(company_id=c_alpha.id, registered_by=p_imran.id, opportunity_id=o1.id,
                              customer_name="HBL Bank",
                              deal_description="Core network observability for 4 DCs — NPM suite, 3,800 devices.",
                              estimated_value=Decimal("240000.00"),
                              expected_close_date=TODAY + timedelta(days=60), status="approved",
                              exclusivity_start=TODAY - timedelta(days=90),
                              exclusivity_end=TODAY + timedelta(days=90),
                              approved_by=cm_sara.id, approved_at=days_ago(90))
        d2 = DealRegistration(company_id=c_tech.id, registered_by=p_omar.id, opportunity_id=o2.id,
                              customer_name="Etisalat",
                              deal_description="Metro Ethernet ring monitoring, Dubai + Sharjah, 5,000 nodes.",
                              estimated_value=Decimal("410000.00"),
                              expected_close_date=TODAY + timedelta(days=120), status="approved",
                              exclusivity_start=TODAY - timedelta(days=75),
                              exclusivity_end=TODAY + timedelta(days=105),
                              approved_by=cm_ahmed.id, approved_at=days_ago(75))
        d3 = DealRegistration(company_id=c_gulf.id, registered_by=p_hassan.id, opportunity_id=o3.id,
                              customer_name="Qatar National Bank",
                              deal_description="Branch network monitoring post SD-WAN refresh — 220 branches.",
                              estimated_value=Decimal("185000.00"),
                              expected_close_date=TODAY + timedelta(days=150), status="approved",
                              exclusivity_start=TODAY - timedelta(days=55),
                              exclusivity_end=TODAY + timedelta(days=125),
                              approved_by=cm_ahmed.id, approved_at=days_ago(55))
        d4 = DealRegistration(company_id=c_future.id, registered_by=p_mariam.id,
                              customer_name="Dubai Municipality",
                              deal_description="Smart-city sensor network monitoring pilot, 900 IoT gateways.",
                              estimated_value=Decimal("130000.00"),
                              expected_close_date=TODAY + timedelta(days=100), status="pending")
        d5 = DealRegistration(company_id=c_orion.id, registered_by=p_danish.id,
                              customer_name="Askari Bank",
                              deal_description="ATM connectivity monitoring, 600 sites.",
                              estimated_value=Decimal("75000.00"),
                              expected_close_date=TODAY - timedelta(days=10), status="expired",
                              exclusivity_start=TODAY - timedelta(days=190),
                              exclusivity_end=TODAY - timedelta(days=10),
                              approved_by=cm_sara.id, approved_at=days_ago(190))
        d6 = DealRegistration(company_id=c_net.id, registered_by=p_khalid.id,
                              customer_name="stc",
                              deal_description="5G transport network assurance — phase 1 scoping.",
                              estimated_value=Decimal("620000.00"),
                              expected_close_date=TODAY + timedelta(days=200), status="rejected",
                              rejection_reason="Direct-touch account handled by Extravis KSA enterprise team.")
        db.add_all([d1, d2, d3, d4, d5, d6])
        await db.flush()

        db.add_all([
            CustomerOwnership(customer_name_normalized=normalize_customer_name("HBL Bank"),
                              country="Pakistan", city="Karachi", company_id=c_alpha.id,
                              source_deal_id=d1.id, source_opportunity_id=o1.id,
                              valid_from=TODAY - timedelta(days=90),
                              valid_until=TODAY + timedelta(days=90), is_active=True),
            CustomerOwnership(customer_name_normalized=normalize_customer_name("Etisalat"),
                              country="United Arab Emirates", city="Dubai", company_id=c_tech.id,
                              source_deal_id=d2.id, source_opportunity_id=o2.id,
                              valid_from=TODAY - timedelta(days=75),
                              valid_until=TODAY + timedelta(days=105), is_active=True),
            CustomerOwnership(customer_name_normalized=normalize_customer_name("Qatar National Bank"),
                              country="Qatar", city="Doha", company_id=c_gulf.id,
                              source_deal_id=d3.id, source_opportunity_id=o3.id,
                              valid_from=TODAY - timedelta(days=55),
                              valid_until=TODAY + timedelta(days=125), is_active=True),
        ])

        def commission(deal, company, user, tier, rate, status, days_back, note=None):
            amount = (deal.estimated_value * Decimal(rate) / Decimal(100)).quantize(Decimal("0.01"))
            return Commission(
                deal_id=deal.id, company_id=company.id, user_id=user.id,
                tier_at_calculation=tier, rate_percentage=Decimal(rate),
                deal_value=deal.estimated_value, amount=amount, currency="USD",
                status=status, notes=note, calculated_at=days_ago(days_back),
                approved_at=days_ago(days_back - 5) if status in ("approved", "paid") else None,
                paid_at=days_ago(days_back - 20) if status == "paid" else None,
            )

        db.add_all([
            commission(d1, c_alpha, p_imran, "gold", "5.00", "paid", 60,
                       "Paid with July statement."),
            commission(d2, c_tech, p_omar, "gold", "5.00", "approved", 40),
            commission(d3, c_gulf, p_hassan, "silver", "3.00", "pending", 20),
        ])
        db.add_all([
            CommissionStatement(company_id=c_alpha.id,
                                period_start=TODAY.replace(day=1) - timedelta(days=31),
                                period_end=TODAY.replace(day=1) - timedelta(days=1),
                                total_amount=Decimal("12000.00"), commission_count=1,
                                generated_at=days_ago(15)),
        ])

        # ------------------------------------------------------------------
        # Knowledge base
        # ------------------------------------------------------------------
        kb_spec = [
            ("Extravis NPM Suite — Datasheet 2026", "Datasheets",
             "Feature overview, supported vendors, polling scale limits and licensing tiers."),
            ("Observability Core — Technical Datasheet", "Datasheets",
             "Architecture, collector sizing and HA topology options for Observability Core."),
            ("Deployment & Sizing Guide v4.2", "Technical Guides",
             "VM sizing per 1k devices, storage retention math, poller placement patterns."),
            ("SD-WAN Monitoring Integration Guide", "Technical Guides",
             "Onboarding Cisco/Fortinet SD-WAN fabrics — API credentials, KPIs, alert templates."),
            ("Competitive Battlecard — Q3 2026", "Sales Enablement",
             "Positioning against SolarWinds, PRTG and LogicMonitor with objection handling."),
            ("Partner Price List — 2026 H2 (Confidential)", "Pricing",
             "Tiered partner pricing, deal-registration discounts and support SKUs."),
            ("Case Study — Tier-1 Bank NOC Transformation", "Case Studies",
             "How a 4-DC bank cut MTTR by 44% with unified network observability."),
            ("SOC/SIEM Telemetry Export Guide", "Technical Guides",
             "Streaming enriched flow and syslog telemetry to Splunk, Sentinel and QRadar."),
        ]
        kb_docs = []
        for i, (title, cat, desc) in enumerate(kb_spec):
            fname = title.split("—")[0].strip().lower().replace(" ", "_").replace("/", "_")[:40] + ".pdf"
            kb_docs.append(KBDocument(
                title=title, category=cat, description=desc, file_name=fname,
                file_url=_write_upload(f"knowledge-base/{fname}"),
                file_size=len(MINIMAL_PDF), content_type="application/pdf",
                version=1, uploaded_by=superadmin.id, is_archived=0,
                published_at=days_ago(random.randint(10, 160)),
            ))
        db.add_all(kb_docs)
        await db.flush()
        db.add_all([
            KBDownloadLog(document_id=kb_docs[0].id, user_id=p_omar.id, downloaded_at=days_ago(9)),
            KBDownloadLog(document_id=kb_docs[2].id, user_id=p_imran.id, downloaded_at=days_ago(6)),
            KBDownloadLog(document_id=kb_docs[4].id, user_id=p_hassan.id, downloaded_at=days_ago(2)),
            KBDownloadLog(document_id=kb_docs[2].id, user_id=rep_usman.id, downloaded_at=days_ago(1)),
        ])

        # ------------------------------------------------------------------
        # LMS: courses + enrollments
        # ------------------------------------------------------------------
        course1 = Course(
            title="Extravis Platform Fundamentals",
            description="Product architecture, licensing model and a guided tour of the core "
                        "monitoring workflows every partner engineer should know.",
            status="published", passing_score=70, duration_hours=4,
            created_by=superadmin.id,
            modules_json=[
                {"id": "m1", "title": "Platform Architecture Overview", "type": "video",
                 "content_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                 "duration_minutes": 35, "order": 1},
                {"id": "m2", "title": "Licensing & Sizing Basics", "type": "text",
                 "description": "How device/node licensing works, when to position each suite, "
                                "and the three sizing questions to ask in discovery.",
                 "duration_minutes": 25, "order": 2},
                {"id": "m3", "title": "Core Workflows Walkthrough", "type": "video",
                 "content_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                 "duration_minutes": 45, "order": 3},
                {"id": "m4", "title": "Knowledge Check", "type": "quiz", "order": 4},
            ],
            assessment_json=[
                {"id": 1, "question": "Which component collects SNMP telemetry from devices?",
                 "options": ["Poller node", "Dashboard node", "Report engine", "License server"],
                 "correct_answer": "Poller node"},
                {"id": 2, "question": "Licensing is primarily based on…",
                 "options": ["Users", "Devices/nodes", "Alerts per day", "Dashboards"],
                 "correct_answer": "Devices/nodes"},
                {"id": 3, "question": "What is the recommended HA pattern for pollers?",
                 "options": ["Active/active pairs", "Single poller", "Cold standby only", "DNS round-robin"],
                 "correct_answer": "Active/active pairs"},
            ],
        )
        course2 = Course(
            title="Advanced Deployment & Sizing",
            description="For deployment engineers: multi-site poller placement, storage retention "
                        "planning and tuning for 5k+ device estates.",
            status="published", passing_score=75, duration_hours=6,
            created_by=superadmin.id,
            modules_json=[
                {"id": "m1", "title": "Multi-site Poller Topologies", "type": "video",
                 "content_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                 "duration_minutes": 50, "order": 1},
                {"id": "m2", "title": "Retention & Storage Math", "type": "text",
                 "description": "Worked examples: 1k/5k/10k device estates with 13-month retention.",
                 "duration_minutes": 40, "order": 2},
                {"id": "m3", "title": "Certification Quiz", "type": "quiz", "order": 3},
            ],
            assessment_json=[
                {"id": 1, "question": "A 5,000-device estate typically needs how many pollers (HA)?",
                 "options": ["2", "4", "6", "8"], "correct_answer": "4"},
                {"id": 2, "question": "Raw flow records should be retained hot for…",
                 "options": ["24 hours", "7 days", "30 days", "13 months"],
                 "correct_answer": "7 days"},
            ],
        )
        course3 = Course(
            title="Sales Enablement Bootcamp 2027",
            description="Draft curriculum for the 2027 partner kickoff — discovery frameworks, "
                        "competitive positioning and demo storylines.",
            status="draft", passing_score=70, duration_hours=3, created_by=superadmin.id,
            modules_json=[
                {"id": "m1", "title": "Discovery Framework", "type": "text",
                 "description": "MEDDICC-lite discovery for network observability deals.",
                 "duration_minutes": 30, "order": 1},
            ],
            assessment_json=[],
        )
        db.add_all([course1, course2, course3])
        await db.flush()

        db.add_all([
            Enrollment(user_id=p_omar.id, course_id=course1.id, status="completed",
                       progress_json={"m1": True, "m2": True, "m3": True, "m4": True},
                       attempt_count=1, score=92, completed_at=days_ago(30),
                       enrolled_at=days_ago(45)),
            Enrollment(user_id=p_imran.id, course_id=course1.id, status="completed",
                       progress_json={"m1": True, "m2": True, "m3": True, "m4": True},
                       attempt_count=2, score=81, completed_at=days_ago(12),
                       enrolled_at=days_ago(40)),
            Enrollment(user_id=p_layla.id, course_id=course1.id, status="in_progress",
                       progress_json={"m1": True, "m2": True}, attempt_count=0,
                       enrolled_at=days_ago(15)),
            Enrollment(user_id=p_hassan.id, course_id=course1.id, status="enrolled",
                       progress_json={}, attempt_count=0, enrolled_at=days_ago(5)),
            Enrollment(user_id=p_ayesha.id, course_id=course2.id, status="in_progress",
                       progress_json={"m1": True}, attempt_count=0, enrolled_at=days_ago(20)),
            Enrollment(user_id=p_khalid.id, course_id=course2.id, status="completed",
                       progress_json={"m1": True, "m2": True, "m3": True},
                       attempt_count=1, score=88, completed_at=days_ago(8),
                       enrolled_at=days_ago(25)),
        ])

        # ------------------------------------------------------------------
        # Doc requests
        # ------------------------------------------------------------------
        dr_pending = DocRequest(company_id=c_net.id, requested_by=p_noura.id,
                                description="Arabic datasheet for the NPM Suite for a government tender.",
                                reason="stc tender submission requires Arabic collateral", urgency="high",
                                status="pending", created_at=days_ago(2))
        db.add_all([
            dr_pending,
            DocRequest(company_id=c_alpha.id, requested_by=p_imran.id,
                       description="Reference architecture for banking DR-site monitoring.",
                       reason="Meezan Bank DR proposal", urgency="medium", status="fulfilled",
                       fulfilled_by=cm_sara.id, fulfilled_at=days_ago(6),
                       fulfilled_file_url=_write_upload("doc-requests/banking_dr_reference.pdf"),
                       fulfilled_file_name="banking_dr_reference.pdf", add_to_kb=1,
                       created_at=days_ago(10)),
            DocRequest(company_id=c_gulf.id, requested_by=p_hassan.id,
                       description="Custom SLA credit matrix template for QNB contract.",
                       reason="Legal wants a per-branch SLA model", urgency="low",
                       status="declined",
                       decline_reason="Commercial/legal templates are issued by Extravis legal "
                                      "directly — routed to your channel manager.",
                       created_at=days_ago(14)),
        ])

        await db.flush()  # doc requests get ids for the notification below

        # ------------------------------------------------------------------
        # Sales activities (current + previous month, weekdays only)
        # ------------------------------------------------------------------
        activity_pool = [
            (ActivityType.CALL, "Intro call — pipeline review", 30),
            (ActivityType.MEETING, "On-site technical workshop", 90),
            (ActivityType.DEMO, "Platform demo for NOC team", 60),
            (ActivityType.EMAIL, "Sent sizing questionnaire + follow-up", 15),
            (ActivityType.SITE_VISIT, "DC walkthrough with facilities", 150),
            (ActivityType.FOLLOW_UP, "Follow-up on POC blockers", 25),
            (ActivityType.TRAINING, "Partner engineer enablement session", 120),
            (ActivityType.OTHER, "Prepared HLD annexures", 45),
        ]
        rep_customers = {
            rep_bilal.id: [("HBL Bank", o1.id), ("K-Electric", o4.id), ("Meezan Bank", None)],
            rep_fatima.id: [("Etisalat", o2.id), ("Emirates NBD", None), ("ADNOC", None)],
            rep_usman.id: [("Qatar National Bank", o3.id), ("Ooredoo", None), ("PTCL", None)],
        }
        window_start = (TODAY.replace(day=1) - timedelta(days=1)).replace(day=1)
        activities = []
        for rep in reps:
            for d in weekdays_between(window_start, TODAY):
                for _ in range(random.choices([0, 1, 2, 3], weights=[25, 40, 25, 10])[0]):
                    a_type, note, dur = random.choice(activity_pool)
                    customer, opp_id = random.choice(rep_customers[rep.id])
                    activities.append(SalesActivity(
                        user_id=rep.id, activity_date=d, activity_type=a_type,
                        customer_name=customer, opportunity_id=opp_id,
                        duration_minutes=dur + random.choice([-10, -5, 0, 5, 10, 15]),
                        notes=note,
                        created_at=datetime(d.year, d.month, d.day, 17, 30, tzinfo=timezone.utc),
                    ))
        db.add_all(activities)

        # ------------------------------------------------------------------
        # Notifications + audit trail
        # ------------------------------------------------------------------
        db.add_all([
            Notification(user_id=p_imran.id, type="opportunity_approved",
                         title="Opportunity approved",
                         message="'HBL Core Network Observability' was approved by Sara Iqbal.",
                         read=True, entity_type="opportunity", entity_id=o1.id,
                         created_at=days_ago(92)),
            Notification(user_id=p_omar.id, type="commission_approved",
                         title="Commission approved",
                         message="Your $20,500.00 commission for the Etisalat deal was approved.",
                         read=False, entity_type="commission", entity_id=d2.id,
                         created_at=days_ago(35)),
            Notification(user_id=p_mariam.id, type="multi_partner_conflict",
                         title="Possible duplicate registration",
                         message="Your ADNOC submission overlaps another partner's registered deal "
                                 "and has been flagged for review.",
                         read=False, entity_type="opportunity", entity_id=o10.id,
                         created_at=days_ago(15)),
            Notification(user_id=cm_ahmed.id, type="doc_request_created",
                         title="New document request",
                         message="NetSphere Systems requested an Arabic NPM datasheet (high urgency).",
                         read=False, entity_type="doc_request", entity_id=dr_pending.id,
                         created_at=days_ago(2)),
            Notification(user_id=rep_fatima.id, type="poc_milestone",
                         title="POC milestone completed",
                         message="Device onboarding completed for the Etisalat metro ring POC.",
                         read=True, entity_type="poc", entity_id=o2.id,
                         created_at=days_ago(6)),
        ])

        db.add_all([
            AuditLog(user_id=superadmin.id, action="CREATE", entity_type="company",
                     entity_id=c_tech.id, metadata_json={"name": SENTINEL_COMPANY},
                     ip_address="10.20.0.4", timestamp=days_ago(160)),
            AuditLog(user_id=cm_sara.id, action="APPROVE", entity_type="opportunity",
                     entity_id=o1.id, metadata_json={"status": "approved"},
                     ip_address="10.20.0.11", timestamp=days_ago(92)),
            AuditLog(user_id=cm_ahmed.id, action="APPROVE", entity_type="deal_registration",
                     entity_id=d2.id, metadata_json={"exclusivity_months": 6},
                     ip_address="10.20.0.12", timestamp=days_ago(75)),
            AuditLog(user_id=rep_bilal.id, action="UPDATE", entity_type="poc",
                     entity_id=o1.id, metadata_json={"status": "successful"},
                     ip_address="10.20.0.31", timestamp=days_ago(42)),
            AuditLog(user_id=superadmin.id, action="UPDATE", entity_type="company",
                     entity_id=c_net.id, metadata_json={"tier": "platinum"},
                     ip_address="10.20.0.4", timestamp=days_ago(75)),
        ])

        await db.commit()

        print("Seed complete.")
        print(f"  Companies: {len(companies)}  Users: {2 + len(reps) + len(partners)} (+1 superadmin)")
        print(f"  Opportunities: {len(opps)}  POCs: 4  Licenses: 3  Deals: 6  Commissions: 3")
        print(f"  KB docs: {len(kb_docs)}  Courses: 3  Enrollments: 6  Doc requests: 3")
        print(f"  Sales activities: {len(activities)}  Notifications: 5  Audit logs: 5")
        print(f"  Demo password for every seeded user: {DEMO_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
