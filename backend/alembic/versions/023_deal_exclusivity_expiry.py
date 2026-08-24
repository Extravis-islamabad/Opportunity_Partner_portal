"""Expire deal exclusivity, and let a partner ask for more time

Revision ID: 023
Revises: 022
Create Date: 2026-08-24

Exclusivity on an approved deal registration blocks every other partner from
the same customer for a fixed window. The window lapsed silently: nobody was
warned it was about to end, there was no way to ask for more time, and the
registration went on reading "approved" long after its protection was gone.

Two ageing columns let the daily sweep warn once and then mark the row
expired, and a request table records extensions asked for, granted and
refused.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EXTENSION_STATUS_VALUES = ("pending", "approved", "refused")

# create_type=False: created explicitly below so downgrade has something
# symmetrical to drop. Same pattern as migrations 013, 015 and 019.
extension_status_enum = postgresql.ENUM(
    *EXTENSION_STATUS_VALUES, name="extensionstatus", create_type=False
)


def upgrade() -> None:
    op.add_column(
        "deal_registrations",
        sa.Column("expiry_warned_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "deal_registrations",
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Registrations whose window has already closed are expired as of now,
    # rather than waiting for a future edit to notice. Without this the first
    # sweep would announce a batch of "your exclusivity has ended" months
    # after the fact, so they are marked but deliberately not warned about:
    # expiry_warned_at is left null only for rows still inside their window.
    op.execute(
        """
        UPDATE deal_registrations
        SET expired_at = now(),
            expiry_warned_at = now()
        WHERE status = 'approved'
          AND deleted_at IS NULL
          AND exclusivity_end IS NOT NULL
          AND exclusivity_end < CURRENT_DATE
        """
    )
    op.execute(
        """
        UPDATE deal_registrations
        SET status = 'expired'
        WHERE expired_at IS NOT NULL
          AND status = 'approved'
        """
    )

    postgresql.ENUM(*EXTENSION_STATUS_VALUES, name="extensionstatus").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "deal_extension_requests",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("deal_id", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.Integer(), nullable=False),
        sa.Column("requested_days", sa.Integer(), nullable=False),
        sa.Column("granted_days", sa.Integer(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("status", extension_status_enum, nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["deal_id"], ["deal_registrations.id"]),
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["decided_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_deal_extension_requests_deal_id", "deal_extension_requests", ["deal_id"]
    )
    op.create_index(
        "ix_deal_extension_requests_requested_by",
        "deal_extension_requests",
        ["requested_by"],
    )
    op.create_index(
        "ix_deal_extension_requests_status", "deal_extension_requests", ["status"]
    )
    op.create_index(
        "ix_deal_extension_requests_status_created",
        "deal_extension_requests",
        ["status", "created_at"],
    )
    # One open request per deal: five queued requests would otherwise be
    # decided one at a time against a window moving underneath the admin.
    op.create_index(
        "uq_deal_extension_requests_open",
        "deal_extension_requests",
        ["deal_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_deal_extension_requests_open", table_name="deal_extension_requests")
    op.drop_index(
        "ix_deal_extension_requests_status_created", table_name="deal_extension_requests"
    )
    op.drop_index("ix_deal_extension_requests_status", table_name="deal_extension_requests")
    op.drop_index(
        "ix_deal_extension_requests_requested_by", table_name="deal_extension_requests"
    )
    op.drop_index("ix_deal_extension_requests_deal_id", table_name="deal_extension_requests")
    op.drop_table("deal_extension_requests")
    postgresql.ENUM(name="extensionstatus").drop(op.get_bind(), checkfirst=True)

    # Registrations this migration expired go back to approved. Rows that were
    # already 'expired' beforehand are untouched — they have no expired_at, so
    # they are not in this set.
    op.execute(
        """
        UPDATE deal_registrations
        SET status = 'approved'
        WHERE status = 'expired'
          AND expired_at IS NOT NULL
        """
    )
    op.drop_column("deal_registrations", "expired_at")
    op.drop_column("deal_registrations", "expiry_warned_at")
