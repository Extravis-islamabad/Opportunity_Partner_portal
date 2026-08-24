"""A record of every email the system tried to send.

Email is not a nice-to-have here: an activation link is the only way a new user
can ever set a password, so a mail failure does not degrade the portal, it
locks people out of it. Until now a send that could not happen logged a
warning and returned False, and nothing that called it looked at the return
value — so a misconfigured deployment looked completely healthy.

Every attempt lands here, including the ones that never left the process, so
"are our emails reaching people" is a question with an answer.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Enum, Index, Integer, String, Text

from app.core.database import Base


class EmailStatus(str, enum.Enum):
    """What happened to one send attempt.

    SKIPPED is deliberately distinct from FAILED. A skip means the system
    never tried — no SMTP credentials — which is a configuration problem and
    will affect every message. A failure means the server was asked and said
    no, which is usually about one message. Collapsing them would hide the
    difference between "nothing works" and "one address bounced".
    """

    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"


class EmailDelivery(Base):
    __tablename__ = "email_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Comma-joined, as passed to the mailer. Not a relationship: an address is
    # not always a user (support aliases, distribution lists), and the record
    # should survive the account being deleted.
    recipients = Column(Text, nullable=False)
    subject = Column(String(500), nullable=False)
    # The Jinja template name, when the send came through send_template_email.
    template = Column(String(100), nullable=True)

    status = Column(
        Enum(EmailStatus, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    # Why it did not go: the SMTP error, or the missing configuration.
    error = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    __table_args__ = (
        # The question this table exists to answer is "what has been failing
        # lately", which is this index.
        Index("ix_email_deliveries_status_created", "status", "created_at"),
    )
