import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text, Date, Numeric
from sqlalchemy.orm import relationship
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
    expected_close_date = Column(Date, nullable=False)
    status = Column(Enum(DealStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=DealStatus.PENDING)
    exclusivity_start = Column(Date, nullable=True)
    exclusivity_end = Column(Date, nullable=True)
    rejection_reason = Column(Text, nullable=True)

    approved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", back_populates="deal_registrations")
    registered_by_user = relationship("User", foreign_keys=[registered_by])
    approver = relationship("User", foreign_keys=[approved_by])
    opportunity = relationship("Opportunity", foreign_keys=[opportunity_id])
    commission = relationship(
        "Commission", back_populates="deal", uselist=False, cascade="all, delete-orphan"
    )
