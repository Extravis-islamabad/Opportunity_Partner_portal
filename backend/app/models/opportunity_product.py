"""What is actually being sold on an opportunity, and at what scale.

An opportunity carried a single free-text `product` column, so a deal for
MonetX and SupportX together was recorded as one or the other, and the sizing
that decides the price — how many devices, how many nodes — was only captured
after the PO landed, on the licence record. Both of those are needed *before*
the PO: sizing is what the quote is built from, and a deal spanning two
products is the normal case, not an edge one.

Each line is one product on one opportunity, with its own scale and its own
value. The value is per line so pipeline can be broken down by product line
without attributing the whole deal to every product it touches, which would
count the same money five times.

`product` is a plain string against a canonical list rather than a database
enum. The catalogue is a business list that grows — adding a sixth product
should be an entry in PRODUCTS, not an ALTER TYPE and a migration — and a free
column also means the backfill from the old text column could not lose a value
it did not recognise.
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base

# The catalogue as it stands. Order is display order.
PRODUCTS: tuple[str, ...] = ("MonetX", "SupportX", "GreenX", "PatchX", "AgentX")

# Lower-cased for tolerant matching on import and backfill, where the same
# product arrives as "monetx", "MonetX" or "MONETX".
PRODUCTS_BY_KEY: dict[str, str] = {p.lower(): p for p in PRODUCTS}


def canonical_product(value: str | None) -> str | None:
    """The catalogue spelling of a product name, or None if it is not one.

    Callers decide what to do with an unrecognised name; this only answers
    whether it is in the catalogue.
    """
    if not value:
        return None
    return PRODUCTS_BY_KEY.get(value.strip().lower())


def primary_product(opp) -> str | None:
    """The product a one-line summary should name: the highest-value line,
    falling back to the first.

    Derived rather than stored so it cannot disagree with the lines it came
    from. Lives here rather than in a service because the POC header, the
    licence row and the export column all need the same answer.
    """
    lines = getattr(opp, "products", None) or []
    if not lines:
        return None
    return max(lines, key=lambda l: (l.value is not None, l.value or 0)).product


def product_names(opp) -> list[str]:
    return [line.product for line in (getattr(opp, "products", None) or [])]


class OpportunityProduct(Base):
    __tablename__ = "opportunity_products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    opportunity_id = Column(
        Integer,
        ForeignKey("opportunities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product = Column(String(50), nullable=False, index=True)

    # Sizing, captured before the PO rather than after it. Nullable because a
    # deal is often qualified before the counts are known, and a zero would
    # read as "none needed" rather than "not yet asked".
    device_count = Column(Integer, nullable=True)
    node_count = Column(Integer, nullable=True)

    # This line's share of the deal. Nullable for the same reason, and
    # deliberately not forced to sum to Opportunity.worth: a deal can include
    # services that belong to no product line. The analytics report the
    # difference as unattributed rather than quietly absorbing it.
    value = Column(Numeric(15, 2), nullable=True)

    notes = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    opportunity = relationship("Opportunity", back_populates="products")

    __table_args__ = (
        # One line per product per opportunity. Two MonetX lines on one deal
        # would double its MonetX pipeline and there is nothing a second line
        # can express that the first cannot.
        Index("uq_opportunity_products_line", "opportunity_id", "product", unique=True),
    )
