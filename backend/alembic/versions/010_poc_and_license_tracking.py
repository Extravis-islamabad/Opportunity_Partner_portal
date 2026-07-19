"""Add POC and post-PO customer licence tracking

Revision ID: 010
Revises: 009
Create Date: 2026-07-17

Two new tables, both one-to-one with an opportunity:

  * pocs              — the technical evaluation an opportunity runs through
                        before a PO. Five stage columns (vm_provisioning →
                        fine_tuning), each a nullable date so stages can be
                        completed independently and out of order. The POC
                        starts on VM allocation and is explicitly closed
                        successful/unsuccessful by a human.

  * customer_licenses — what happens after the PO lands: device/node counts,
                        licence activation and expiry, so renewals are
                        visible before they lapse.

Both use a UNIQUE FK on opportunity_id (one POC / one licence per
opportunity) with ON DELETE CASCADE, and carry deleted_at to match the soft
delete convention every other table follows.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# create_type=False: we create these explicitly in upgrade() so that
# downgrade() can drop them (DROP TABLE leaves the type behind). Without the
# flag, create_table() would try to CREATE TYPE a second time and fail with
# DuplicateObjectError.
POC_STATUS_VALUES = ("not_started", "running", "successful", "unsuccessful")
LICENSE_STATUS_VALUES = ("pending_activation", "active", "expiring_soon", "expired")

poc_status_enum = postgresql.ENUM(*POC_STATUS_VALUES, name="pocstatus", create_type=False)
license_status_enum = postgresql.ENUM(*LICENSE_STATUS_VALUES, name="licensestatus", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    postgresql.ENUM(*POC_STATUS_VALUES, name="pocstatus").create(bind, checkfirst=True)
    postgresql.ENUM(*LICENSE_STATUS_VALUES, name="licensestatus").create(bind, checkfirst=True)

    op.create_table(
        "pocs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("status", poc_status_enum, nullable=False, server_default="not_started"),
        # start_date mirrors vm_provisioning_completed_at, denormalised so
        # date-range filters stay indexable.
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("target_end_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        # The five stages — null means not yet done.
        sa.Column("vm_provisioning_completed_at", sa.Date(), nullable=True),
        sa.Column("deployment_completed_at", sa.Date(), nullable=True),
        sa.Column("device_onboarding_completed_at", sa.Date(), nullable=True),
        sa.Column("dashboarding_completed_at", sa.Date(), nullable=True),
        sa.Column("fine_tuning_completed_at", sa.Date(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("outcome_notes", sa.Text(), nullable=True),
        sa.Column("failure_reason", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"],
            name="fk_pocs_opportunity_id", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["closed_by"], ["users.id"],
            name="fk_pocs_closed_by", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("opportunity_id", name="uq_pocs_opportunity_id"),
    )
    op.create_index("ix_pocs_opportunity_id", "pocs", ["opportunity_id"])
    op.create_index("ix_pocs_status", "pocs", ["status"])
    op.create_index("ix_pocs_start_date", "pocs", ["start_date"])
    op.create_index("ix_pocs_end_date", "pocs", ["end_date"])

    op.create_table(
        "customer_licenses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("po_number", sa.String(length=100), nullable=True),
        sa.Column("po_received_date", sa.Date(), nullable=True),
        sa.Column("po_value", sa.Numeric(15, 2), nullable=True),
        # Devices and nodes are licensed separately, so counted separately.
        sa.Column("device_count", sa.Integer(), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=True),
        sa.Column("license_activated_at", sa.Date(), nullable=True),
        sa.Column("license_expires_at", sa.Date(), nullable=True),
        sa.Column("license_key", sa.String(length=255), nullable=True),
        sa.Column("status", license_status_enum, nullable=False, server_default="pending_activation"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"],
            name="fk_customer_licenses_opportunity_id", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("opportunity_id", name="uq_customer_licenses_opportunity_id"),
    )
    op.create_index("ix_customer_licenses_opportunity_id", "customer_licenses", ["opportunity_id"])
    op.create_index("ix_customer_licenses_status", "customer_licenses", ["status"])
    op.create_index("ix_customer_licenses_po_number", "customer_licenses", ["po_number"])
    op.create_index("ix_customer_licenses_po_received_date", "customer_licenses", ["po_received_date"])
    op.create_index("ix_customer_licenses_license_activated_at", "customer_licenses", ["license_activated_at"])
    op.create_index("ix_customer_licenses_license_expires_at", "customer_licenses", ["license_expires_at"])


def downgrade() -> None:
    op.drop_index("ix_customer_licenses_license_expires_at", table_name="customer_licenses")
    op.drop_index("ix_customer_licenses_license_activated_at", table_name="customer_licenses")
    op.drop_index("ix_customer_licenses_po_received_date", table_name="customer_licenses")
    op.drop_index("ix_customer_licenses_po_number", table_name="customer_licenses")
    op.drop_index("ix_customer_licenses_status", table_name="customer_licenses")
    op.drop_index("ix_customer_licenses_opportunity_id", table_name="customer_licenses")
    op.drop_table("customer_licenses")

    op.drop_index("ix_pocs_end_date", table_name="pocs")
    op.drop_index("ix_pocs_start_date", table_name="pocs")
    op.drop_index("ix_pocs_status", table_name="pocs")
    op.drop_index("ix_pocs_opportunity_id", table_name="pocs")
    op.drop_table("pocs")

    bind = op.get_bind()
    postgresql.ENUM(name="licensestatus").drop(bind, checkfirst=True)
    postgresql.ENUM(name="pocstatus").drop(bind, checkfirst=True)
