"""Record what a leaver handed to whom

Revision ID: 028
Revises: 027
Create Date: 2026-08-25

Deactivating an account was one status flag. Everything the person held —
opportunities, registrations, managed companies, POC seats, stage ownership —
went on pointing at a login nobody can use. The work did not disappear, it
became invisible, and a queue nobody owns still looks answered.

Reassignment is a precondition of deactivation now, and this table is the
record of it: who took over what, from whom, and who decided.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "028"
down_revision: Union[str, None] = "027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_handovers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("from_user_id", sa.Integer(), nullable=False),
        sa.Column("to_user_id", sa.Integer(), nullable=False),
        sa.Column("performed_by", sa.Integer(), nullable=False),
        sa.Column("moved", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["from_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["to_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["performed_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_handovers_from_user_id", "user_handovers", ["from_user_id"])
    op.create_index("ix_user_handovers_to_user_id", "user_handovers", ["to_user_id"])
    op.create_index(
        "ix_user_handovers_from_created", "user_handovers", ["from_user_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_user_handovers_from_created", table_name="user_handovers")
    op.drop_index("ix_user_handovers_to_user_id", table_name="user_handovers")
    op.drop_index("ix_user_handovers_from_user_id", table_name="user_handovers")
    op.drop_table("user_handovers")
