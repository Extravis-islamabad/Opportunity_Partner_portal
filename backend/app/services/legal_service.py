"""Which legal documents a partner still has to accept.

Onboarding recorded that somebody ticked a box, not what they agreed to. This
answers the question that matters instead: is this person's acceptance of the
*current* partner agreement and NDA on file, and if not, what is missing.

Publishing a new version is what makes the answer change. Old acceptances are
kept — they are the record of what was agreed and when — but they stop
satisfying the requirement, because what was agreed is no longer what is in
force.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    BadRequestException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
)
from app.models.legal import (
    LEGAL_DOCUMENT_LABELS,
    LegalAcceptance,
    LegalDocument,
    LegalDocumentKind,
)
from app.models.user import User, UserRole
from app.utils.audit import write_audit_log


def applies_to(user: User) -> bool:
    """Whether these documents are this person's to accept.

    The partner agreement and the NDA are what a partner company signs to be
    in the programme. Extravis staff are covered by their employment, and a
    customer company's users are not in the programme at all — asking either
    for a partner agreement would be nonsense they cannot act on.
    """
    if user.role != UserRole.PARTNER:
        return False
    company = getattr(user, "company", None)
    # No company means an account mid-setup; nothing to sign yet.
    return bool(company and company.is_channel_partner)


async def current_documents(db: AsyncSession) -> list[LegalDocument]:
    """The version of each kind that is in force: the most recently published."""
    out = []
    for kind in LegalDocumentKind:
        row = (await db.execute(
            select(LegalDocument)
            .where(LegalDocument.kind == kind)
            .order_by(LegalDocument.published_at.desc(), LegalDocument.id.desc())
            .limit(1)
        )).scalar_one_or_none()
        if row is not None:
            out.append(row)
    return out


async def pending_for(db: AsyncSession, user: User) -> list[dict]:
    """Current documents this user has not accepted.

    Empty for anybody the documents do not apply to, and empty when nothing has
    been published — a portal with no agreement loaded should not block every
    partner in it.
    """
    if not applies_to(user):
        return []

    documents = await current_documents(db)
    if not documents:
        # A short-circuit, not a rule: the comprehension below would return an
        # empty list anyway. It saves a pointless query on a portal with no
        # agreement loaded — which is also the state in which blocking every
        # partner would be worst.
        return []

    accepted = set((await db.execute(
        select(LegalAcceptance.document_id).where(
            LegalAcceptance.user_id == user.id,
            LegalAcceptance.document_id.in_([d.id for d in documents]),
        )
    )).scalars().all())

    return [
        {
            "id": d.id,
            "kind": d.kind.value,
            "label": LEGAL_DOCUMENT_LABELS[d.kind],
            "version": d.version,
            "title": d.title,
            "body": d.body,
            "published_at": d.published_at,
        }
        for d in documents
        if d.id not in accepted
    ]


async def accept(
    db: AsyncSession,
    user: User,
    document_id: int,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> LegalAcceptance:
    """Record that this person accepted this exact version."""
    document = (await db.execute(
        select(LegalDocument).where(LegalDocument.id == document_id)
    )).scalar_one_or_none()
    if document is None:
        raise NotFoundException(
            code="DOCUMENT_NOT_FOUND", message="That document could not be found"
        )
    if not applies_to(user):
        raise ForbiddenException(
            message="These documents are for partner companies in the programme"
        )

    existing = (await db.execute(
        select(LegalAcceptance).where(
            LegalAcceptance.user_id == user.id,
            LegalAcceptance.document_id == document_id,
        )
    )).scalar_one_or_none()
    if existing is not None:
        # Idempotent rather than an error: a double-submitted form should not
        # look like a failure, and the first acceptance is the one that counts.
        return existing

    row = LegalAcceptance(
        user_id=user.id,
        document_id=document_id,
        ip_address=ip_address,
        user_agent=(user_agent or "")[:500] or None,
    )
    db.add(row)
    await db.flush()

    await write_audit_log(
        db, user.id, "CREATE", "legal_acceptance", row.id,
        {"kind": document.kind.value, "version": document.version},
    )
    return row


async def acceptances_for(db: AsyncSession, user_id: int) -> list[dict]:
    """Everything this person has ever accepted, newest first."""
    from sqlalchemy.orm import joinedload

    rows = (await db.execute(
        select(LegalAcceptance)
        .options(joinedload(LegalAcceptance.document))
        .where(LegalAcceptance.user_id == user_id)
        .order_by(LegalAcceptance.accepted_at.desc())
    )).unique().scalars().all()

    return [
        {
            "id": r.id,
            "kind": r.document.kind.value,
            "label": LEGAL_DOCUMENT_LABELS[r.document.kind],
            "version": r.document.version,
            "accepted_at": r.accepted_at,
            "ip_address": r.ip_address,
        }
        for r in rows
    ]


async def publish(
    db: AsyncSession,
    kind: str,
    version: str,
    title: str,
    body: str,
    actor: User,
) -> LegalDocument:
    """Publish a new version, which asks everybody again.

    The previous version is left exactly as it was: somebody accepted that
    text, and editing it afterwards would make their acceptance a record of
    something that never existed.
    """
    try:
        document_kind = LegalDocumentKind(kind)
    except ValueError:
        raise BadRequestException(
            code="UNKNOWN_DOCUMENT_KIND",
            message=f"{kind} is not a document we publish",
        )

    clash = (await db.execute(
        select(LegalDocument).where(
            LegalDocument.kind == document_kind,
            LegalDocument.version == version.strip(),
        )
    )).scalar_one_or_none()
    if clash is not None:
        raise ConflictException(
            code="VERSION_EXISTS",
            message=(
                f"Version {version} of the "
                f"{LEGAL_DOCUMENT_LABELS[document_kind]} already exists. "
                f"Publish it under a new version rather than replacing it."
            ),
        )

    row = LegalDocument(
        kind=document_kind,
        version=version.strip(),
        title=title.strip(),
        body=body,
        published_by=actor.id,
    )
    db.add(row)
    await db.flush()

    await write_audit_log(
        db, actor.id, "CREATE", "legal_document", row.id,
        {"kind": document_kind.value, "version": row.version},
    )
    return row


async def assert_accepted(db: AsyncSession, user: User) -> None:
    """Refuse an action while the current documents are unaccepted.

    Applied to the things a partner does *as* a partner — registering business
    — rather than to reading their own dashboard. Locking someone out of the
    portal entirely would leave them unable to reach the documents they are
    being asked to accept.
    """
    pending = await pending_for(db, user)
    if not pending:
        return
    names = ", ".join(f"{p['label']} ({p['version']})" for p in pending)
    raise ForbiddenException(
        code="LEGAL_ACCEPTANCE_REQUIRED",
        message=(
            f"Please accept the {names} before registering business. "
            f"You will find it on your dashboard."
        ),
    )
