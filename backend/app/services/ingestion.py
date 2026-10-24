import hashlib

import structlog
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.errors import ConflictError
from app.db.models import Chunk, Document
from app.services.chunking import chunk_text
from app.services.embeddings import EmbeddingProvider

logger = structlog.get_logger(__name__)


class DuplicateDocumentError(ConflictError):
    code = "DOCUMENT_ALREADY_EXISTS"
    message = "A document with identical content already exists."


async def ingest_document(
    session: AsyncSession,
    embedder: EmbeddingProvider,
    settings: Settings,
    *,
    title: str,
    content: str,
) -> Document:
    """Chunk, embed and persist a document in a single transaction.

    Embeddings are computed *before* opening the write transaction so no database
    connection is held while the model runs. Either the document and all of its chunks are
    stored, or nothing is (a document is never visible half-indexed).
    """
    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing_id = await session.scalar(select(Document.id).where(Document.content_sha256 == content_hash))
    if existing_id is not None:
        raise DuplicateDocumentError(details={"document_id": str(existing_id)})
    # Release the connection while embeddings are computed.
    await session.rollback()

    chunks = chunk_text(content, settings.chunk_size, settings.chunk_overlap)
    # The title is prepended so chunks like "You have 30 days." still carry their topic.
    vectors = await embedder.embed_documents([f"{title}\n\n{chunk}" for chunk in chunks])

    document = Document(
        title=title,
        content=content,
        content_sha256=content_hash,
        status="indexed",
        chunk_count=len(chunks),
        embedding_model=embedder.model,
        chunks=[
            Chunk(chunk_index=index, content=chunk, embedding=vector)
            for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
        ],
    )
    session.add(document)
    try:
        await session.commit()
    except IntegrityError as exc:  # lost a race with an identical concurrent submission
        await session.rollback()
        raise DuplicateDocumentError() from exc

    logger.info("document_indexed", document_id=str(document.id), chunks=len(chunks), chars=len(content))
    return document
