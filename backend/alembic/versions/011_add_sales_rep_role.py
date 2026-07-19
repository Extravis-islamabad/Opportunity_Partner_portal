"""Add the sales_rep user role

Revision ID: 011
Revises: 010
Create Date: 2026-07-17

Sales reps get real accounts: they own opportunities via
Opportunity.sales_rep_id and are the people who actually drive POC,
deployment, and licence records day to day. Until now the app only had
'admin' and 'partner', and a rep was just a users row an admin pointed
sales_rep_id at.

Postgres cannot ADD VALUE to an enum inside a transaction block and then use
that value in the same transaction, so the upgrade runs in an autocommit
block. IF NOT EXISTS keeps it idempotent across re-runs.

Downgrade rebuilds userrole without 'sales_rep'. It deliberately raises if
any sales_rep users still exist rather than silently rewriting them to
'partner' — a partner account carries company-scoped data access, so
auto-converting a rep would hand them a partner's view of the portal. The
operator must reassign or delete those accounts first.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'sales_rep'")


def downgrade() -> None:
    conn = op.get_bind()
    remaining = conn.exec_driver_sql(
        "SELECT count(*) FROM users WHERE role = 'sales_rep'"
    ).scalar()
    if remaining:
        raise RuntimeError(
            f"Cannot downgrade: {remaining} user(s) still have role='sales_rep'. "
            "Reassign or delete these accounts before downgrading — they are not "
            "auto-converted to 'partner' because that would grant them a "
            "partner's company-scoped data access."
        )

    op.execute("ALTER TYPE userrole RENAME TO userrole_old")
    op.execute("CREATE TYPE userrole AS ENUM ('admin', 'partner')")
    op.execute(
        "ALTER TABLE users ALTER COLUMN role TYPE userrole "
        "USING role::text::userrole"
    )
    op.execute("DROP TYPE userrole_old")
