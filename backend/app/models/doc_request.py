import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class DocRequestStatus(str, enum.Enum):
    PENDING = "pending"
    FULFILLED = "fulfilled"
    DECLINED = "declined"


class DocRequestUrgency(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DocRequest(Base):
    __tablename__ = "doc_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=False, index=True)
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    description = Column(Text, nullable=False)
    reason = Column(Text, nullable=True)
    urgency = Column(Enum(DocRequestUrgency, values_callable=lambda x: [e.value for e in x]), nullable=False, default=DocRequestUrgency.MEDIUM)
    status = Column(Enum(DocRequestStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=DocRequestStatus.PENDING)

    fulfilled_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    fulfilled_at = Column(DateTime(timezone=True), nullable=True)
    fulfilled_file_url = Column(String(1000), nullable=True)
    fulfilled_file_name = Column(String(500), nullable=True)
    decline_reason = Column(Text, nullable=True)
    add_to_kb = Column(Integer, default=0, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", back_populates="doc_requests")
    requested_by_user = relationship("User", back_populates="doc_requests", foreign_keys=[requested_by])
    fulfilled_by_user = relationship("User", foreign_keys=[fulfilled_by])
