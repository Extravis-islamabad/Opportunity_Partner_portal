"""Add department to users

Revision ID: 032
Revises: 031
Create Date: 2026-09-15

A partner company can now add its own employees ("team members") from
inside the portal rather than waiting on an admin. Those individuals carry a
department alongside the job_title (designation) the users table already
had, so this adds the one missing column. Nullable: every account predating
this migration — admins, sales reps, and partner accounts created the old
way — simply has no department.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("department", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "department")
