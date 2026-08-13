"""Add the sales rep daily activity log

Revision ID: 012
Revises: 011
Create Date: 2026-07-21

sales_activities — one row per activity (call, meeting, demo, …) a sales rep
performs on a working day. Entry-based rather than per-day counters so each
activity can carry customer/opportunity context and notes; the month grid
and totals the UI shows are aggregations over these rows.

FKs: user_id CASCADE (activities are meaningless without their author),
opportunity_id SET NULL (the log survives an opportunity being deleted).
Carries deleted_at to match the soft-delete convention of every other table.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# create_type=False: created explicitly in upgrade() so downgrade() can drop
# it — same pattern as migration 010's enums.
ACTIVITY_TYPE_VALUES = (
    "call", "meeting", "demo", "email",
    "site_visit", "follow_up", "training", "other",
)

activity_type_enum = postgresql.ENUM(
    *ACTIVITY_TYPE_VALUES, name="activitytype", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*ACTIVITY_TYPE_VALUES, name="activitytype").create(bind, checkfirst=True)

    op.create_table(
        "sales_activities",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("activity_type", activity_type_enum, nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=True),
        sa.Column("duration_minutes", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_sales_activities_user_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"],
            name="fk_sales_activities_opportunity_id", ondelete="SET NULL",
        ),
    )
    op.create_index("ix_sales_activities_user_id", "sales_activities", ["user_id"])
    op.create_index("ix_sales_activities_activity_date", "sales_activities", ["activity_date"])
    op.create_index("ix_sales_activities_activity_type", "sales_activities", ["activity_type"])
    op.create_index("ix_sales_activities_opportunity_id", "sales_activities", ["opportunity_id"])
    # The month-grid query is always (user, date range) — give it a composite.
    op.create_index(
        "ix_sales_activities_user_date", "sales_activities",
        ["user_id", "activity_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_sales_activities_user_date", table_name="sales_activities")
    op.drop_index("ix_sales_activities_opportunity_id", table_name="sales_activities")
    op.drop_index("ix_sales_activities_activity_type", table_name="sales_activities")
    op.drop_index("ix_sales_activities_activity_date", table_name="sales_activities")
    op.drop_index("ix_sales_activities_user_id", table_name="sales_activities")
    op.drop_table("sales_activities")
    postgresql.ENUM(name="activitytype").drop(op.get_bind(), checkfirst=True)
