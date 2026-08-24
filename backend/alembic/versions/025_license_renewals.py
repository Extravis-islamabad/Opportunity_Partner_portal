"""Chase licence renewals, and link a renewal back to what it renews

Revision ID: 025
Revises: 024
Create Date: 2026-08-24

A licence carried an expiry date and a status that read "expiring soon" for
its last two months, and that was the whole of renewals: a date on a screen
nobody had a reason to open. Nothing told the partner, and a renewal raised by
hand was an ordinary new-business opportunity with no link to the licence it
replaced, so "did this customer renew" could not be answered.

`renewal_notified_at` lets the daily sweep chase a licence once, and
`renewal_of_license_id` is the link that makes the chain readable: renewal
opportunity → licence → the opportunity that licence came from.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "025"
down_revision: Union[str, None] = "024"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "customer_licenses",
        sa.Column("renewal_notified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "opportunities",
        sa.Column("renewal_of_license_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_opportunities_renewal_of_license_id",
        "opportunities",
        ["renewal_of_license_id"],
    )
    op.create_foreign_key(
        "fk_opportunities_renewal_of_license_id",
        "opportunities",
        "customer_licenses",
        ["renewal_of_license_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_opportunities_renewal_of_license_id", "opportunities", type_="foreignkey"
    )
    op.drop_index("ix_opportunities_renewal_of_license_id", table_name="opportunities")
    op.drop_column("opportunities", "renewal_of_license_id")
    op.drop_column("customer_licenses", "renewal_notified_at")
