"""
AI service powered by Groq's OpenAI-compatible Chat Completions API.

Design principles:
- Every feature function degrades gracefully: if the API key is missing,
  rate-limited, errors out, or returns malformed JSON, we log and return
  a sentinel (None / empty). Callers must never block a user-facing
  operation on AI output.
- We scrub obvious PII (emails, phone numbers) from payloads before sending
  to Groq.
- JSON-mode responses are validated with lightweight Pydantic models.
- The client is created once per process.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Iterable, Optional

import httpx
import structlog
from pydantic import BaseModel, Field, ValidationError

from app.core.config import settings

logger = structlog.get_logger()


class AIUnavailableError(Exception):
    """Raised when the upstream Groq API is missing, misconfigured, or failing."""


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=settings.GROQ_BASE_URL,
            timeout=httpx.Timeout(
                connect=5.0,
                read=settings.GROQ_TIMEOUT_SECONDS,
                write=10.0,
                pool=5.0,
            ),
        )
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


async def _chat(
    messages: list[dict[str, str]],
    *,
    model: Optional[str] = None,
    temperature: float = 0.2,
    json_mode: bool = False,
    max_tokens: int = 800,
) -> str:
    if not settings.ai_is_configured:
        raise AIUnavailableError("AI disabled or GROQ_API_KEY missing")

    payload: dict[str, Any] = {
        "model": model or settings.GROQ_MODEL_DEFAULT,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    try:
        response = await _get_client().post(
            "/chat/completions",
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
        )
    except httpx.HTTPError as exc:
        raise AIUnavailableError(f"Network error calling Groq: {exc}") from exc

    if response.status_code >= 400:
        snippet = response.text[:200] if response.text else ""
        raise AIUnavailableError(
            f"Groq returned {response.status_code}: {snippet}"
        )

    try:
        data = response.json()
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        raise AIUnavailableError(f"Malformed Groq response: {exc}") from exc


# ---------------------------------------------------------------------------
# PII scrubbing
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.\-]+@[\w.\-]+\.[a-zA-Z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d[\d\-\s().]{7,}\d)")


def _scrub_pii(text: Optional[str]) -> str:
    if not text:
        return ""
    text = _EMAIL_RE.sub("[EMAIL]", text)
    text = _PHONE_RE.sub("[PHONE]", text)
    return text


# ---------------------------------------------------------------------------
# Opportunity lead scoring
# ---------------------------------------------------------------------------

class _ScoreResponse(BaseModel):
    score: int = Field(ge=0, le=100)
    reasoning: str = Field(max_length=400)


async def score_opportunity(opp: Any) -> Optional[tuple[int, str]]:
    """
    Returns (score 0-100, reasoning <=280 chars) or None on failure.

    `opp` is the Opportunity ORM row; we read plain attributes so this can be
    called with either a detached or attached instance.
    """
    try:
        company_tier = getattr(getattr(opp, "company", None), "tier", None)
        tier_str = company_tier.value if company_tier is not None and hasattr(company_tier, "value") else "unknown"

        payload = {
            "name": opp.name,
            "customer": opp.customer_name,
            "region": opp.region,
            "country": opp.country,
            "worth_usd": float(opp.worth) if opp.worth is not None else 0,
            "closing_date": str(opp.closing_date) if opp.closing_date else None,
            "requirements": _scrub_pii(opp.requirements)[:2000],
            "partner_tier": tier_str,
        }

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a B2B lead scoring engine. Given a sales opportunity, "
                    "rate its likelihood of closing on a 0-100 scale. Consider deal "
                    "size, timeline clarity, customer specificity, requirement detail, "
                    "and partner tier. Return STRICT JSON: "
                    '{"score": <int 0-100>, "reasoning": "<=280 char explanation"}. '
                    "No prose, no markdown."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ]

        raw = await _chat(
            messages,
            model=settings.GROQ_MODEL_FAST,
            temperature=0.2,
            json_mode=True,
            max_tokens=300,
        )
        parsed = _ScoreResponse.model_validate_json(raw)
        return parsed.score, parsed.reasoning[:280]
    except (AIUnavailableError, ValidationError, json.JSONDecodeError) as exc:
        logger.warning("ai.score_failed", error=str(exc), opp_id=getattr(opp, "id", None))
        return None
    except Exception as exc:  # pragma: no cover
        logger.exception("ai.score_unexpected", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

class _DupEntry(BaseModel):
    id: int
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(max_length=200)


class _DupResponse(BaseModel):
    duplicates: list[_DupEntry] = Field(default_factory=list)


async def detect_duplicates(opp: Any, candidates: Iterable[Any]) -> list[dict]:
    """
    Returns [{opportunity_id, confidence, reason}] — only entries with
    confidence >= 0.6. Empty list on any failure.
    """
    candidates_list = list(candidates)
    if not candidates_list:
        return []

    try:
        new_opp = {
            "id": 0,  # placeholder — we never ask the model about the new opp
            "name": opp.name,
            "customer": opp.customer_name,
            "worth": float(opp.worth) if opp.worth is not None else 0,
            "description": _scrub_pii(opp.requirements)[:600],
        }
        candidate_payload = [
            {
                "id": c.id,
                "name": c.name,
                "customer": c.customer_name,
                "worth": float(c.worth) if c.worth is not None else 0,
            }
            for c in candidates_list[:20]  # hard cap for token budget
        ]

        messages = [
            {
                "role": "system",
                "content": (
                    "You detect duplicate B2B sales opportunities. Given a NEW "
                    "opportunity and a list of EXISTING ones, identify any that "
                    "appear to be duplicates (same customer + similar scope). "
                    'Return STRICT JSON: {"duplicates": [{"id": <int>, '
                    '"confidence": <0.0-1.0>, "reason": "<short>"}]}. '
                    "Only include entries with confidence >= 0.6. "
                    "If none match, return an empty array. No prose, no markdown."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"new": new_opp, "existing": candidate_payload}),
            },
        ]

        raw = await _chat(
            messages,
            model=settings.GROQ_MODEL_FAST,
            temperature=0.0,
            json_mode=True,
            max_tokens=400,
        )
        parsed = _DupResponse.model_validate_json(raw)
        return [
            {"opportunity_id": d.id, "confidence": d.confidence, "reason": d.reason}
            for d in parsed.duplicates
            if d.confidence >= 0.6
        ]
    except (AIUnavailableError, ValidationError, json.JSONDecodeError) as exc:
        logger.warning("ai.dedupe_failed", error=str(exc))
        return []
    except Exception as exc:  # pragma: no cover
        logger.exception("ai.dedupe_unexpected", error=str(exc))
        return []


# ---------------------------------------------------------------------------
# KB question answering
# ---------------------------------------------------------------------------

class _KbAnswer(BaseModel):
    answer: str
    citations: list[int] = Field(default_factory=list)


async def answer_kb_question(
    question: str, top_docs: list[dict]
) -> Optional[dict]:
    """
    `top_docs` is [{id, title, category, content}] — content should be the
    relevant excerpt, pre-truncated by the caller.
    Returns {"answer": str, "citations": [doc_id]} or None on failure.
    """
    if not question.strip():
        return None
    if not top_docs:
        return {"answer": "No matching documents were found in the knowledge base.", "citations": []}

    try:
        snippets = []
        for d in top_docs[:5]:
            snippets.append(
                {
                    "id": d["id"],
                    "title": d.get("title", ""),
                    "category": d.get("category", ""),
                    "excerpt": _scrub_pii(d.get("content", ""))[:1500],
                }
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a knowledge base assistant. Answer the user's question "
                    "USING ONLY the provided documents. If the answer isn't in the "
                    "documents, say 'I couldn't find that in the knowledge base.' "
                    "Cite the documents you used by their id. Be concise. "
                    'Return STRICT JSON: {"answer": "<text>", "citations": [<int>]}. '
                    "No markdown, no prose outside the JSON."
                ),
            },
            {
                "role": "user",
                "content": json.dumps({"question": question, "documents": snippets}),
            },
        ]

        raw = await _chat(
            messages,
            model=settings.GROQ_MODEL_DEFAULT,
            temperature=0.1,
            json_mode=True,
            max_tokens=600,
        )
        parsed = _KbAnswer.model_validate_json(raw)
        return {"answer": parsed.answer, "citations": parsed.citations}
    except (AIUnavailableError, ValidationError, json.JSONDecodeError) as exc:
        logger.warning("ai.kb_ask_failed", error=str(exc))
        return None
    except Exception as exc:  # pragma: no cover
        logger.exception("ai.kb_ask_unexpected", error=str(exc))
        return None


# ---------------------------------------------------------------------------
# Opportunity summarization
# ---------------------------------------------------------------------------

async def summarize_opportunity(opp: Any) -> Optional[str]:
    try:
        payload = {
            "name": opp.name,
            "customer": opp.customer_name,
            "country": opp.country,
            "worth_usd": float(opp.worth) if opp.worth is not None else 0,
            "closing_date": str(opp.closing_date) if opp.closing_date else None,
            "description": _scrub_pii(opp.requirements)[:3000],
        }
        messages = [
            {
                "role": "system",
                "content": (
                    "Summarize the following B2B sales opportunity in at most 120 words, "
                    "as 3-5 short bullet points highlighting: customer context, scope, "
                    "key requirements, timing, and any risks. Plain text only, no markdown."
                ),
            },
            {"role": "user", "content": json.dumps(payload)},
        ]
        raw = await _chat(
            messages,
            model=settings.GROQ_MODEL_DEFAULT,
            temperature=0.3,
            json_mode=False,
            max_tokens=300,
        )
        return raw.strip()
    except AIUnavailableError as exc:
        logger.warning("ai.summarize_failed", error=str(exc))
        return None
    except Exception as exc:  # pragma: no cover
        logger.exception("ai.summarize_unexpected", error=str(exc))
        return None
