"""Question answering: embed -> retrieve -> generate -> cite -> record."""

import re
import time
import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import QuestionLog
from app.schemas.ask import AskResponse, Source
from app.services.embeddings import EmbeddingProvider
from app.services.llm import ContextPassage, LLMProvider
from app.services.prompts import NO_ANSWER, build_prompt
from app.services.retrieval import RetrievedChunk, search_chunks

logger = structlog.get_logger(__name__)

_CITATION = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
_SNIPPET_CHARS = 300


@dataclass(frozen=True)
class RetrievalConfig:
    top_k: int
    min_score: float


async def answer_question(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    llm: LLMProvider,
    config: RetrievalConfig,
    *,
    question: str,
    client_id: str,
) -> AskResponse:
    started = time.perf_counter()

    query_vector = await embedder.embed_query(question)
    hits = await search_chunks(session, query_vector, top_k=config.top_k, min_score=config.min_score)

    if not hits:
        # Nothing relevant: answer honestly without spending an LLM call.
        answer, mode, model, cited = NO_ANSWER, "no_context", None, set()
    else:
        passages = [ContextPassage(number=i, title=h.title, content=h.content) for i, h in enumerate(hits, 1)]
        answer = await llm.generate(build_prompt(question, passages))
        mode = "demo" if llm.name == "mock" else "llm"
        model = llm.model
        cited = _cited_numbers(answer)

    declined = NO_ANSWER.lower() in answer.lower()
    sources = [_source(hit, number in cited) for number, hit in enumerate(hits, 1)]
    latency_ms = int((time.perf_counter() - started) * 1000)

    question_id = await _record(
        session,
        client_id=client_id,
        question=question,
        answer=answer,
        sources=sources,
        mode=mode,
        model=model,
        latency_ms=latency_ms,
    )
    logger.info(
        "question_answered",
        mode=mode,
        hits=len(hits),
        top_score=round(hits[0].score, 3) if hits else None,
        cited=sorted(cited),
        latency_ms=latency_ms,
    )
    return AskResponse(
        question_id=question_id,
        answer=answer,
        sources=sources,
        grounded=bool(hits) and not declined,
        mode=mode,
        model=model,
        latency_ms=latency_ms,
    )


def _cited_numbers(answer: str) -> set[int]:
    return {int(n) for group in _CITATION.findall(answer) for n in group.split(",")}


def _source(hit: RetrievedChunk, cited: bool) -> Source:
    snippet = hit.content if len(hit.content) <= _SNIPPET_CHARS else hit.content[:_SNIPPET_CHARS].rstrip() + "..."
    return Source(
        document_id=hit.document_id,
        title=hit.title,
        chunk_id=hit.chunk_id,
        chunk_index=hit.chunk_index,
        snippet=snippet,
        score=round(hit.score, 4),
        cited=cited,
    )


async def _record(session: AsyncSession, *, sources: list[Source], **fields) -> uuid.UUID:
    """Persist question history. A failure here is logged but never fails the answer:
    the user already has a valid response and history is secondary."""
    entry = QuestionLog(
        id=uuid.uuid4(),  # assigned up front so the response has an id even if the write fails
        sources=[s.model_dump(mode="json", include={"document_id", "chunk_id", "title", "score", "cited"}) for s in sources],
        **fields,
    )
    try:
        session.add(entry)
        await session.commit()
    except Exception:
        await session.rollback()
        logger.exception("question_history_write_failed")
    return entry.id
