"""Drop the certificate-request columns

Revision ID: 018
Revises: 017
Create Date: 2026-08-24

Certificates are issued automatically the moment a course is completed. The
older request-then-admin-approves queue has been removed, and these two
columns went with it.

They carry nothing worth keeping. `certificate_requested` was set to True by
the auto-issue path purely so the old admin queue would not re-issue a
certificate that already existed, and `certificate_requested_at` was set to the
completion timestamp — the same value certificate_issued_at already holds. So
every row where they are meaningful is a row where certificate_issued_at says
the same thing.

Irreversible in the strict sense: downgrade restores the columns but not the
values, since there is no longer anything to derive a *request* time from that
is not simply the issue time. The downgrade back-fills from
certificate_issued_at, which is what the data actually meant.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "018"
down_revision: Union[str, None] = "017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("enrollments", "certificate_requested_at")
    op.drop_column("enrollments", "certificate_requested")


def downgrade() -> None:
    op.add_column(
        "enrollments",
        sa.Column(
            "certificate_requested",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "enrollments",
        sa.Column("certificate_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Restore the meaning rather than a blank column: an issued certificate
    # was, under the old model, necessarily a requested one.
    op.execute(
        "UPDATE enrollments SET certificate_requested = true, "
        "certificate_requested_at = certificate_issued_at "
        "WHERE certificate_issued_at IS NOT NULL"
    )
    op.alter_column("enrollments", "certificate_requested", server_default=None)
