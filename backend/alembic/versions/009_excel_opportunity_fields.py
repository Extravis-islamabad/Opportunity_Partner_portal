"""Add Excel-driven fields to opportunities

Revision ID: 009
Revises: 008
Create Date: 2026-05-19

Adds first-class columns required by the 2027 Target Plan import:

  * industry          — customer industry (FSI, Healthcare, Telco / ISP, …)
  * product           — Extravis product (MonetX, PatchX, SupportX)
  * stage_probability — pipeline probability 0.10–1.00 matching the Excel
                        legend (Raw Lead → Payment Received)
  * time_frame        — quarter string e.g. "Q3 - 2027"
  * sales_rep_id      — Extravis Team rep owning the opp (FK users.id)

These are all nullable so existing rows aren't broken; the importer fills
them in on insert.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("opportunities", sa.Column("industry", sa.String(length=100), nullable=True))
    op.add_column("opportunities", sa.Column("product", sa.String(length=50), nullable=True))
    op.add_column("opportunities", sa.Column("stage_probability", sa.Numeric(3, 2), nullable=True))
    op.add_column("opportunities", sa.Column("time_frame", sa.String(length=20), nullable=True))
    op.add_column("opportunities", sa.Column("sales_rep_id", sa.Integer(), nullable=True))

    op.create_foreign_key(
        "fk_opportunities_sales_rep_id",
        "opportunities", "users",
        ["sales_rep_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_opportunities_industry", "opportunities", ["industry"])
    op.create_index("ix_opportunities_product", "opportunities", ["product"])
    op.create_index("ix_opportunities_time_frame", "opportunities", ["time_frame"])
    op.create_index("ix_opportunities_sales_rep_id", "opportunities", ["sales_rep_id"])


def downgrade() -> None:
    op.drop_index("ix_opportunities_sales_rep_id", table_name="opportunities")
    op.drop_index("ix_opportunities_time_frame", table_name="opportunities")
    op.drop_index("ix_opportunities_product", table_name="opportunities")
    op.drop_index("ix_opportunities_industry", table_name="opportunities")
    op.drop_constraint("fk_opportunities_sales_rep_id", "opportunities", type_="foreignkey")
    op.drop_column("opportunities", "sales_rep_id")
    op.drop_column("opportunities", "time_frame")
    op.drop_column("opportunities", "stage_probability")
    op.drop_column("opportunities", "product")
    op.drop_column("opportunities", "industry")
