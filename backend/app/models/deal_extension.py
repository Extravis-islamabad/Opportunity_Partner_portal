"""A partner asking for more time on a deal registration.

Approving a deal grants exclusivity for a fixed window, and that window is
load-bearing: while it is open, no other partner can register or submit an
opportunity for the same customer. Until now the window simply lapsed — no
warning to the partner who was relying on it, no way to ask for more time,
and no record on the registration that its protection had ended.

An extension is a request rather than a setting because granting one takes
protection away from everybody else for longer, which is an admin's decision.
Each request is kept after it is decided: "we asked twice and were refused"
is the history that matters when a deal is later lost to another partner.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class ExtensionStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REFUSED = "refused"


class DealExtensionRequest(Base):
    __tablename__ = "deal_extension_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    deal_id = Column(
        Integer, ForeignKey("deal_registrations.id"), nullable=False, index=True
    )
    requested_by = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)

    # What the partner asked for, and what was actually granted — an admin can
    # give less than was asked, and the difference is worth keeping.
    requested_days = Column(Integer, nullable=False)
    granted_days = Column(Integer, nullable=True)
    reason = Column(Text, nullable=True)

    status = Column(
        Enum(ExtensionStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=ExtensionStatus.PENDING,
        index=True,
    )
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    deal = relationship("DealRegistration", back_populates="extension_requests")
    requester = relationship("User", foreign_keys=[requested_by])
    decider = relationship("User", foreign_keys=[decided_by])

    __table_args__ = (
        # One open request per deal. Without this a partner can queue five
        # requests and an admin decides them one at a time against a window
        # that moves underneath them. Decided rows are unconstrained, so the
        # history stays complete.
        Index(
            "uq_deal_extension_requests_open",
            "deal_id",
            unique=True,
            postgresql_where=status == ExtensionStatus.PENDING,
        ),
        Index("ix_deal_extension_requests_status_created", "status", "created_at"),
    )
