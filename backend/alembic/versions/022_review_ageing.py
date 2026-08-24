"""Age a claimed opportunity review

Revision ID: 022
Revises: 021
Create Date: 2026-08-24

An admin opening a pending opportunity claims it: the status becomes
under_review and the partner loses the ability to edit. Nothing then moved it
on. If the reviewer went on leave the deal stayed locked indefinitely, with no
reminder, no escalation and no way for another admin to take it over.

review_claimed_at is when the claim was taken. The other two record that a
reminder or an escalation has already gone out, so the daily job does not send
the same nag every morning — a reminder that arrives every day is one nobody
reads.

Backfilled from reviewed_at for anything already sitting under_review, so
existing stuck reviews start ageing from a real timestamp instead of appearing
brand new on deploy day.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "022"
down_revision: Union[str, None] = "021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "opportunities",
        sa.Column("review_claimed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("review_reminded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("review_escalated_at", sa.DateTime(timezone=True), nullable=True),
    )
    # The daily sweep asks "which claims are old", which is this index.
    op.create_index(
        "ix_opportunities_review_claimed_at", "opportunities", ["review_claimed_at"]
    )

    # Existing stuck reviews are the ones this feature exists for; starting
    # their clock at deploy time would give every one of them a fresh grace
    # period. reviewed_at is when the claim was taken, so use it — and fall
    # back to updated_at where it is null.
    op.execute(
        "UPDATE opportunities "
        "SET review_claimed_at = COALESCE(reviewed_at, updated_at) "
        "WHERE status = 'under_review' AND review_claimed_at IS NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_review_claimed_at", table_name="opportunities")
    op.drop_column("opportunities", "review_escalated_at")
    op.drop_column("opportunities", "review_reminded_at")
    op.drop_column("opportunities", "review_claimed_at")
