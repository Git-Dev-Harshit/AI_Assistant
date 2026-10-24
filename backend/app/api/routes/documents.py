import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import delete, func, select

from app.api.deps import ServicesDep, SessionDep, SettingsDep
from app.core.errors import NotFoundError
from app.db.models import Document
from app.schemas.documents import (
    DocumentCreate,
    DocumentCreated,
    DocumentDetail,
    DocumentPage,
    DocumentSummary,
)
from app.services.ingestion import ingest_document

router = APIRouter(prefix="/documents", tags=["documents"])


class DocumentNotFoundError(NotFoundError):
    code = "DOCUMENT_NOT_FOUND"
    message = "Document not found."


def _summary(document: Document) -> DocumentSummary:
    return DocumentSummary(
        document_id=document.id,
        title=document.title,
        status=document.status,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=DocumentCreated,
    summary="Add a knowledge article",
    responses={409: {"description": "Identical content already exists"}, 422: {"description": "Invalid input"}},
)
async def create_document(
    payload: DocumentCreate,
    session: SessionDep,
    services: ServicesDep,
    settings: SettingsDep,
    response: Response,
) -> DocumentCreated:
    document = await ingest_document(
        session, services.embedder, settings, title=payload.title, content=payload.content
    )
    response.headers["Location"] = f"/documents/{document.id}"
    return DocumentCreated(
        document_id=document.id,
        status=document.status,
        chunk_count=document.chunk_count,
        created_at=document.created_at,
    )


@router.get("", response_model=DocumentPage, summary="List knowledge articles (newest first)")
async def list_documents(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> DocumentPage:
    total = await session.scalar(select(func.count()).select_from(Document)) or 0
    rows = await session.scalars(
        select(Document).order_by(Document.created_at.desc(), Document.id.desc()).limit(limit).offset(offset)
    )
    return DocumentPage(items=[_summary(doc) for doc in rows], total=total, limit=limit, offset=offset)


@router.get("/{document_id}", response_model=DocumentDetail, summary="Get one article with its content")
async def get_document(document_id: uuid.UUID, session: SessionDep) -> DocumentDetail:
    document = await session.get(Document, document_id)
    if document is None:
        raise DocumentNotFoundError()
    return DocumentDetail(**_summary(document).model_dump(), content=document.content)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an article and its chunks")
async def delete_document(document_id: uuid.UUID, session: SessionDep) -> Response:
    result = await session.execute(delete(Document).where(Document.id == document_id))
    await session.commit()
    if result.rowcount == 0:
        raise DocumentNotFoundError()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
