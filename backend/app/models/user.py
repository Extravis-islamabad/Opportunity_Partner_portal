import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, ForeignKey, Boolean, Text
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    PARTNER = "partner"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING_ACTIVATION = "pending_activation"
    LOCKED = "locked"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(Enum(UserRole, values_callable=lambda x: [e.value for e in x]), nullable=False, default=UserRole.PARTNER)
    status = Column(Enum(UserStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=UserStatus.PENDING_ACTIVATION)
    job_title = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    company_id = Column(Integer, ForeignKey("companies.id"), nullable=True, index=True)
    is_superadmin = Column(Boolean, default=False, nullable=False)
    has_completed_onboarding = Column(Boolean, default=False, nullable=False)

    activation_token = Column(String(255), nullable=True)
    activation_token_expires = Column(DateTime(timezone=True), nullable=True)
    reset_token = Column(String(255), nullable=True)
    reset_token_expires = Column(DateTime(timezone=True), nullable=True)

    failed_login_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    company = relationship("Company", back_populates="partner_accounts", foreign_keys=[company_id])
    managed_companies = relationship("Company", back_populates="channel_manager", foreign_keys="[Company.channel_manager_id]")
    opportunities = relationship("Opportunity", back_populates="submitted_by_user", foreign_keys="[Opportunity.submitted_by]")
    enrollments = relationship("Enrollment", back_populates="user")
    notifications = relationship("Notification", back_populates="user")
    doc_requests = relationship("DocRequest", back_populates="requested_by_user", foreign_keys="[DocRequest.requested_by]")
