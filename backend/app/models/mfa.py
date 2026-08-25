"""Second-factor enrolment and the recovery codes that go with it.

A password is the only thing standing between an attacker and a superadmin
account that can read every partner's pipeline, change commission rates and
publish legal documents. This adds a second factor for anybody who wants one,
and lets it be required of the accounts where the blast radius is largest.

Two details matter more than the mechanism:

  - the shared secret is stored, because TOTP needs it to verify a code, so it
    is the one secret here that cannot be hashed. It is written once at
    enrolment and never returned again after the setup step.
  - recovery codes *are* hashed, exactly like passwords, and single-use.
    Somebody who loses their phone needs a way back in; somebody who reads the
    database must not get one.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class MfaEnrollment(Base):
    """One user's second factor. At most one row per user."""

    __tablename__ = "mfa_enrollments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, unique=True, index=True
    )

    # Base32, as TOTP requires. Not hashed — verifying a code means recomputing
    # it, which needs the secret itself. Everything else about the design
    # assumes this is the crown jewel of the row.
    secret = Column(String(64), nullable=False)

    # Enrolment is two steps: generate a secret, then prove a code from it.
    # Until the proof lands the row exists but does not count, so a half-set-up
    # authenticator cannot lock somebody out.
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    # The last window accepted, to stop a code being replayed inside its own
    # 30-second life.
    last_used_counter = Column(Integer, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    user = relationship("User", foreign_keys=[user_id])
    recovery_codes = relationship(
        "MfaRecoveryCode",
        back_populates="enrollment",
        cascade="all, delete-orphan",
        # Eager: an enrolment is never loaded without something wanting to know
        # how many codes are left, and a lazy load on an async session raises
        # rather than falling back to a query.
        lazy="selectin",
    )

    @property
    def is_active(self) -> bool:
        return self.confirmed_at is not None


class MfaRecoveryCode(Base):
    """One single-use way back in without the authenticator.

    Hashed like a password, because that is what it is: a credential that
    grants a session. Marked used rather than deleted, so "which of my codes
    have I burned" has an answer.
    """

    __tablename__ = "mfa_recovery_codes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    enrollment_id = Column(
        Integer,
        ForeignKey("mfa_enrollments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code_hash = Column(String(255), nullable=False)
    used_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    enrollment = relationship("MfaEnrollment", back_populates="recovery_codes")

    __table_args__ = (
        Index("ix_mfa_recovery_codes_enrollment_used", "enrollment_id", "used_at"),
    )
