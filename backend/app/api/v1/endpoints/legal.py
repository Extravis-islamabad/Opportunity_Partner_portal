"""The partner agreement and the NDA."""
from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_superadmin, get_current_user
from app.models.legal import LEGAL_DOCUMENT_LABELS, LegalDocumentKind
from app.models.user import User
from app.services import legal_service

router = APIRouter(prefix="/legal", tags=["Legal"])


class PublishRequest(BaseModel):
    """A new version of a document. Versions are never edited in place —
    somebody accepted the old text, and changing it would make their
    acceptance a record of something that never existed."""

    kind: str = Field(..., pattern="^(partner_agreement|nda)$")
    version: str = Field(..., min_length=1, max_length=50)
    title: str = Field(..., min_length=1, max_length=255)
    body: str = Field(..., min_length=1)


@router.get("/pending", status_code=200)
async def list_pending(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Documents this user still has to accept.

    Empty for anybody they do not apply to, and empty when nothing has been
    published — so the dashboard prompt appears only when there is something
    to do.
    """
    return await legal_service.pending_for(db, current_user)


@router.post("/{document_id}/accept", status_code=201)
async def accept_document(
    document_id: int,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Record that this person accepted this exact version."""
    row = await legal_service.accept(
        db,
        current_user,
        document_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return {"id": row.id, "document_id": row.document_id, "accepted_at": row.accepted_at}


@router.get("/my-acceptances", status_code=200)
async def my_acceptances(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """What this person has accepted, and when. Theirs to see."""
    return await legal_service.acceptances_for(db, current_user.id)


@router.get("/documents", status_code=200)
async def list_documents(
    _admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """The version of each document currently in force."""
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
        for d in await legal_service.current_documents(db)
    ]


@router.post("/documents", status_code=201)
async def publish_document(
    data: PublishRequest,
    # Superadmin only: publishing asks every partner in the programme to agree
    # again, which is not a channel manager's call to make.
    admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """Publish a new version, which asks everybody again."""
    row = await legal_service.publish(
        db, data.kind, data.version, data.title, data.body, admin
    )
    return {
        "id": row.id,
        "kind": row.kind.value,
        "version": row.version,
        "published_at": row.published_at,
    }


@router.get("/users/{user_id}/acceptances", status_code=200)
async def user_acceptances(
    user_id: int,
    _admin: User = Depends(get_current_superadmin),
    db: AsyncSession = Depends(get_db),
):
    """One person's acceptance history — the evidence, for whoever has to
    produce it."""
    return await legal_service.acceptances_for(db, user_id)
