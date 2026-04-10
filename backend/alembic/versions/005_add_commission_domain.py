"""Add commission & scorecard domain

Revision ID: 005
Revises: 004
Create Date: 2026-04-10

Creates three tables: tier_commission_rates, commissions, commission_statements.
Seeds default tier rates: silver 5%, gold 8%, platinum 12%.
"""
from datetime import date
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # commissionstatus enum is new. partnertier enum already exists — reuse it
    # by passing create_type=False on the Enum column.
    commission_status = sa.Enum(
        "pending", "approved", "paid", "void", name="commissionstatus"
    )
    commission_status.create(op.get_bind(), checkfirst=True)

    partner_tier_existing = sa.Enum(
        "silver", "gold", "platinum", name="partnertier", create_type=False
    )

    op.create_table(
        "tier_commission_rates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("tier", partner_tier_existing, nullable=False),
        sa.Column("percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_tier_commission_rates_tier", "tier_commission_rates", ["tier"]
    )

    op.create_table(
        "commissions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("company_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("tier_at_calculation", partner_tier_existing, nullable=False),
        sa.Column("rate_percentage", sa.Numeric(5, 2), nullable=False),
        sa.Column("deal_value", sa.Numeric(14, 2), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("status", commission_status, nullable=False, server_default="pending"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "calculated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["deal_id"], ["deal_registrations.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deal_id", name="uq_commissions_deal_id"),
    )
    op.create_index("ix_commissions_deal_id", "commissions", ["deal_id"])
    op.create_index("ix_commissions_company_id", "commissions", ["company_id"])
    op.create_index("ix_commissions_user_id", "commissions", ["user_id"])
    op.create_index(
        "ix_commissions_company_status", "commissions", ["company_id", "status"]
    )

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

    # Seed default tier rates
    today = date.today().isoformat()
    op.bulk_insert(
        sa.table(
            "tier_commission_rates",
            sa.column("tier", sa.String()),
            sa.column("percentage", sa.Numeric(5, 2)),
            sa.column("effective_from", sa.Date()),
        ),
        [
            {"tier": "silver", "percentage": 5.00, "effective_from": today},
            {"tier": "gold", "percentage": 8.00, "effective_from": today},
            {"tier": "platinum", "percentage": 12.00, "effective_from": today},
        ],
    )


def downgrade() -> None:
    op.drop_index("ix_commission_statements_company_id", table_name="commission_statements")
    op.drop_table("commission_statements")

    op.drop_index("ix_commissions_company_status", table_name="commissions")
    op.drop_index("ix_commissions_user_id", table_name="commissions")
    op.drop_index("ix_commissions_company_id", table_name="commissions")
    op.drop_index("ix_commissions_deal_id", table_name="commissions")
    op.drop_table("commissions")

    op.drop_index("ix_tier_commission_rates_tier", table_name="tier_commission_rates")
    op.drop_table("tier_commission_rates")

    sa.Enum(name="commissionstatus").drop(op.get_bind(), checkfirst=True)
