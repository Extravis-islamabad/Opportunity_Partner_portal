"""
AI endpoints powered by Groq.

Routes degrade gracefully when Groq is unavailable: KB ask returns a polite
fallback, summarize/rescore return 503 with a clear message.
"""
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_admin, get_current_user
from app.core.exceptions import NotFoundException
from app.core.rate_limit import limiter
from app.core.redis import redis_client
from app.models.kb_document import KBDocument
from app.models.opportunity import Opportunity
from app.models.user import User
from app.services import ai_service

router = APIRouter(prefix="/ai", tags=["AI"])


# ---------------------------------------------------------------------------
# Config probe (used by frontend to conditionally mount chat widget)
# ---------------------------------------------------------------------------

class AIConfigResponse(BaseModel):
    enabled: bool
    model_default: str
    model_fast: str


@router.get("/config", response_model=AIConfigResponse)
async def ai_config(
    _current_user: User = Depends(get_current_user),
) -> AIConfigResponse:
    return AIConfigResponse(
        enabled=settings.ai_is_configured,
        model_default=settings.GROQ_MODEL_DEFAULT,
        model_fast=settings.GROQ_MODEL_FAST,
    )


# ---------------------------------------------------------------------------
# KB Q&A
# ---------------------------------------------------------------------------

class KbAskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class KbCitation(BaseModel):
    id: int
    title: str
    category: str


class KbAskResponse(BaseModel):
    answer: str
    citations: list[KbCitation]


async def _retrieve_kb_docs(db: AsyncSession, question: str, limit: int = 5) -> list[KBDocument]:
    """
    Simple keyword retrieval — no vector DB to stay within constraints.
    Tokenizes the question on whitespace, builds ILIKE filters against
    title + category + description, and sorts by match count.
    """
    tokens = [t.strip() for t in question.split() if len(t.strip()) >= 3]
    if not tokens:
        return []

    conditions = []
    for t in tokens[:5]:  # cap to first 5 terms
        like = f"%{t}%"
        conditions.append(KBDocument.title.ilike(like))
        conditions.append(KBDocument.category.ilike(like))
        conditions.append(KBDocument.description.ilike(like))

    query = (
        select(KBDocument)
        .where(
            KBDocument.deleted_at.is_(None),
            or_(*conditions),
        )
        .limit(limit)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


@router.post("/kb-ask", response_model=KbAskResponse)
@limiter.limit("10/minute")
async def kb_ask(
    request: Request,
    payload: KbAskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KbAskResponse:
    docs = await _retrieve_kb_docs(db, payload.question)

    if not settings.ai_is_configured:
        # Fallback: return plain matches without any AI summary
        return KbAskResponse(
            answer=(
                "AI assistant is not configured. Here are the documents that match "
                "your question by keyword — please review them directly."
            ),
            citations=[
                KbCitation(id=d.id, title=d.title, category=d.category) for d in docs
            ],
        )

    snippets = [
        {
            "id": d.id,
            "title": d.title,
            "category": d.category,
            "content": (d.description or "")[:1500],
        }
        for d in docs
    ]

    result = await ai_service.answer_kb_question(payload.question, snippets)
    if result is None:
        return KbAskResponse(
            answer="I'm having trouble reaching the AI service right now. Please try again in a moment.",
            citations=[
                KbCitation(id=d.id, title=d.title, category=d.category) for d in docs
            ],
        )

    citation_ids = set(result.get("citations", []))
    citations = [
        KbCitation(id=d.id, title=d.title, category=d.category)
        for d in docs
        if d.id in citation_ids
    ]
    # If the model didn't return citations, fall back to retrieved docs
    if not citations:
        citations = [
            KbCitation(id=d.id, title=d.title, category=d.category) for d in docs[:3]
        ]

    return KbAskResponse(answer=result["answer"], citations=citations)


# ---------------------------------------------------------------------------
# Opportunity summarize + rescore
# ---------------------------------------------------------------------------

class OpportunitySummaryResponse(BaseModel):
    opportunity_id: int
    summary: str
    cached: bool


def _summary_cache_key(opp_id: int, updated_at) -> str:
    raw = f"{opp_id}:{updated_at.isoformat() if updated_at else 'none'}"
    digest = hashlib.sha1(raw.encode()).hexdigest()[:16]
    return f"ai:summary:{opp_id}:{digest}"


@router.post("/opportunities/{opp_id}/summarize", response_model=OpportunitySummaryResponse)
@limiter.limit("20/minute")
async def summarize_opportunity(
    request: Request,
    opp_id: int,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> OpportunitySummaryResponse:
    if not settings.ai_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI features are disabled. Configure GROQ_API_KEY to enable.",
        )

    result = await db.execute(
        select(Opportunity)
        .options(joinedload(Opportunity.company))
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    cache_key = _summary_cache_key(opp_id, opp.updated_at)
    try:
        cached = await redis_client.get(cache_key)
    except Exception:  # pragma: no cover
        cached = None

    if cached:
        return OpportunitySummaryResponse(
            opportunity_id=opp_id,
            summary=cached.decode() if isinstance(cached, bytes) else cached,
            cached=True,
        )

    summary = await ai_service.summarize_opportunity(opp)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is currently unavailable. Please try again shortly.",
        )

    try:
        await redis_client.setex(cache_key, settings.AI_SCORE_CACHE_SECONDS, summary)
    except Exception:  # pragma: no cover
        pass

    return OpportunitySummaryResponse(
        opportunity_id=opp_id, summary=summary, cached=False
    )


class RescoreResponse(BaseModel):
    opportunity_id: int
    score: Optional[int]
    reasoning: Optional[str]


@router.post("/opportunities/{opp_id}/rescore", response_model=RescoreResponse)
@limiter.limit("20/minute")
async def rescore_opportunity(
    request: Request,
    opp_id: int,
    _admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> RescoreResponse:
    if not settings.ai_is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI features are disabled. Configure GROQ_API_KEY to enable.",
        )

    result = await db.execute(
        select(Opportunity)
        .options(joinedload(Opportunity.company))
        .where(Opportunity.id == opp_id, Opportunity.deleted_at.is_(None))
    )
    opp = result.unique().scalar_one_or_none()
    if not opp:
        raise NotFoundException(code="OPPORTUNITY_NOT_FOUND", message="Opportunity not found")

    score_result = await ai_service.score_opportunity(opp)
    if score_result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI scoring failed. Please try again shortly.",
        )

    from datetime import datetime, timezone

    score, reasoning = score_result
    opp.ai_score = score
    opp.ai_reasoning = reasoning
    opp.ai_scored_at = datetime.now(timezone.utc)
    await db.flush()

    return RescoreResponse(
        opportunity_id=opp_id, score=score, reasoning=reasoning
    )
