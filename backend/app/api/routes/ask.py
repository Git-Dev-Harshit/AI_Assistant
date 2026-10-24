from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.client import client_identity
from app.api.deps import ServicesDep, SessionDep, SettingsDep
from app.schemas.ask import AskRequest, AskResponse
from app.services.qa import RetrievalConfig, answer_question

router = APIRouter(tags=["ask"])


@router.post(
    "/ask",
    response_model=AskResponse,
    summary="Ask a question and get a grounded answer with sources",
    responses={
        422: {"description": "Invalid question"},
        503: {"description": "Embedding model, database or LLM unavailable"},
        504: {"description": "LLM timed out"},
    },
)
async def ask(
    payload: AskRequest,
    session: SessionDep,
    services: ServicesDep,
    settings: SettingsDep,
    client_id: Annotated[str, Depends(client_identity)],
) -> AskResponse:
    config = RetrievalConfig(
        top_k=payload.top_k or settings.retrieval_top_k,
        min_score=settings.effective_min_score,
    )
    return await answer_question(
        session, services.embedder, services.llm, config, question=payload.question, client_id=client_id
    )
