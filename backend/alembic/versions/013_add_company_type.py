"""Add company_type to companies

Revision ID: 013
Revises: 012
Create Date: 2026-08-24

Until now every company in the portal was implicitly a partner. This adds an
explicit classification — customer / distributor / partner — which decides
whether the company's users can reach deal registration, commissions,
scorecards and tier progression at all.

Backfill: the column is created with a server_default of 'partner', so every
pre-existing row becomes a PARTNER, which is exactly what the code assumed
before. The default is then DROPPED so new rows must classify themselves
explicitly — the API requires company_type on create, and leaving the default
in place would silently let a caller omit it.

Downgrade drops the column and the enum type. It is lossless in the sense
that nothing else references company_type, but the classification itself is
discarded and every company reverts to being implicitly a partner.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "013"
down_revision: Union[str, None] = "012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# create_type=False: created explicitly in upgrade() so downgrade() can drop
# it — same pattern as migrations 010 and 012.
COMPANY_TYPE_VALUES = ("customer", "distributor", "partner")

company_type_enum = postgresql.ENUM(
    *COMPANY_TYPE_VALUES, name="companytype", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*COMPANY_TYPE_VALUES, name="companytype").create(bind, checkfirst=True)

    # server_default backfills every existing row to 'partner' in the same
    # statement that adds the NOT NULL column.
    op.add_column(
        "companies",
        sa.Column(
            "company_type",
            company_type_enum,
            nullable=False,
            server_default="partner",
        ),
    )

    # Drop the default now the backfill is done: classification is a required
    # decision on create, not something to fall through to silently.
    op.alter_column("companies", "company_type", server_default=None)

    op.create_index("ix_companies_company_type", "companies", ["company_type"])


def downgrade() -> None:
    op.drop_index("ix_companies_company_type", table_name="companies")
    op.drop_column("companies", "company_type")
    postgresql.ENUM(name="companytype").drop(op.get_bind(), checkfirst=True)
