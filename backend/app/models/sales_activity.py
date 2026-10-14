"""A sales rep's daily activity log.

Each row is one activity a rep performed on a given working day — a call, a
meeting, a demo, and so on. Reps log several per day; the UI presents them in
a Monday–Friday month grid, and admins review any rep's month.

Deliberately entry-based (one row per activity) rather than per-day counters:
entries carry a customer/opportunity context and notes, and monthly totals
are a trivial GROUP BY away.

Ownership: an activity belongs to the user who logged it (user_id). Only
sales reps create them; admins read them. There is no company_id here — reps
are not company-scoped the way partners are.
"""
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, DateTime, Enum, ForeignKey, Text, Date, Index, func
)
from sqlalchemy.orm import relationship
from app.core.database import Base


class ActivityType(str, enum.Enum):
    CALL = "call"
    MEETING = "meeting"
    DEMO = "demo"
    EMAIL = "email"
    SITE_VISIT = "site_visit"
    FOLLOW_UP = "follow_up"
    TRAINING = "training"
    DEPLOYMENT = "deployment"
    OTHER = "other"


ACTIVITY_TYPE_LABELS: dict[str, str] = {
    ActivityType.CALL.value: "Call",
    ActivityType.MEETING.value: "Meeting",
    ActivityType.DEMO.value: "Demo",
    ActivityType.EMAIL.value: "Email",
    ActivityType.SITE_VISIT.value: "Site Visit",
    ActivityType.FOLLOW_UP.value: "Follow-up",
    ActivityType.TRAINING.value: "Training",
    ActivityType.DEPLOYMENT.value: "Deployment",
    ActivityType.OTHER.value: "Other",
}


class SalesActivity(Base):
    __tablename__ = "sales_activities"
    # Mirrors migration 012 — the month-grid query is always (user, date
    # range). Declared here too so alembic autogenerate doesn't try to drop it.
    __table_args__ = (
        Index("ix_sales_activities_user_date", "user_id", "activity_date"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    # The rep who performed and logged the activity.
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    activity_date = Column(Date, nullable=False, index=True)
    activity_type = Column(
        Enum(ActivityType, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )

    # Who the activity was with. Free text — not every call maps to a portal
    # opportunity, but link one when it does.
    customer_name = Column(String(255), nullable=True)
    opportunity_id = Column(
        Integer,
        ForeignKey("opportunities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The POC this work was part of, when it was POC work. Independent of
    # opportunity_id above: a POC belongs to one opportunity, but not every
    # activity on that opportunity is POC work — a contract call is not an
    # onboarding session. The POC activity feed unions both links and says
    # which one matched, rather than treating them as the same thing.
    poc_id = Column(
        Integer,
        ForeignKey("pocs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # The partner the work was for, alongside the client above. Free text for
    # the same reason customer_name is.
    partner_name = Column(String(255), nullable=True)

    # No longer asked for — the form shows the partner name in its place — but
    # kept so the minutes already logged still count in the monthly totals.
    duration_minutes = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)

    # A follow-up the rep wants to be nudged about. The reminder sweep
    # (sales_activity_service.send_due_reminders) notifies the rep once
    # reminder_at has passed and stamps reminder_sent_at so it never fires
    # twice. Moving reminder_at clears reminder_sent_at again.
    reminder_at = Column(DateTime(timezone=True), nullable=True)
    reminder_note = Column(Text, nullable=True)
    reminder_sent_at = Column(DateTime(timezone=True), nullable=True)

    # server_default mirrors migration 012 so the ORM and a fresh DB agree.
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), server_default=func.now(), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    opportunity = relationship("Opportunity", foreign_keys=[opportunity_id])
    poc = relationship("Poc", foreign_keys=[poc_id])
