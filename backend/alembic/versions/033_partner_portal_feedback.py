"""Partner portal feedback round: several channel managers per company,
optional company location, opportunities without a partner, activity
reminders, and one sizing number per product line.

Revision ID: 033
Revises: 032
Create Date: 2026-10-14

- company_channel_managers: a company can now be looked after by more than
  one channel manager. companies.channel_manager_id stays as the *primary*
  manager (it is NOT NULL and read in a dozen places), and every existing
  company gets its current manager backfilled into the new table so scope
  checks that read the table see exactly what they saw before.
- companies.region / companies.city become optional. Partners were being
  asked to invent a region for a single-city country.
- opportunities.company_id becomes nullable. A sales rep can register a deal
  that has no partner attached yet ("on behalf of" is optional now).
- sales_activities gets a `deployment` type, a partner name, and a follow-up
  reminder (when, what, and whether it has been sent).
- Devices and nodes are the same thing. Product lines and licences keep both
  columns so nothing is lost, but a row that only ever had nodes recorded has
  that number moved into device_count, which is the one the UI now reads.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ---- several channel managers per company -------------------------------
    op.create_table(
        "company_channel_managers",
        sa.Column("company_id", sa.Integer(), sa.ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_channel_managers_user_id", "company_channel_managers", ["user_id"])
    op.execute(
        "INSERT INTO company_channel_managers (company_id, user_id) "
        "SELECT id, channel_manager_id FROM companies WHERE channel_manager_id IS NOT NULL"
    )

    # ---- optional company location ------------------------------------------
    op.alter_column("companies", "region", existing_type=sa.String(100), nullable=True)
    op.alter_column("companies", "city", existing_type=sa.String(100), nullable=True)

    # ---- opportunities without a partner company ------------------------------
    op.alter_column("opportunities", "company_id", existing_type=sa.Integer(), nullable=True)

    # ---- activity log: deployment type, partner name, reminders ---------------
    # ADD VALUE cannot be used in the transaction that adds it, so give it a
    # block of its own.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE activitytype ADD VALUE IF NOT EXISTS 'deployment' AFTER 'training'")

    op.add_column("sales_activities", sa.Column("partner_name", sa.String(255), nullable=True))
    op.add_column("sales_activities", sa.Column("reminder_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sales_activities", sa.Column("reminder_note", sa.Text(), nullable=True))
    op.add_column("sales_activities", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
    # The sweep only ever asks for "due and not yet sent".
    op.create_index(
        "ix_sales_activities_reminder_due",
        "sales_activities",
        ["reminder_at"],
        postgresql_where=sa.text("reminder_sent_at IS NULL AND deleted_at IS NULL"),
    )

    # ---- review clock for manually claimed reviews ----------------------------
    # "Mark under review" never stamped review_claimed_at, so those claims were
    # invisible to the SLA sweep. Same backfill migration 022 used.
    op.execute(
        "UPDATE opportunities SET review_claimed_at = COALESCE(reviewed_at, updated_at) "
        "WHERE status = 'under_review' AND review_claimed_at IS NULL"
    )

    # ---- devices and nodes are one number --------------------------------------
    for table in ("opportunity_products", "customer_licenses"):
        op.execute(
            f"UPDATE {table} SET device_count = node_count "
            f"WHERE device_count IS NULL AND node_count IS NOT NULL"
        )


def downgrade() -> None:
    op.drop_index("ix_sales_activities_reminder_due", table_name="sales_activities")
    op.drop_column("sales_activities", "reminder_sent_at")
    op.drop_column("sales_activities", "reminder_note")
    op.drop_column("sales_activities", "reminder_at")
    op.drop_column("sales_activities", "partner_name")
    # Postgres cannot drop an enum value; rows using it are re-filed as other.
    op.execute("UPDATE sales_activities SET activity_type = 'other' WHERE activity_type = 'deployment'")

    # Refuse rather than delete: a partnerless deal is real pipeline.
    orphans = op.get_bind().execute(
        sa.text("SELECT count(*) FROM opportunities WHERE company_id IS NULL")
    ).scalar()
    if orphans:
        raise RuntimeError(
            f"{orphans} opportunities have no partner company; assign one before downgrading"
        )
    op.alter_column("opportunities", "company_id", existing_type=sa.Integer(), nullable=False)

    op.execute("UPDATE companies SET region = '' WHERE region IS NULL")
    op.execute("UPDATE companies SET city = '' WHERE city IS NULL")
    op.alter_column("companies", "region", existing_type=sa.String(100), nullable=False)
    op.alter_column("companies", "city", existing_type=sa.String(100), nullable=False)

    op.drop_index("ix_company_channel_managers_user_id", table_name="company_channel_managers")
    op.drop_table("company_channel_managers")
