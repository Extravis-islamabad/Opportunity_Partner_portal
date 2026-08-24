"""Add the POC team roster

Revision ID: 015
Revises: 014
Create Date: 2026-08-24

A POC is worked by more than the opportunity's named sales rep. This table
records who else is on it and in what capacity, and membership grants those
people access to the POC (see deps.assert_can_work_on_poc) — before this,
anyone but the named rep was refused.

Removal is soft: `removed_at` is stamped and the row stays, so the roster has a
history rather than only a present tense.

Both foreign keys to users are deliberately different: user_id CASCADEs
(a hard-deleted person leaves no dangling membership) while assigned_by and
removed_by SET NULL (losing the assigner must never delete the assignment
itself). Company deletion in this codebase is a soft delete, so these are
backstops for a hard delete run by hand.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


POC_TEAM_ROLE_VALUES = (
    "presales_lead",
    "solution_architect",
    "deployment_engineer",
    "project_manager",
    "qa",
    "support",
)

# create_type=False: the type is created explicitly in upgrade() so that
# downgrade() has something symmetrical to drop. Without it, create_table
# would emit a second CREATE TYPE and fail on the one already there. Same
# pattern as migration 013.
poc_team_role_enum = postgresql.ENUM(
    *POC_TEAM_ROLE_VALUES, name="pocteamrole", create_type=False
)


def upgrade() -> None:
    postgresql.ENUM(*POC_TEAM_ROLE_VALUES, name="pocteamrole").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "poc_team_members",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("poc_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", poc_team_role_enum, nullable=False),
        sa.Column("assigned_by", sa.Integer(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("removed_by", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["poc_id"], ["pocs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["removed_by"], ["users.id"], ondelete="SET NULL"),
    )

    op.create_index("ix_poc_team_members_poc_id", "poc_team_members", ["poc_id"])
    op.create_index("ix_poc_team_members_user_id", "poc_team_members", ["user_id"])
    # The access check on every POC request a team member makes.
    op.create_index(
        "ix_poc_team_members_user_active", "poc_team_members", ["user_id", "poc_id"]
    )
    # One *live* membership per person per POC. Partial, so the rows left
    # behind by a removal don't block putting that person back on later.
    op.create_index(
        "uq_poc_team_members_active",
        "poc_team_members",
        ["poc_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("removed_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_poc_team_members_active", table_name="poc_team_members")
    op.drop_index("ix_poc_team_members_user_active", table_name="poc_team_members")
    op.drop_index("ix_poc_team_members_user_id", table_name="poc_team_members")
    op.drop_index("ix_poc_team_members_poc_id", table_name="poc_team_members")
    op.drop_table("poc_team_members")
    postgresql.ENUM(name="pocteamrole").drop(op.get_bind(), checkfirst=True)
