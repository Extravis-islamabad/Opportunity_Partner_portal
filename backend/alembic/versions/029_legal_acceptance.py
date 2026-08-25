"""Versioned partner agreement and NDA, and who accepted which version

Revision ID: 029
Revises: 028
Create Date: 2026-08-25

Onboarding recorded that somebody ticked a box. It did not record what they
agreed to, which version, or when — so "has this partner accepted the current
NDA" was not a question the system could answer, and republishing the
agreement changed nothing for anybody already signed up.

Documents are versioned and acceptance is per version. Publishing a new
version leaves the old acceptances standing as a record of what was agreed,
and asks everybody again, because what they agreed to is no longer in force.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "029"
down_revision: Union[str, None] = "028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

KIND_VALUES = ("partner_agreement", "nda")

# create_type=False: created explicitly below so downgrade has something
# symmetrical to drop. Same pattern as 013, 015, 019, 023 and 027.
kind_enum = postgresql.ENUM(
    *KIND_VALUES, name="legaldocumentkind", create_type=False
)


def upgrade() -> None:
    postgresql.ENUM(*KIND_VALUES, name="legaldocumentkind").create(
        op.get_bind(), checkfirst=True
    )

    op.create_table(
        "legal_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("kind", kind_enum, nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["published_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_documents_kind", "legal_documents", ["kind"])
    op.create_index(
        "ix_legal_documents_kind_published", "legal_documents", ["kind", "published_at"]
    )
    op.create_index(
        "uq_legal_documents_kind_version",
        "legal_documents",
        ["kind", "version"],
        unique=True,
    )

    op.create_table(
        "legal_acceptances",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["document_id"], ["legal_documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_legal_acceptances_user_id", "legal_acceptances", ["user_id"])
    op.create_index(
        "ix_legal_acceptances_document_id", "legal_acceptances", ["document_id"]
    )
    op.create_index(
        "uq_legal_acceptances_user_doc",
        "legal_acceptances",
        ["user_id", "document_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_legal_acceptances_user_doc", table_name="legal_acceptances")
    op.drop_index("ix_legal_acceptances_document_id", table_name="legal_acceptances")
    op.drop_index("ix_legal_acceptances_user_id", table_name="legal_acceptances")
    op.drop_table("legal_acceptances")

    op.drop_index("uq_legal_documents_kind_version", table_name="legal_documents")
    op.drop_index("ix_legal_documents_kind_published", table_name="legal_documents")
    op.drop_index("ix_legal_documents_kind", table_name="legal_documents")
    op.drop_table("legal_documents")
    postgresql.ENUM(name="legaldocumentkind").drop(op.get_bind(), checkfirst=True)
