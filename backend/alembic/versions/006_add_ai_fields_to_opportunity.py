"""Add AI scoring + duplicate detection fields to opportunities

Revision ID: 006
Revises: 005
Create Date: 2026-04-10

All new columns are nullable. No backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("ai_score", sa.Integer(), nullable=True))
    op.add_column("opportunities", sa.Column("ai_reasoning", sa.Text(), nullable=True))
    op.add_column(
        "opportunities",
        sa.Column("ai_scored_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("ai_duplicate_of_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_opportunities_ai_duplicate_of_id",
        "opportunities",
        "opportunities",
        ["ai_duplicate_of_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_opportunities_ai_duplicate_of_id", "opportunities", type_="foreignkey"
    )
    op.drop_column("opportunities", "ai_duplicate_of_id")
    op.drop_column("opportunities", "ai_scored_at")
    op.drop_column("opportunities", "ai_reasoning")
    op.drop_column("opportunities", "ai_score")
