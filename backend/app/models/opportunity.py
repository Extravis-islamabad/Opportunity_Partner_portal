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
    # Final outcome. APPROVED means Extravis accepted the registration; these
    # two say what became of the deal, which is a different question and used
    # to be inferable only from the POC and the licence.
    WON = "won"
    LOST = "lost"


class LossReason(str, enum.Enum):
    """Why a deal was lost. A fixed list rather than free text, because the
    point is to be able to count them — "price" written six different ways
    reports as six different reasons. `loss_notes` carries the detail."""

    PRICE = "price"
    COMPETITOR = "competitor"
    NO_BUDGET = "no_budget"
    TIMING = "timing"
    TECHNICAL_FIT = "technical_fit"
    NO_DECISION = "no_decision"


LOSS_REASON_LABELS: dict[LossReason, str] = {
    LossReason.PRICE: "Price",
    LossReason.COMPETITOR: "Lost to competitor",
    LossReason.NO_BUDGET: "No budget",
    LossReason.TIMING: "Timing",
    LossReason.TECHNICAL_FIT: "Technical fit",
    LossReason.NO_DECISION: "No decision made",
}


# Statuses meaning Extravis accepted the registration. WON belongs here: a deal
# that was approved and then won is not less approved than one still open, and
# every count of "approved opportunities" — tier progression, dashboards,
# company performance — must include it or winning a deal would silently
# subtract from the partner's record.
ACCEPTED_STATUSES: tuple[OpportunityStatus, ...] = (
    OpportunityStatus.APPROVED,
    OpportunityStatus.WON,
)

# Terminal outcomes. Nothing further happens to these.
CLOSED_STATUSES: tuple[OpportunityStatus, ...] = (
    OpportunityStatus.WON,
    OpportunityStatus.LOST,
)


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

    # Excel-driven fields (2027 Target Plan)
    industry = Column(String(100), nullable=True, index=True)
    product = Column(String(50), nullable=True, index=True)
    stage_probability = Column(Numeric(3, 2), nullable=True)
    time_frame = Column(String(20), nullable=True, index=True)
    sales_rep_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(Enum(OpportunityStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=OpportunityStatus.DRAFT)
    preferred_partner = Column(Boolean, default=False, nullable=False)
    multi_partner_alert = Column(Boolean, default=False, nullable=False)
    rejection_reason = Column(Text, nullable=True)

    # Review ageing. An admin opening a pending opportunity claims it — the
    # status moves to under_review and the partner can no longer edit. If that
    # admin then goes on leave, nothing used to move it again: the deal sat
    # locked with nobody chasing, and the partner could not even withdraw it.
    #
    # These three timestamps are what make the claim visible and chaseable:
    # when it was taken, and whether the reviewer has already been reminded or
    # the claim escalated — so neither happens twice.
    review_claimed_at = Column(DateTime(timezone=True), nullable=True, index=True)
    review_reminded_at = Column(DateTime(timezone=True), nullable=True)
    review_escalated_at = Column(DateTime(timezone=True), nullable=True)

    # Closure. Set together when an opportunity reaches WON or LOST;
    # loss_reason is required for a loss and meaningless for a win.
    loss_reason = Column(
        Enum(LossReason, values_callable=lambda x: [e.value for e in x]),
        nullable=True,
    )
    loss_notes = Column(Text, nullable=True)
    closed_outcome_at = Column(DateTime(timezone=True), nullable=True)
    closed_outcome_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
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
    sales_rep = relationship("User", foreign_keys=[sales_rep_id])
    company = relationship("Company", back_populates="opportunities")
    documents = relationship("OppDocument", back_populates="opportunity", cascade="all, delete-orphan")
    poc = relationship("Poc", back_populates="opportunity", uselist=False, cascade="all, delete-orphan")
    license = relationship("CustomerLicense", back_populates="opportunity", uselist=False, cascade="all, delete-orphan")
