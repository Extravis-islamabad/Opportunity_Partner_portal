"""Fix enrollment progress_json type, add assessment fields, and unique constraint

Revision ID: 003
Revises: 002
Create Date: 2026-04-09

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change progress_json from String to JSON
    op.alter_column(
        "enrollments",
        "progress_json",
        existing_type=sa.String(),
        type_=sa.JSON(),
        existing_nullable=True,
        postgresql_using="progress_json::json",
    )

    # Add attempt_count and score to enrollments
    op.add_column("enrollments", sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("enrollments", sa.Column("score", sa.Integer(), nullable=True))

    # Add assessment_json and passing_score to courses
    op.add_column("courses", sa.Column("assessment_json", sa.JSON(), nullable=True))
    op.add_column("courses", sa.Column("passing_score", sa.Integer(), nullable=False, server_default="70"))

    # Add unique constraint on user_id + course_id
    op.create_unique_constraint("uq_enrollment_user_course", "enrollments", ["user_id", "course_id"])


def downgrade() -> None:
    op.drop_constraint("uq_enrollment_user_course", "enrollments", type_="unique")
    op.drop_column("courses", "passing_score")
    op.drop_column("courses", "assessment_json")
    op.drop_column("enrollments", "score")
    op.drop_column("enrollments", "attempt_count")
    op.alter_column(
        "enrollments",
        "progress_json",
        existing_type=sa.JSON(),
        type_=sa.String(),
        existing_nullable=True,
    )
