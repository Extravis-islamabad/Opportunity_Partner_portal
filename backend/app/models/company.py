import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Table, Text, func, or_, select
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


# Every channel manager of a company. companies.channel_manager_id is still
# the *primary* one (NOT NULL, and the name shown where only one fits), and is
# always in this table as well — company_service keeps the two in step. Scope
# checks go through `Company.managed_by`, which reads both, so a company made
# by a path that only sets channel_manager_id (bulk import, seeds) is still in
# its manager's scope.
company_channel_managers = Table(
    "company_channel_managers",
    Base.metadata,
    Column("company_id", Integer, ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True, index=True),
    Column("created_at", DateTime(timezone=True), server_default=func.now(), nullable=False),
)


class Company(Base):
    __tablename__ = "companies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False, index=True)
    country = Column(String(100), nullable=False)
    # Optional: a single-city country has no meaningful region to ask for.
    region = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
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

    # When the company first stopped meeting the requirements for the tier it
    # holds. Null means it currently qualifies. Set rather than demoting on the
    # spot because tier sets the commission rate: a quiet quarter should be a
    # warning with a deadline, not an unannounced pay cut. Cleared the moment
    # the company qualifies again.
    tier_at_risk_since = Column(DateTime(timezone=True), nullable=True)

    # Reseller link: a PARTNER company may sit underneath a DISTRIBUTOR.
    # Null means the company reports directly to Extravis, which is every
    # company predating migration 014.
    #
    # The graph is structurally two levels deep and acyclic, enforced by type
    # rather than by a cycle check: only a PARTNER may have a parent, and only
    # a DISTRIBUTOR may be one, so a parent can never itself be a child.
    # company_service.assert_valid_parent_distributor is the one place that
    # rule lives.
    parent_distributor_id = Column(
        Integer,
        ForeignKey("companies.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    channel_manager_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    @property
    def is_channel_partner(self) -> bool:
        """True when this company takes part in the partner programme."""
        return self.company_type in CHANNEL_COMPANY_TYPES

    @property
    def can_have_resellers(self) -> bool:
        """Only a distributor sits above other companies."""
        return self.company_type == CompanyType.DISTRIBUTOR

    @classmethod
    def managed_by(cls, user_id: int):
        """SQL predicate: this company is channel-managed by `user_id`, either
        as its primary manager or as one of its additional ones."""
        return or_(
            cls.channel_manager_id == user_id,
            cls.id.in_(
                select(company_channel_managers.c.company_id).where(
                    company_channel_managers.c.user_id == user_id
                )
            ),
        )

    channel_manager = relationship("User", back_populates="managed_companies", foreign_keys=[channel_manager_id])
    # All managers, primary included. selectin so every read path can list
    # them without an async lazy load.
    channel_managers = relationship(
        "User",
        secondary=company_channel_managers,
        lazy="selectin",
        order_by="User.full_name",
        viewonly=True,
    )
    parent_distributor = relationship(
        "Company", remote_side="Company.id", foreign_keys=[parent_distributor_id],
        back_populates="resellers",
    )
    resellers = relationship(
        "Company", foreign_keys=[parent_distributor_id], back_populates="parent_distributor",
    )
    partner_accounts = relationship("User", back_populates="company", foreign_keys="[User.company_id]")
    opportunities = relationship("Opportunity", back_populates="company")
    doc_requests = relationship("DocRequest", back_populates="company")
    tier_history = relationship("PartnerTierHistory", back_populates="company")
    deal_registrations = relationship("DealRegistration", back_populates="company")
