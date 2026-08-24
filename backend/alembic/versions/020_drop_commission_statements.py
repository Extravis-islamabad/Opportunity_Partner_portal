"""Drop the unused commission_statements table

Revision ID: 020
Revises: 019
Create Date: 2026-08-24

Statements are computed on demand from Commission rows
(commission_service.list_statements and build_statement). This table was never
read by anything — only written by the demo seed, which is worse than being
empty: it looked populated in development and was always empty in production,
so anyone reasoning from a dev database drew the wrong conclusion about where
statement data lived.

Downgrade recreates the table but not its contents, which is honest: there is
nothing to restore, because nothing ever depended on what was in it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "020"
down_revision: Union[str, None] = "019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table("commission_statements")


def downgrade() -> None:
    # Mirrors migration 005 exactly, so a downgrade restores the schema this
    # table actually had rather than an approximation of it.
    op.create_table(
        "commission_statements",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("commission_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("pdf_url", sa.String(500), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_commission_statements_company_id", "commission_statements", ["company_id"]
    )
