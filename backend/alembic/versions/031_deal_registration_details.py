"""Client details and tender / non-tender structure on deal registrations

Revision ID: 031
Revises: 030
Create Date: 2026-09-07

A deal registration recorded four things about a deal worth protecting:
customer, description, value, close date. The registration form now captures
who the client actually is (contact details and the individual involved) and
what kind of pursuit it is — a tender with its number, submission date and
MAL/MAF requirement, or a direct non-tender opportunity — plus which products
the deal is about.

Every column is nullable: registrations made before this migration stay
valid, and required-ness is the form's decision, not the schema's.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = [
    sa.Column("client_email", sa.String(length=255), nullable=True),
    sa.Column("client_website", sa.String(length=255), nullable=True),
    sa.Column("client_contact", sa.String(length=50), nullable=True),
    sa.Column("client_fax", sa.String(length=50), nullable=True),
    sa.Column("client_address", sa.String(length=500), nullable=True),
    sa.Column("individual_name", sa.String(length=255), nullable=True),
    sa.Column("individual_department", sa.String(length=255), nullable=True),
    sa.Column("individual_designation", sa.String(length=255), nullable=True),
    sa.Column("opportunity_type", sa.String(length=20), nullable=True),
    sa.Column("opportunity_name", sa.String(length=200), nullable=True),
    sa.Column("tender_number", sa.String(length=100), nullable=True),
    sa.Column("tender_submission_date", sa.Date(), nullable=True),
    sa.Column("mal_maf_required", sa.Boolean(), nullable=True),
    sa.Column("poc_required", sa.Boolean(), nullable=True),
    sa.Column("products", sa.JSON(), nullable=True),
]


def upgrade() -> None:
    for column in _COLUMNS:
        op.add_column("deal_registrations", column)


def downgrade() -> None:
    for column in reversed(_COLUMNS):
        op.drop_column("deal_registrations", column.name)
