from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class PartnerTierHistory(Base):
    __tablename__ = "partner_tier_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    previous_tier = Column(String(20), nullable=True)
    new_tier = Column(String(20), nullable=False)
    reason = Column(Text, nullable=True)
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    changed_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    company = relationship("Company", back_populates="tier_history")
    changed_by_user = relationship("User", foreign_keys=[changed_by])
