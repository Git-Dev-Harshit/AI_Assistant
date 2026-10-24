from sqlalchemy import func, select

from app.db.models import QuestionLog
from app.services.llm import LLMTimeoutError, LLMUnavailableError, MockLLM

REFUND = {
    "title": "Refund Policy",
    "content": (
        "Customers can request a full refund within 30 days of purchase. "
        "Refund requests must include the original order number.\n\n"
        "Approved refunds are returned to the original payment method within 5 business days."
    ),
}
VPN = {
    "title": "VPN Troubleshooting",
    "content": "If the VPN client fails to connect, restart the client and check your network connection. "
    "Error 809 usually means the firewall is blocking the VPN port.",
}


async def seed(client):
    for doc in (REFUND, VPN):
        response = await client.post("/documents", json=doc)
        assert response.status_code == 201


async def test_ask_returns_grounded_answer_with_cited_sources(client, fake_llm):
    await seed(client)
    fake_llm.answer = "You have 30 days to request a refund [1]."

    response = await client.post("/ask", json={"question": "How many days do I have to request a refund?"})

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "You have 30 days to request a refund [1]."
    assert body["grounded"] is True
    assert body["mode"] == "llm"
    top = body["sources"][0]
    assert top["title"] == "Refund Policy"
    assert top["cited"] is True
    assert 0 < top["score"] <= 1
    assert "30 days" in top["snippet"]


async def test_prompt_contains_question_and_retrieved_context(client, fake_llm):
    await seed(client)

    await client.post("/ask", json={"question": "What does VPN error 809 mean?"})

    prompt = fake_llm.prompts[-1]
    assert "What does VPN error 809 mean?" in prompt.user
    assert "[1] (Source: VPN Troubleshooting)" in prompt.user
    assert "ONLY the numbered context passages" in prompt.system


async def test_unrelated_question_returns_no_context_without_calling_llm(client, fake_llm):
    await seed(client)

    response = await client.post("/ask", json={"question": "Which pizza toppings are popular?"})

    body = response.json()
    assert response.status_code == 200
    assert body["mode"] == "no_context"
    assert body["grounded"] is False
    assert body["sources"] == []
    assert fake_llm.prompts == []


async def test_ask_on_empty_knowledge_base(client, fake_llm):
    response = await client.post("/ask", json={"question": "How do refunds work?"})

    assert response.status_code == 200
    assert response.json()["mode"] == "no_context"


async def test_questions_are_recorded_in_history(client, engine):
    await seed(client)

    await client.post("/ask", json={"question": "How do refunds work?"})

    async with engine.connect() as conn:
        assert await conn.scalar(select(func.count()).select_from(QuestionLog)) == 1


async def test_invalid_questions_are_rejected(client):
    for payload in ({"question": ""}, {"question": "  "}, {"question": "x" * 1001}, {}, {"question": "ok?", "top_k": 50}):
        response = await client.post("/ask", json=payload)
        assert response.status_code == 422, payload
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_llm_outage_returns_stable_503_without_internal_details(client, fake_llm):
    await seed(client)
    fake_llm.error = LLMUnavailableError()

    response = await client.post("/ask", json={"question": "How do refunds work?"})

    assert response.status_code == 503
    error = response.json()["error"]
    assert error["code"] == "LLM_UNAVAILABLE"
    assert error["request_id"]
    assert "ollama" not in response.text.lower()
    assert "traceback" not in response.text.lower()


async def test_llm_timeout_returns_504(client, fake_llm):
    await seed(client)
    fake_llm.error = LLMTimeoutError()

    response = await client.post("/ask", json={"question": "How do refunds work?"})

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "LLM_TIMEOUT"


async def test_demo_mode_is_clearly_labelled(client, services):
    services.llm = MockLLM()
    await seed(client)

    response = await client.post("/ask", json={"question": "How do refunds work?"})

    body = response.json()
    assert body["mode"] == "demo"
    assert body["answer"].startswith("[DEMO MODE")
