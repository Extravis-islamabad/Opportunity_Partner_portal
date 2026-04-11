"""Customer ownership tracks which company has 'first-touch' rights on a
particular customer (normalized name + country) for the duration of an
active deal-registration exclusivity window.

When a deal is approved, an active row is inserted here. While the row is
active, no other company can register an opportunity for the same customer
in the same country — the duplicate detection service issues a hard 409
block, even if the customer name differs slightly (fuzzy match).
"""
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, Date
from sqlalchemy.orm import relationship
from app.core.database import Base


class CustomerOwnership(Base):
    __tablename__ = "customer_ownership"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_name_normalized = Column(String(300), nullable=False, index=True)
    country = Column(String(100), nullable=False, index=True)
    city = Column(String(100), nullable=True)

    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    source_deal_id = Column(Integer, ForeignKey("deal_registrations.id"), nullable=True)
    source_opportunity_id = Column(Integer, ForeignKey("opportunities.id"), nullable=True)

    valid_from = Column(Date, nullable=False)
    valid_until = Column(Date, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    company = relationship("Company", foreign_keys=[company_id])
