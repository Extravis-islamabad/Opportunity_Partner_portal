"""What one person handed to another when they left.

Deactivating an account used to be one flag. Everything the person held —
opportunities they submitted, deals they registered, companies they
channel-managed, POCs they were staffed on and stages they owned — stayed
pointing at a login nobody can use. The work did not disappear; it became
invisible, which is worse, because a queue nobody owns still looks answered.

Reassignment is now a precondition of deactivation rather than a tidy-up
afterwards, and this is the record of it: who took over what, from whom, and
who decided. Six months later "why is this deal mine" has an answer.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class UserHandover(Base):
    __tablename__ = "user_handovers"

    id = Column(Integer, primary_key=True, autoincrement=True)

    from_user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    to_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    performed_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # {"opportunities": 12, "companies": 3, ...} — counts rather than ids, so
    # the record stays readable when the underlying rows move on again. The
    # audit log has the detail; this is the summary somebody actually reads.
    moved = Column(JSON, nullable=False, default=dict)
    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])
    performed_by_user = relationship("User", foreign_keys=[performed_by])

    __table_args__ = (
        Index("ix_user_handovers_from_created", "from_user_id", "created_at"),
    )
