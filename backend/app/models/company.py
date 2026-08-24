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


class CompanyType(str, enum.Enum):
    """What a company *is* to Extravis, which decides what its users can do.

    - CUSTOMER    — an end customer with a portal login. They track their own
                    opportunities, POCs and licences, but take no part in the
                    partner programme: no deal registration, no commissions,
                    no scorecard, and no tier.
    - DISTRIBUTOR — resells through sub-partners. Full partner programme.
    - PARTNER     — a direct channel partner. Full partner programme.

    Every company predating this column is a PARTNER (see migration 013),
    which is what the portal implicitly assumed before.
    """
    CUSTOMER = "customer"
    DISTRIBUTOR = "distributor"
    PARTNER = "partner"


# The company types that participate in the partner programme. Membership here
# is the single source of truth for "may this company's users reach deal
# registration, commissions, scorecards and tier progression?" — the backend
# guard (deps.deny_customer_company), the tier evaluator and the frontend
# capability set all derive from it rather than testing for CUSTOMER directly,
# so adding a fourth type later is one edit here.
CHANNEL_COMPANY_TYPES: frozenset[CompanyType] = frozenset(
    {CompanyType.DISTRIBUTOR, CompanyType.PARTNER}
)


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
    company_type = Column(
        Enum(CompanyType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=CompanyType.PARTNER,
        index=True,
    )
    # Only meaningful for a channel company — a customer has no tier. The
    # column stays NOT NULL so the enum is simple, but reads null it out for
    # non-channel companies (company_service.tier_for) and the tier evaluator
    # refuses to promote them.
    tier = Column(Enum(PartnerTier, values_callable=lambda x: [e.value for e in x]), nullable=False, default=PartnerTier.SILVER)

    channel_manager_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_channel_partner(self) -> bool:
        """True when this company takes part in the partner programme."""
        return self.company_type in CHANNEL_COMPANY_TYPES

    channel_manager = relationship("User", back_populates="managed_companies", foreign_keys=[channel_manager_id])
    partner_accounts = relationship("User", back_populates="company", foreign_keys="[User.company_id]")
    opportunities = relationship("Opportunity", back_populates="company")
    doc_requests = relationship("DocRequest", back_populates="company")
    tier_history = relationship("PartnerTierHistory", back_populates="company")
    deal_registrations = relationship("DealRegistration", back_populates="company")
