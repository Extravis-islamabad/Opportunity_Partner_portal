import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class CompanyStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"


class PartnerTier(str, enum.Enum):
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    country = Column(String(100), nullable=False)
    region = Column(String(100), nullable=False)
    city = Column(String(100), nullable=False)
    industry = Column(String(255), nullable=False)
    contact_email = Column(String(255), nullable=False)
    status = Column(Enum(CompanyStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=CompanyStatus.ACTIVE)
    tier = Column(Enum(PartnerTier, values_callable=lambda x: [e.value for e in x]), nullable=False, default=PartnerTier.SILVER)

    channel_manager_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    channel_manager = relationship("User", back_populates="managed_companies", foreign_keys=[channel_manager_id])
    partner_accounts = relationship("User", back_populates="company", foreign_keys="[User.company_id]")
    opportunities = relationship("Opportunity", back_populates="company")
    doc_requests = relationship("DocRequest", back_populates="company")
    tier_history = relationship("PartnerTierHistory", back_populates="company")
    deal_registrations = relationship("DealRegistration", back_populates="company")
