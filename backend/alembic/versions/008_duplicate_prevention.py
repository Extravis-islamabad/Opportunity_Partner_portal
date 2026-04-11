"""Duplicate prevention foundation

Revision ID: 008
Revises: 007
Create Date: 2026-04-11

Adds the schema needed for best-in-class duplicate detection on opportunities:

  1. Enables the pg_trgm extension for fuzzy text matching
  2. Adds opportunities.customer_name_normalized (indexed) — populated from
     existing rows during the migration via the same Python normalization
     helper used at runtime
  3. Adds opportunities.customer_domain (indexed) — optional bot-able match
  4. Adds a GIN trigram index on customer_name_normalized for fast fuzzy
     similarity() lookups
  5. Creates the customer_ownership table — tracks which company "owns" a
     customer for the duration of an active deal-registration exclusivity
     window. Used to enforce hard blocks on duplicate registration.
"""
from typing import Sequence, Union

import re
import sqlalchemy as sa
from alembic import op
from sqlalchemy.sql import table, column

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- Inline normalization (must match app.utils.customer_normalize) -------
_COMPANY_SUFFIXES = {
    "inc", "incorporated", "corp", "corporation", "co",
    "ltd", "limited", "llc", "llp", "lp", "plc",
    "gmbh", "ag", "sa", "sas", "srl", "spa", "bv", "nv", "ab", "as",
    "pty", "pte", "pvt", "private",
    "company", "group", "holdings", "international", "intl",
    "the",
}
_PUNCT_RE = re.compile(r"[^\w\s]")
_WS_RE = re.compile(r"\s+")


def _normalize(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    n = _PUNCT_RE.sub(" ", n)
    tokens = [t for t in _WS_RE.split(n) if t and t not in _COMPANY_SUFFIXES]
    return " ".join(tokens)


def upgrade() -> None:
    # 1. pg_trgm extension (idempotent)
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # 2. New columns
    op.add_column(
        "opportunities",
        sa.Column("customer_name_normalized", sa.String(300), nullable=True, index=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("customer_domain", sa.String(255), nullable=True, index=True),
    )

    # 3. Backfill normalized names from existing rows
    conn = op.get_bind()
    opp_table = table(
        "opportunities",
        column("id", sa.Integer),
        column("customer_name", sa.String),
        column("customer_name_normalized", sa.String),
    )
    existing = conn.execute(
        sa.select(opp_table.c.id, opp_table.c.customer_name)
    ).fetchall()
    for row in existing:
        normalized = _normalize(row[1] or "")
        conn.execute(
            opp_table.update()
            .where(opp_table.c.id == row[0])
            .values(customer_name_normalized=normalized)
        )

    # 4. GIN trigram index for fast fuzzy similarity()
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_opp_customer_normalized_trgm "
        "ON opportunities USING gin (customer_name_normalized gin_trgm_ops)"
    )

    # 5. customer_ownership table
    op.create_table(
        "customer_ownership",
        sa.Column("id", sa.Integer(), autoincrement=True, primary_key=True),
        sa.Column("customer_name_normalized", sa.String(300), nullable=False, index=True),
        sa.Column("country", sa.String(100), nullable=False, index=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("source_deal_id", sa.Integer(), sa.ForeignKey("deal_registrations.id"), nullable=True),
        sa.Column("source_opportunity_id", sa.Integer(), sa.ForeignKey("opportunities.id"), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_customer_ownership_active_lookup",
        "customer_ownership",
        ["customer_name_normalized", "country", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_customer_ownership_active_lookup", table_name="customer_ownership")
    op.drop_table("customer_ownership")
    op.execute("DROP INDEX IF EXISTS ix_opp_customer_normalized_trgm")
    op.drop_column("opportunities", "customer_domain")
    op.drop_column("opportunities", "customer_name_normalized")
    # Leave the pg_trgm extension installed — other things may use it
