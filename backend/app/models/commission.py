import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.company import PartnerTier


class CommissionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    PAID = "paid"
    VOID = "void"


class TierCommissionRate(Base):
    """
    Configuration table: commission percentage per partner tier.

    A row is keyed by `tier` and is effective from `effective_from` until
    `effective_to` (nullable means still active). Allows auditing historic
    rate changes without rewriting past commissions.
    """
    __tablename__ = "tier_commission_rates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tier = Column(
        Enum(PartnerTier, values_callable=lambda x: [e.value for e in x], name="partnertier"),
        nullable=False,
    )
    percentage = Column(Numeric(5, 2), nullable=False)
    effective_from = Column(Date, nullable=False)
    effective_to = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class Commission(Base):
    """
    One row per approved deal. Amount is calculated at deal-approval time
    using the partner's tier at that moment and the active TierCommissionRate.

    Idempotent: `deal_id` is UNIQUE so calling calculate_commission_for_deal
    twice for the same deal won't create duplicates.
    """
    __tablename__ = "commissions"
    __table_args__ = (
        UniqueConstraint("deal_id", name="uq_commissions_deal_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    deal_id = Column(Integer, ForeignKey("deal_registrations.id"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)

    tier_at_calculation = Column(
        Enum(PartnerTier, values_callable=lambda x: [e.value for e in x], name="partnertier"),
        nullable=False,
    )
    rate_percentage = Column(Numeric(5, 2), nullable=False)
    deal_value = Column(Numeric(14, 2), nullable=False)
    amount = Column(Numeric(14, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="USD")

    status = Column(
        Enum(CommissionStatus, values_callable=lambda x: [e.value for e in x], name="commissionstatus"),
        nullable=False,
        default=CommissionStatus.PENDING,
    )
    notes = Column(Text, nullable=True)

    calculated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    deal = relationship("DealRegistration", back_populates="commission")
    company = relationship("Company")
    user = relationship("User")


class CommissionStatement(Base):
    """
    A rolled-up monthly statement for a company — aggregates Commission rows
    within a period. Lightweight for now; PDF path is optional so statements
    can be generated lazily.
    """
    __tablename__ = "commission_statements"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    total_amount = Column(Numeric(14, 2), nullable=False, default=0)
    commission_count = Column(Integer, nullable=False, default=0)
    pdf_url = Column(String(500), nullable=True)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company")
