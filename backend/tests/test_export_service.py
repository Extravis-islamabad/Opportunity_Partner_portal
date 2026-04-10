"""
Unit tests for export_service builders. Verifies the PDF and XLSX outputs
render without raising for both populated and empty result sets.
"""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.services.export_service import (
    build_company_pdf,
    build_company_xlsx,
    build_deal_xlsx,
    build_opportunity_pdf,
    build_opportunity_xlsx,
)


def _fake_company(id_: int = 1):
    return SimpleNamespace(
        id=id_,
        name=f"Acme {id_}",
        country="USA",
        region="NA",
        city="Austin",
        industry="Software",
        contact_email="hi@acme.test",
        tier=SimpleNamespace(value="gold"),
        status=SimpleNamespace(value="active"),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _fake_opportunity(id_: int = 1):
    return SimpleNamespace(
        id=id_,
        name=f"Deal {id_}",
        customer_name="Big Corp",
        region="NA",
        country="USA",
        worth=Decimal("100000.00"),
        closing_date=date(2026, 12, 31),
        status=SimpleNamespace(value="approved"),
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
        pdf = build_opportunity_pdf([_fake_opportunity(1), _fake_opportunity(2)])
        assert pdf.startswith(b"%PDF-")
        assert len(pdf) > 500

    def test_pdf_empty(self):
        pdf = build_opportunity_pdf([])
        assert pdf.startswith(b"%PDF-")

    def test_xlsx_populated(self):
        xlsx = build_opportunity_xlsx([_fake_opportunity(1)])
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
