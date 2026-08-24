"""Link a sales activity to a POC

Revision ID: 017
Revises: 016
Create Date: 2026-08-24

An activity could already name the opportunity it was about. It can now name
the POC too, so a POC can be opened and answer "who actually did what on this",
rather than only "who was assigned to it".

Not backfilled, and deliberately so. A POC belongs to exactly one opportunity,
so every existing activity carrying that opportunity_id *could* be stamped with
the POC id — but "I called them about the contract" and "I ran the onboarding
session" are different things, and guessing would put commercial calls into a
technical work log. The POC activity feed instead unions both links at read
time and labels which one matched (poc_service.list_poc_activities), so no
history is lost and none of it is misattributed.

SET NULL on delete, matching the existing opportunity_id: deleting a POC must
not delete the record that someone did the work.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "017"
down_revision: Union[str, None] = "016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sales_activities", sa.Column("poc_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_sales_activities_poc_id",
        "sales_activities", "pocs",
        ["poc_id"], ["id"],
        ondelete="SET NULL",
    )
    # The POC activity feed filters on this on every read of a POC.
    op.create_index("ix_sales_activities_poc_id", "sales_activities", ["poc_id"])


def downgrade() -> None:
    op.drop_index("ix_sales_activities_poc_id", table_name="sales_activities")
    op.drop_constraint("fk_sales_activities_poc_id", "sales_activities", type_="foreignkey")
    op.drop_column("sales_activities", "poc_id")
