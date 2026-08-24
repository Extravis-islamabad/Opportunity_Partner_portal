"""Record every email send attempt

Revision ID: 019
Revises: 018
Create Date: 2026-08-24

Email is load-bearing: an activation link is the only way a new user can set a
password. A send that could not happen previously logged a warning and returned
False that no caller checked, so a deployment unable to mail anyone looked
completely healthy.

Every attempt is now recorded — including the ones that never left the process,
which are the ones that matter most, because they mean the configuration is
wrong rather than one address being bad.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EMAIL_STATUS_VALUES = ("sent", "failed", "skipped")

# create_type=False: created explicitly below so downgrade has something
# symmetrical to drop. Same pattern as migrations 013 and 015.
email_status_enum = postgresql.ENUM(
    *EMAIL_STATUS_VALUES, name="emailstatus", create_type=False
)


def upgrade() -> None:
    postgresql.ENUM(*EMAIL_STATUS_VALUES, name="emailstatus").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "email_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipients", sa.Text(), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("template", sa.String(length=100), nullable=True),
        sa.Column("status", email_status_enum, nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_deliveries_status", "email_deliveries", ["status"])
    op.create_index("ix_email_deliveries_created_at", "email_deliveries", ["created_at"])
    # "What has been failing lately" is the question this table exists for.
    op.create_index(
        "ix_email_deliveries_status_created", "email_deliveries", ["status", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_email_deliveries_status_created", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_created_at", table_name="email_deliveries")
    op.drop_index("ix_email_deliveries_status", table_name="email_deliveries")
    op.drop_table("email_deliveries")
    postgresql.ENUM(name="emailstatus").drop(op.get_bind(), checkfirst=True)
