"""Add deleted_at to opp_documents

Revision ID: 007
Revises: 006
Create Date: 2026-04-10

The OppDocument model gained a soft-delete column but no migration was added,
causing UndefinedColumnError on every opportunity load. Adds the column as
nullable with no backfill.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "opp_documents",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("opp_documents", "deleted_at")
