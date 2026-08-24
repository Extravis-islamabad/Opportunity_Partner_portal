"""Track when a company falls below the tier it holds

Revision ID: 024
Revises: 023
Create Date: 2026-08-24

Tier only ever moved upward. A company that dropped below its requirements
kept the tier — and the commission rate that comes with it — indefinitely, so
the requirements meant something on the way up and nothing afterwards.

Demotion is real now, but never immediate: falling short starts a grace
period, and this column is when it started. Null means the company currently
qualifies, which is true of every company at the moment this runs — the first
review after deployment is what sets it for anyone who does not.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "024"
down_revision: Union[str, None] = "023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "companies",
        sa.Column("tier_at_risk_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("companies", "tier_at_risk_since")
