"""The partner agreement and the NDA, and who has accepted which version.

Onboarding asked a partner to read a knowledge-base article and tick a box.
Nothing recorded that they had agreed to anything, which version they agreed
to, or when — so "did this partner accept the current NDA" was not a question
the system could answer, and republishing the agreement changed nothing for
anybody already signed up.

Documents are versioned and acceptance is per version. Publishing a new
version does not invalidate the old acceptance — it stands as a record of what
was agreed and when — but it does mean everybody is asked again, because what
they agreed to is no longer what is in force.
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.database import Base


class LegalDocumentKind(str, enum.Enum):
    PARTNER_AGREEMENT = "partner_agreement"
    NDA = "nda"


LEGAL_DOCUMENT_LABELS: dict[LegalDocumentKind, str] = {
    LegalDocumentKind.PARTNER_AGREEMENT: "Partner Agreement",
    LegalDocumentKind.NDA: "Non-Disclosure Agreement",
}


class LegalDocument(Base):
    """One published version of one document.

    Versions are never edited in place. A document somebody has accepted is
    evidence of what they accepted; changing its text afterwards would make
    that record a lie.
    """

    __tablename__ = "legal_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)

    kind = Column(
        Enum(LegalDocumentKind, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True,
    )
    # Free text rather than a number: real agreements are versioned by date or
    # by the legal team's own scheme, and forcing an integer means the label
    # in the portal disagrees with the label on the PDF.
    version = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=False)

    published_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    published_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    publisher = relationship("User", foreign_keys=[published_by])
    acceptances = relationship(
        "LegalAcceptance", back_populates="document", cascade="all, delete-orphan"
    )

    __table_args__ = (
        # One row per version of a kind. Publishing the same version twice is a
        # mistake, and it would make "the current version" ambiguous.
        Index("uq_legal_documents_kind_version", "kind", "version", unique=True),
        # The current document is the most recently published of its kind, and
        # this is the index that makes finding it one lookup.
        Index("ix_legal_documents_kind_published", "kind", "published_at"),
    )


class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(
        Integer, ForeignKey("legal_documents.id"), nullable=False, index=True
    )

    accepted_at = Column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Kept because an acceptance is evidence. Where it came from is part of
    # what makes it worth anything later.
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(500), nullable=True)

    user = relationship("User", foreign_keys=[user_id])
    document = relationship("LegalDocument", back_populates="acceptances")

    __table_args__ = (
        # Accepting the same version twice is a no-op, not a second agreement.
        Index("uq_legal_acceptances_user_doc", "user_id", "document_id", unique=True),
    )
