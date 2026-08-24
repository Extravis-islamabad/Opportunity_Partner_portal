"""Record whether an opportunity was won or lost

Revision ID: 021
Revises: 020
Create Date: 2026-08-24

Status stopped at "approved" — meaning Extravis accepted the registration —
with the actual outcome inferable only from whether a POC succeeded and a
licence appeared. That is not the same question, and it cannot be reported on.

WON and LOST are added to the existing enum rather than kept in a separate
column, because they are genuinely the next states of the same lifecycle and a
parallel column would let a row be approved-and-lost at once.

`loss_reason` is a fixed enum rather than free text: the point of capturing it
is to count it, and "price" typed six ways counts as six reasons. Detail goes
in loss_notes.

Note for anyone reading counts after this lands: every place that counted
`status == 'approved'` now counts `status IN ('approved','won')`
(models.opportunity.ACCEPTED_STATUSES). Without that, winning a deal would
quietly remove it from a partner's approved total and from tier progression.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "021"
down_revision: Union[str, None] = "020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

LOSS_REASON_VALUES = (
    "price", "competitor", "no_budget", "timing", "technical_fit", "no_decision",
)

loss_reason_enum = postgresql.ENUM(
    *LOSS_REASON_VALUES, name="lossreason", create_type=False
)


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction block on older
    # servers; alembic runs migrations in one, so commit first. Postgres 12+
    # allows it transactionally, but committing is safe on every version.
    op.execute("COMMIT")
    for value in ("won", "lost"):
        op.execute(f"ALTER TYPE opportunitystatus ADD VALUE IF NOT EXISTS '{value}'")

    postgresql.ENUM(*LOSS_REASON_VALUES, name="lossreason").create(
        op.get_bind(), checkfirst=True
    )

    op.add_column("opportunities", sa.Column("loss_reason", loss_reason_enum, nullable=True))
    op.add_column("opportunities", sa.Column("loss_notes", sa.Text(), nullable=True))
    op.add_column(
        "opportunities",
        sa.Column("closed_outcome_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("opportunities", sa.Column("closed_outcome_by", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_opportunities_closed_outcome_by",
        "opportunities", "users",
        ["closed_outcome_by"], ["id"],
        ondelete="SET NULL",
    )
    # "Why do we lose" is a group-by on this column over closed opportunities.
    op.create_index("ix_opportunities_loss_reason", "opportunities", ["loss_reason"])


def downgrade() -> None:
    op.drop_index("ix_opportunities_loss_reason", table_name="opportunities")
    op.drop_constraint("fk_opportunities_closed_outcome_by", "opportunities", type_="foreignkey")
    op.drop_column("opportunities", "closed_outcome_by")
    op.drop_column("opportunities", "closed_outcome_at")
    op.drop_column("opportunities", "loss_notes")
    op.drop_column("opportunities", "loss_reason")
    postgresql.ENUM(name="lossreason").drop(op.get_bind(), checkfirst=True)
    # 'won' and 'lost' stay in opportunitystatus. Postgres cannot remove a
    # value from an enum, and rebuilding the type would require rewriting every
    # row that uses it — including any already closed, whose outcome would be
    # destroyed. Leaving two unused labels behind is the lesser harm.
