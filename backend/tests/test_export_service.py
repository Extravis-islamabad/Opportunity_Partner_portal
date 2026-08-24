"""
Unit tests for export_service builders. Verifies the PDF and XLSX outputs
render without raising for both populated and empty result sets.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.models.opportunity import LossReason
from app.services.export_service import (
    COMPANY_HEADERS,
    _company_row,
    build_company_pdf,
    build_company_xlsx,
    build_deal_xlsx,
    build_opportunity_pdf,
    build_opportunity_xlsx,
)


def _fake_company(
    id_: int = 1,
    company_type: str = "partner",
    is_channel: bool = True,
    parent_distributor_name: str | None = None,
):
    return SimpleNamespace(
        id=id_,
        name=f"Acme {id_}",
        parent_distributor=(
            SimpleNamespace(name=parent_distributor_name)
            if parent_distributor_name
            else None
        ),
        country="USA",
        region="NA",
        city="Austin",
        industry="Software",
        contact_email="hi@acme.test",
        company_type=SimpleNamespace(value=company_type),
        is_channel_partner=is_channel,
        tier=SimpleNamespace(value="gold"),
        status=SimpleNamespace(value="active"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _fake_opportunity(id_: int = 1, *, lost: bool = False):
    return SimpleNamespace(
        id=id_,
        name=f"Deal {id_}",
        customer_name="Big Corp",
        region="NA",
        country="USA",
        worth=Decimal("100000.00"),
        closing_date=date(2026, 12, 31),
        status=SimpleNamespace(value="lost" if lost else "approved"),
        loss_reason=LossReason.COMPETITOR if lost else None,
        company=_fake_company(id_),
        submitted_by_user=SimpleNamespace(full_name="Jane Partner"),
        created_at=datetime(2026, 1, 15, tzinfo=timezone.utc),
    )


def _fake_deal(id_: int = 1):
    return SimpleNamespace(
        id=id_,
        customer_name="Big Corp",
        company=_fake_company(id_),
        deal_description="Multi-region rollout",
        estimated_value=Decimal("250000.00"),
        expected_close_date=date(2026, 11, 30),
        status=SimpleNamespace(value="approved"),
        exclusivity_start=date(2026, 1, 1),
        exclusivity_end=date(2026, 4, 1),
        created_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
    )


class TestOpportunityExport:
    def test_pdf_populated(self):
        # One won/open and one lost, so the loss-reason column renders both a
        # value and the blank that most rows carry.
        pdf = build_opportunity_pdf(
            [_fake_opportunity(1), _fake_opportunity(2, lost=True)]
        )
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 500

    def test_pdf_empty(self):
        pdf = build_opportunity_pdf([])
        assert pdf.startswith(b"%PDF-")

    def test_xlsx_populated(self):
        xlsx = build_opportunity_xlsx(
            [_fake_opportunity(1), _fake_opportunity(2, lost=True)]
        )
        # XLSX is a zip file: magic number PK
        assert xlsx[:2] == b"PK"

    def test_xlsx_empty(self):
        xlsx = build_opportunity_xlsx([])
        assert xlsx[:2] == b"PK"


class TestDealExport:
    def test_xlsx_populated(self):
        xlsx = build_deal_xlsx([_fake_deal(1), _fake_deal(2)])
        assert xlsx[:2] == b"PK"


class TestCompanyExport:
    def test_xlsx(self):
        xlsx = build_company_xlsx([_fake_company()])
        assert xlsx[:2] == b"PK"

    def test_pdf(self):
        pdf = build_company_pdf([_fake_company()])
        assert pdf.startswith(b"%PDF-")

    def test_headers_include_type(self):
        assert "Type" in COMPANY_HEADERS

    def test_pdf_column_widths_match_header_count(self):
        # The PDF builder passes a fixed col_widths list; a header added
        # without a matching width raises inside reportlab at build time.
        build_company_pdf([_fake_company()])

    def test_partner_row_carries_type_and_tier(self):
        row = _company_row(_fake_company(company_type="distributor"))
        assert row[COMPANY_HEADERS.index("Type")] == "Distributor"
        assert row[COMPANY_HEADERS.index("Tier")] == "Gold"

    def test_customer_row_has_type_but_blank_tier(self):
        # A customer keeps a tier value in the column but must never export it.
        row = _company_row(
            _fake_company(company_type="customer", is_channel=False)
        )
        assert row[COMPANY_HEADERS.index("Type")] == "Customer"
        assert row[COMPANY_HEADERS.index("Tier")] == ""

    def test_reseller_row_names_its_parent_distributor(self):
        row = _company_row(
            _fake_company(parent_distributor_name="Nordwind Distribution")
        )
        assert row[COMPANY_HEADERS.index("Parent Distributor")] == "Nordwind Distribution"

    def test_direct_company_has_blank_parent_distributor(self):
        # Most companies report straight to Extravis; the column must be empty
        # for them rather than repeating their own name.
        row = _company_row(_fake_company())
        assert row[COMPANY_HEADERS.index("Parent Distributor")] == ""

    def test_mixed_export_renders(self):
        companies = [
            _fake_company(1, "partner", parent_distributor_name="Nordwind"),
            _fake_company(2, "distributor"),
            _fake_company(3, "customer", is_channel=False),
        ]
        assert build_company_pdf(companies).startswith(b"%PDF-")
        assert build_company_xlsx(companies)[:2] == b"PK"
