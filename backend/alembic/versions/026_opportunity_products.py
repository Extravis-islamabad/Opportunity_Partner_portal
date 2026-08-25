"""Multiple products per opportunity, with the sizing behind the quote

Revision ID: 026
Revises: 025
Create Date: 2026-08-24

An opportunity carried one free-text `product`, so a deal for MonetX and
SupportX together was recorded as one or the other, and the sizing that decides
the price — devices, nodes — only appeared after the PO, on the licence.

Each product on a deal is now its own line with its own scale and value. The
old column is backfilled into a single line per opportunity and then dropped:
leaving it would give pipeline-by-product two sources that drift apart, which
is the failure this replaces rather than repeats.

The line's `product` is text against a canonical list rather than an enum, so
the backfill cannot lose a value it does not recognise, and adding a sixth
product later is a list entry rather than an ALTER TYPE.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "026"
down_revision: Union[str, None] = "025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "opportunity_products",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("opportunity_id", sa.Integer(), nullable=False),
        sa.Column("product", sa.String(length=50), nullable=False),
        sa.Column("device_count", sa.Integer(), nullable=True),
        sa.Column("node_count", sa.Integer(), nullable=True),
        sa.Column("value", sa.Numeric(precision=15, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["opportunity_id"], ["opportunities.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_opportunity_products_opportunity_id",
        "opportunity_products",
        ["opportunity_id"],
    )
    op.create_index("ix_opportunity_products_product", "opportunity_products", ["product"])
    op.create_index(
        "uq_opportunity_products_line",
        "opportunity_products",
        ["opportunity_id", "product"],
        unique=True,
    )

    # One line per opportunity that named a product, carrying the whole stated
    # worth: before this migration the deal *was* that one product, so all of
    # its value belonged to it. Sizing stays null — it was never captured
    # pre-PO, and inventing counts here would put figures nobody agreed into
    # the record.
    # Case and spacing are normalised to the catalogue spelling on the way in.
    # The old column was free text written by imports and seeds, so the same
    # product arrived as "MonetX", "monetx" and "  supportx " — carrying those
    # through verbatim would split one product into three rows in every
    # breakdown. A name that is not in the catalogue is kept as-is (trimmed)
    # rather than dropped: losing a deal's product is worse than an odd label,
    # and it can be corrected in the UI.
    op.execute(
        """
        INSERT INTO opportunity_products
            (opportunity_id, product, value, created_at, updated_at)
        SELECT
            id,
            CASE lower(btrim(product))
                WHEN 'monetx'   THEN 'MonetX'
                WHEN 'supportx' THEN 'SupportX'
                WHEN 'greenx'   THEN 'GreenX'
                WHEN 'patchx'   THEN 'PatchX'
                WHEN 'agentx'   THEN 'AgentX'
                ELSE btrim(product)
            END,
            worth,
            now(),
            now()
        FROM opportunities
        WHERE product IS NOT NULL AND btrim(product) <> ''
        """
    )

    op.drop_index("ix_opportunities_product", table_name="opportunities")
    op.drop_column("opportunities", "product")


def downgrade() -> None:
    op.add_column(
        "opportunities", sa.Column("product", sa.String(length=50), nullable=True)
    )
    op.create_index("ix_opportunities_product", "opportunities", ["product"])

    # Back to one product per opportunity: the highest-value line, falling back
    # to the first. A deal that genuinely spans two products cannot survive the
    # trip, which is the point of the forward migration.
    op.execute(
        """
        UPDATE opportunities o
        SET product = sub.product
        FROM (
            SELECT DISTINCT ON (opportunity_id) opportunity_id, product
            FROM opportunity_products
            ORDER BY opportunity_id, value DESC NULLS LAST, id ASC
        ) AS sub
        WHERE sub.opportunity_id = o.id
        """
    )

    op.drop_index("uq_opportunity_products_line", table_name="opportunity_products")
    op.drop_index("ix_opportunity_products_product", table_name="opportunity_products")
    op.drop_index(
        "ix_opportunity_products_opportunity_id", table_name="opportunity_products"
    )
    op.drop_table("opportunity_products")
