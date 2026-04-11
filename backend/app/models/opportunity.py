import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, ForeignKey, Text, Numeric, Boolean, Date
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class OpportunityStatus(str, enum.Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    REMOVED = "removed"
    MULTI_PARTNER_FLAGGED = "multi_partner_flagged"


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(200), nullable=False, index=True)
    customer_name = Column(String(200), nullable=False, index=True)
    # Stripped, lowercased, suffix-removed form of customer_name used for
    # duplicate detection (exact match + pg_trgm fuzzy match). Populated
    # automatically on insert/update by the opportunity_service.
    customer_name_normalized = Column(String(300), nullable=True, index=True)
    # Optional customer domain (e.g. "atlas-mfg.com"). When two opps share
    # the same domain it's a near-certain duplicate even if names differ.
    customer_domain = Column(String(255), nullable=True, index=True)
    region = Column(String(100), nullable=False)
    country = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    worth = Column(Numeric(15, 2), nullable=False)
    closing_date = Column(Date, nullable=False)
    requirements = Column(Text, nullable=False)
    status = Column(Enum(OpportunityStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=OpportunityStatus.DRAFT)
    preferred_partner = Column(Boolean, default=False, nullable=False)
    multi_partner_alert = Column(Boolean, default=False, nullable=False)
    rejection_reason = Column(Text, nullable=True)
    internal_notes = Column(Text, nullable=True)

    # AI-generated fields (populated asynchronously by ai_service)
    ai_score = Column(Integer, nullable=True)
    ai_reasoning = Column(Text, nullable=True)
    ai_scored_at = Column(DateTime(timezone=True), nullable=True)
    ai_duplicate_of_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)

    submitted_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    reviewed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    submitted_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    submitted_by_user = relationship("User", back_populates="opportunities", foreign_keys=[submitted_by])
    reviewer = relationship("User", foreign_keys=[reviewed_by])
    company = relationship("Company", back_populates="opportunities")
    documents = relationship("OppDocument", back_populates="opportunity", cascade="all, delete-orphan")
