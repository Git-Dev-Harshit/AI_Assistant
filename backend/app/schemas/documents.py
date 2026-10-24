import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_TITLE_CHARS = 200
MAX_CONTENT_CHARS = 100_000

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_TITLE_CHARS)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_CONTENT_CHARS)]


class DocumentCreate(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "title": "Refund Policy",
                "content": "Customers can request a full refund within 30 days of purchase...",
            }
        },
    )

    title: Title
    content: Content


class DocumentCreated(BaseModel):
    document_id: uuid.UUID
    status: str
    chunk_count: int
    created_at: datetime


class DocumentSummary(BaseModel):
    document_id: uuid.UUID
    title: str
    status: str
    chunk_count: int
    created_at: datetime


class DocumentDetail(DocumentSummary):
    content: str


class DocumentPage(BaseModel):
    items: list[DocumentSummary]
    total: int = Field(description="Total number of documents, for pagination controls.")
    limit: int
    offset: int
