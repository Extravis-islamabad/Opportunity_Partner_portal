"""Second-factor enrolment and recovery codes

Revision ID: 030
Revises: 029
Create Date: 2026-08-25

A password was the only thing between an attacker and a superadmin account
that can read every partner's pipeline, change commission rates and publish
legal documents.

The TOTP secret is stored rather than hashed, because verifying a code means
recomputing it — that is inherent to TOTP, and it is why the row is treated as
the sensitive thing it is. Recovery codes *are* hashed, like passwords,
because that is what they are: credentials that grant a session.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "030"
down_revision: Union[str, None] = "029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mfa_enrollments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("secret", sa.String(length=64), nullable=False),
        # Null until the person has proved they can produce a code from the
        # secret. A half-finished setup must not lock anybody out.
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_counter", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_mfa_enrollments_user"),
    )
    op.create_index("ix_mfa_enrollments_user_id", "mfa_enrollments", ["user_id"])

    op.create_table(
        "mfa_recovery_codes",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("enrollment_id", sa.Integer(), nullable=False),
        sa.Column("code_hash", sa.String(length=255), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["enrollment_id"], ["mfa_enrollments.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mfa_recovery_codes_enrollment_id", "mfa_recovery_codes", ["enrollment_id"]
    )
    op.create_index(
        "ix_mfa_recovery_codes_enrollment_used",
        "mfa_recovery_codes",
        ["enrollment_id", "used_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mfa_recovery_codes_enrollment_used", table_name="mfa_recovery_codes"
    )
    op.drop_index(
        "ix_mfa_recovery_codes_enrollment_id", table_name="mfa_recovery_codes"
    )
    op.drop_table("mfa_recovery_codes")
    op.drop_index("ix_mfa_enrollments_user_id", table_name="mfa_enrollments")
    op.drop_table("mfa_enrollments")
