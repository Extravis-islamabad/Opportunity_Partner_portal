import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Computed, Integer, String, DateTime, Enum, ForeignKey, Text, Date,
    Numeric, Boolean, JSON,
)
from sqlalchemy.orm import relationship
from app.models.currency import Currency
from app.core.database import Base


class DealStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class DealRegistration(Base):
    __tablename__ = "deal_registrations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    registered_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True, index=True)
    customer_name = Column(String(200), nullable=False)
    deal_description = Column(Text, nullable=False)
    estimated_value = Column(Numeric(15, 2), nullable=False)

    # Same shape as an opportunity's: the currency the deal is in, the rate
    # that was true when it was registered, and the reporting value Postgres
    # derives from the two. Commission is calculated from the USD figure, so
    # a partner in Karachi and one in Dubai are paid on comparable numbers.
    currency = Column(
        Enum(Currency, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        server_default=Currency.USD.value,
        default=Currency.USD,
        index=True,
    )
    exchange_rate_to_usd = Column(
        Numeric(18, 6), nullable=False, server_default="1.0", default=1
    )
    estimated_value_usd = Column(
        Numeric(18, 2),
        Computed("estimated_value * exchange_rate_to_usd", persisted=True),
    )
    expected_close_date = Column(Date, nullable=False)

    # --- Client details: who the end client is beyond the name. All nullable
    # so registrations predating these fields stay valid; the form decides
    # what is required.
    client_email = Column(String(255), nullable=True)
    client_website = Column(String(255), nullable=True)
    client_contact = Column(String(50), nullable=True)
    client_fax = Column(String(50), nullable=True)
    client_address = Column(String(500), nullable=True)
    individual_name = Column(String(255), nullable=True)
    individual_department = Column(String(255), nullable=True)
    individual_designation = Column(String(255), nullable=True)

    # --- Opportunity type: tender or non_tender, with the supporting detail.
    # A plain string, not a Postgres enum: two values do not earn a type that
    # every future value would need a migration to extend.
    opportunity_type = Column(String(20), nullable=True)
    opportunity_name = Column(String(200), nullable=True)
    tender_number = Column(String(100), nullable=True)
    tender_submission_date = Column(Date, nullable=True)
    mal_maf_required = Column(Boolean, nullable=True)
    poc_required = Column(Boolean, nullable=True)
    # Product names off the shared catalogue (PRODUCTS). A JSON list rather
    # than a line table: deals carry no per-product sizing the way
    # opportunities do, only which products the deal is about.
    products = Column(JSON, nullable=True)
    status = Column(Enum(DealStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=DealStatus.PENDING)
    exclusivity_start = Column(Date, nullable=True)
    exclusivity_end = Column(Date, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    # Exclusivity ageing. Stamped by the daily sweep so the warning goes out
    # once rather than every morning, and so a lapsed registration reads as
    # expired instead of sitting at "approved" forever. Cleared when an
    # extension is granted: the partner gets a fresh warning before the new
    # end date.
    expiry_warned_at = Column(DateTime(timezone=True), nullable=True)
    expired_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", back_populates="deal_registrations")
    registered_by_user = relationship("User", foreign_keys=[registered_by])
    approver = relationship("User", foreign_keys=[approved_by])
    opportunity = relationship("Opportunity", foreign_keys=[opportunity_id])
    extension_requests = relationship(
        "DealExtensionRequest", back_populates="deal", cascade="all, delete-orphan"
    )
    commission = relationship(
        "Commission", back_populates="deal", uselist=False, cascade="all, delete-orphan"
    )
