"""Give each POC stage an owner

Revision ID: 016
Revises: 015
Create Date: 2026-08-24

One column per stage, mirroring the {stage}_completed_at columns already
there. The stage list is a fixed tuple in the model (POC_STAGES), so five
columns is the shape that matches it — and it makes "one owner per stage" true
by construction rather than something a join table has to be constrained into.

Nullable with no backfill: every stage of every existing POC is unowned, which
is exactly what was true before this column existed. Nothing can be inferred
about who was responsible.

SET NULL on delete: losing an account must leave the stage unowned rather than
take the POC with it.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "016"
down_revision: Union[str, None] = "015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Must stay in step with POC_STAGE_KEYS in app/models/poc.py.
POC_STAGE_KEYS = (
    "vm_provisioning",
    "deployment",
    "device_onboarding",
    "dashboarding",
    "fine_tuning",
)


def upgrade() -> None:
    for key in POC_STAGE_KEYS:
        column = f"{key}_owner_id"
        op.add_column("pocs", sa.Column(column, sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_pocs_{column}", "pocs", "users", [column], ["id"], ondelete="SET NULL"
        )
    # Deliberately no index: owners are read as part of a POC that has already
    # been fetched by id, never filtered on. "POCs where I own a stage" would
    # need one, and would need to be an OR across five columns — the moment
    # that view is wanted, this shape should be revisited.


def downgrade() -> None:
    for key in reversed(POC_STAGE_KEYS):
        column = f"{key}_owner_id"
        op.drop_constraint(f"fk_pocs_{column}", "pocs", type_="foreignkey")
        op.drop_column("pocs", column)
