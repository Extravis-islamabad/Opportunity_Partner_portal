"""Record what currency a deal is in, and the rate used to report it

Revision ID: 027
Revises: 026
Create Date: 2026-08-25

Every value in this system was a bare number with no currency attached, so a
500,000 PKR deal and a 500,000 USD deal added up to a million of nothing.

Each deal now carries the currency it was done in and the rate that was true
when its value was set. The rate lives on the row rather than being looked up
at read time, so a report run next quarter still shows the same number for the
same closed deal — the alternative restates history every time a rate moves.

`worth_usd` and `estimated_value_usd` are generated columns: Postgres keeps
them in step with the two columns they come from, which is what lets seventeen
aggregation sites sum one column instead of repeating the arithmetic and
eventually disagreeing.

Existing rows are USD at a rate of 1, which is what they have always implicitly
been.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CURRENCY_VALUES = ("USD", "SAR", "AED", "PKR")

# create_type=False: created explicitly below so downgrade has something
# symmetrical to drop. Same pattern as migrations 013, 015, 019 and 023.
currency_enum = postgresql.ENUM(*CURRENCY_VALUES, name="currency", create_type=False)

# The two pegged currencies at their peg, PKR at a round recent figure. Seeded
# so a fresh install can convert on day one rather than valuing every non-USD
# deal at zero.
SEED_RATES = (
    ("USD", "1.0"),
    ("SAR", "0.2666"),
    ("AED", "0.2723"),
    ("PKR", "0.0036"),
)


def _add_currency_columns(table: str, amount_column: str, generated_column: str) -> None:
    op.add_column(
        table,
        sa.Column(
            "currency", currency_enum, nullable=False, server_default="USD"
        ),
    )
    op.add_column(
        table,
        sa.Column(
            "exchange_rate_to_usd",
            sa.Numeric(precision=18, scale=6),
            nullable=False,
            server_default="1.0",
        ),
    )
    op.create_index(f"ix_{table}_currency", table, ["currency"])
    # Added as SQL rather than through add_column: a generated column cannot be
    # expressed by Alembic's column helper.
    op.execute(
        f"ALTER TABLE {table} "
        f"ADD COLUMN {generated_column} NUMERIC(18, 2) "
        f"GENERATED ALWAYS AS ({amount_column} * exchange_rate_to_usd) STORED"
    )


def upgrade() -> None:
    postgresql.ENUM(*CURRENCY_VALUES, name="currency").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "currency_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("currency", currency_enum, nullable=False),
        sa.Column("rate_to_usd", sa.Numeric(precision=18, scale=6), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_currency_rates_currency", "currency_rates", ["currency"])
    op.create_index(
        "ix_currency_rates_currency_from", "currency_rates", ["currency", "effective_from"]
    )
    # One open rate per currency, or "the current rate" is whichever row the
    # query happened to pick.
    op.create_index(
        "uq_currency_rates_current",
        "currency_rates",
        ["currency"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL"),
    )

    for code, rate in SEED_RATES:
        op.execute(
            "INSERT INTO currency_rates "
            "(currency, rate_to_usd, effective_from, created_at) "
            f"VALUES ('{code}', {rate}, CURRENT_DATE, now())"
        )

    _add_currency_columns("opportunities", "worth", "worth_usd")
    _add_currency_columns("deal_registrations", "estimated_value", "estimated_value_usd")


def downgrade() -> None:
    op.drop_column("deal_registrations", "estimated_value_usd")
    op.drop_index("ix_deal_registrations_currency", table_name="deal_registrations")
    op.drop_column("deal_registrations", "exchange_rate_to_usd")
    op.drop_column("deal_registrations", "currency")

    op.drop_column("opportunities", "worth_usd")
    op.drop_index("ix_opportunities_currency", table_name="opportunities")
    op.drop_column("opportunities", "exchange_rate_to_usd")
    op.drop_column("opportunities", "currency")

    op.drop_index("uq_currency_rates_current", table_name="currency_rates")
    op.drop_index("ix_currency_rates_currency_from", table_name="currency_rates")
    op.drop_index("ix_currency_rates_currency", table_name="currency_rates")
    op.drop_table("currency_rates")
    postgresql.ENUM(name="currency").drop(op.get_bind(), checkfirst=True)
