"""Link a partner company to a parent distributor

Revision ID: 014
Revises: 013
Create Date: 2026-08-24

Distributors can now have resellers underneath them. A PARTNER company may
point at a DISTRIBUTOR company via parent_distributor_id; the distributor then
sees its resellers' pipeline (opportunities, POCs, licences). Resellers see
neither each other nor their parent — visibility only ever walks downward.

Nullable with no backfill: every existing company reports directly to Extravis,
which is what the portal assumed before.

ondelete SET NULL rather than CASCADE: deleting a distributor must orphan its
resellers back to reporting directly, never delete them. (Company deletion is
a soft delete in this codebase, so this is a backstop for a hard delete run by
hand.)

The two-level, acyclic shape is enforced by type in the service layer
(company_service.assert_valid_parent_distributor): only a PARTNER may have a
parent and only a DISTRIBUTOR may be one, so a parent can never be a child.
That rule needs a lookup of the other row's type, which a CHECK constraint
cannot express, so it is not duplicated here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "014"
down_revision: Union[str, None] = "013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("parent_distributor_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_companies_parent_distributor_id",
        "companies", "companies",
        ["parent_distributor_id"], ["id"],
        ondelete="SET NULL",
    )
    # The reseller lookup (parent_distributor_id = :id) runs on every request
    # a distributor user makes, so it gets an index.
    op.create_index(
        "ix_companies_parent_distributor_id", "companies", ["parent_distributor_id"]
    )
    # A company can never be its own parent. Cheap to assert in SQL, and it
    # closes the one cycle a single row could create on its own.
    op.create_check_constraint(
        "ck_companies_parent_not_self",
        "companies",
        "parent_distributor_id IS NULL OR parent_distributor_id <> id",
    )


def downgrade() -> None:
    op.drop_constraint("ck_companies_parent_not_self", "companies", type_="check")
    op.drop_index("ix_companies_parent_distributor_id", table_name="companies")
    op.drop_constraint("fk_companies_parent_distributor_id", "companies", type_="foreignkey")
    op.drop_column("companies", "parent_distributor_id")
