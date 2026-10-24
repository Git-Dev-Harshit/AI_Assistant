import math
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Chunk, Document


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str
    chunk_index: int
    content: str
    score: float  # cosine similarity in [-1, 1]; higher is more similar


async def search_chunks(
    session: AsyncSession,
    query_embedding: list[float],
    *,
    top_k: int,
    min_score: float,
) -> list[RetrievedChunk]:
    """Top-k nearest chunks by cosine similarity (served by the HNSW index).

    Results below `min_score` are dropped so that an unrelated question gets "no answer"
    instead of an answer built from irrelevant context.
    """
    distance = Chunk.embedding.cosine_distance(query_embedding)
    stmt = (
        select(
            Chunk.id,
            Chunk.document_id,
            Chunk.chunk_index,
            Chunk.content,
            Document.title,
            distance.label("distance"),
        )
        .join(Document, Document.id == Chunk.document_id)
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await session.execute(stmt)).all()

    results = []
    for row in rows:
        score = 1.0 - float(row.distance)
        if math.isnan(score) or score < min_score:  # NaN happens for all-zero vectors
            continue
        results.append(
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                title=row.title,
                chunk_index=row.chunk_index,
                content=row.content,
                score=score,
            )
        )
    return results
