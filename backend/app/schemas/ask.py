import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_QUESTION_CHARS = 1_000

Question = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=MAX_QUESTION_CHARS)]


class AskRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={"example": {"question": "How long do I have to request a refund?"}},
    )

    question: Question
    top_k: int | None = Field(default=None, ge=1, le=10, description="Number of chunks to retrieve.")


class Source(BaseModel):
    document_id: uuid.UUID
    title: str
    chunk_id: uuid.UUID
    chunk_index: int
    snippet: str
    score: float = Field(description="Cosine similarity between the question and this chunk.")
    cited: bool = Field(description="Whether the answer explicitly cites this source.")


class AskResponse(BaseModel):
    question_id: uuid.UUID
    answer: str
    sources: list[Source]
    grounded: bool = Field(description="False when no sufficiently relevant context was found.")
    mode: Literal["llm", "demo", "no_context"] = Field(
        description="llm: real model; demo: mock fallback; no_context: nothing relevant was retrieved."
    )
    model: str | None
    latency_ms: int
