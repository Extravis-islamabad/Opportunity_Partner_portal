"""Post-PO customer tracking.

Once a PO is received, an opportunity stops being pipeline and becomes a live
customer deployment we have to track: how many devices/nodes were licensed,
when the licence was activated, and when it expires (so renewals don't get
missed).

One licence record per opportunity (unique FK), created when the PO lands.

The `status` column is a CACHE written at save time. Licence status is
time-dependent, so the column goes stale on its own as dates pass: a row
saved as ACTIVE is EXPIRED a year later with no write in between. Never trust
it directly — reads derive status via poc_service.derive_license_status, and
queries group/filter via poc_service.license_status_expr (the same rule in
SQL). Only that keeps a licence from rendering "active" past its expiry.
"""
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, ForeignKey, Text, Date, Numeric
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class LicenseStatus(str, enum.Enum):
    PENDING_ACTIVATION = "pending_activation"
    ACTIVE = "active"
    EXPIRING_SOON = "expiring_soon"
    EXPIRED = "expired"


# A licence within this many days of expiry is surfaced as EXPIRING_SOON so
# renewals get chased before they lapse.
EXPIRING_SOON_DAYS = 60


class CustomerLicense(Base):
    __tablename__ = "customer_licenses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(
        Integer,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # PO details
    po_number = Column(String(100), nullable=True, index=True)
    po_received_date = Column(Date, nullable=True, index=True)
    po_value = Column(Numeric(15, 2), nullable=True)

    # Scale of the deployment. Devices and nodes are tracked separately
    # because they're licensed separately.
    device_count = Column(Integer, nullable=True)
    node_count = Column(Integer, nullable=True)

    # Licence window
    license_activated_at = Column(Date, nullable=True, index=True)
    license_expires_at = Column(Date, nullable=True, index=True)
    license_key = Column(String(255), nullable=True)

    status = Column(
        Enum(LicenseStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LicenseStatus.PENDING_ACTIVATION,
        index=True,
    )

    notes = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    opportunity = relationship("Opportunity", back_populates="license")

    @property
    def days_until_expiry(self) -> int | None:
        if self.license_expires_at is None:
            return None
        return (self.license_expires_at - datetime.now(timezone.utc).date()).days
