"""OllamaLLM resilience: timeouts, bounded retries, upstream 429 handling, backpressure.

The HTTP layer is replaced with httpx.MockTransport, so no model server is needed.
"""

import asyncio

import httpx
import pytest

from app.services.llm import (
    LLMBusyError,
    LLMModelNotReadyError,
    LLMRateLimitedError,
    LLMTimeoutError,
    LLMUnavailableError,
    OllamaLLM,
    Prompt,
)

PROMPT = Prompt(system="system", user="question", passages=[])


def ok(content: str = "Refunds are available for 30 days [1].") -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", "content": content}})


def make_llm(handler, **overrides) -> tuple[OllamaLLM, list[httpx.Request]]:
    calls: list[httpx.Request] = []

    async def recording_handler(request: httpx.Request):
        calls.append(request)
        result = handler(request, len(calls))
        return await result if asyncio.iscoroutine(result) else result

    options = {"max_retries": 2, "backoff_base_s": 0, **overrides}
    llm = OllamaLLM("http://ollama.test", "test-model", transport=httpx.MockTransport(recording_handler), **options)
    return llm, calls


async def test_successful_generation_returns_content():
    llm, calls = make_llm(lambda request, n: ok())

    assert await llm.generate(PROMPT) == "Refunds are available for 30 days [1]."
    assert len(calls) == 1


async def test_transient_5xx_is_retried_then_succeeds():
    llm, calls = make_llm(lambda request, n: httpx.Response(503) if n < 3 else ok())

    assert await llm.generate(PROMPT)
    assert len(calls) == 3


async def test_retries_are_bounded():
    llm, calls = make_llm(lambda request, n: httpx.Response(500))

    with pytest.raises(LLMUnavailableError):
        await llm.generate(PROMPT)
    assert len(calls) == 3  # 1 attempt + max_retries=2


async def test_connection_errors_are_retried_and_reported_as_unavailable():
    def refuse(request, n):
        raise httpx.ConnectError("connection refused", request=request)

    llm, calls = make_llm(refuse)

    with pytest.raises(LLMUnavailableError) as excinfo:
        await llm.generate(PROMPT)
    assert excinfo.value.status_code == 503
    assert len(calls) == 3


async def test_read_timeout_is_not_retried():
    def slow(request, n):
        raise httpx.ReadTimeout("timed out", request=request)

    llm, calls = make_llm(slow)

    with pytest.raises(LLMTimeoutError) as excinfo:
        await llm.generate(PROMPT)
    assert excinfo.value.status_code == 504
    assert len(calls) == 1


async def test_upstream_429_with_short_retry_after_is_retried():
    llm, calls = make_llm(lambda request, n: httpx.Response(429, headers={"Retry-After": "0"}) if n == 1 else ok())

    assert await llm.generate(PROMPT)
    assert len(calls) == 2


async def test_upstream_429_with_long_retry_after_is_surfaced_with_retry_after():
    llm, calls = make_llm(lambda request, n: httpx.Response(429, headers={"Retry-After": "120"}))

    with pytest.raises(LLMRateLimitedError) as excinfo:
        await llm.generate(PROMPT)
    assert excinfo.value.status_code == 503
    assert excinfo.value.headers["Retry-After"] == "120"
    assert len(calls) == 1, "should not block the request for minutes"


async def test_missing_model_is_not_retried():
    llm, calls = make_llm(lambda request, n: httpx.Response(404, json={"error": "model not found"}))

    with pytest.raises(LLMModelNotReadyError):
        await llm.generate(PROMPT)
    assert len(calls) == 1


async def test_empty_or_malformed_response_is_an_error():
    llm, _ = make_llm(lambda request, n: httpx.Response(200, json={"unexpected": True}))

    with pytest.raises(LLMUnavailableError) as excinfo:
        await llm.generate(PROMPT)
    assert excinfo.value.code == "LLM_BAD_RESPONSE"


async def test_excess_concurrency_fails_fast_with_busy_error():
    release = asyncio.Event()

    async def blocked(request, n):
        await release.wait()
        return ok()

    llm, _ = make_llm(blocked, max_concurrency=1, queue_timeout_s=0.05)
    first = asyncio.create_task(llm.generate(PROMPT))
    await asyncio.sleep(0.01)

    with pytest.raises(LLMBusyError) as excinfo:
        await llm.generate(PROMPT)
    assert excinfo.value.headers["Retry-After"]

    release.set()
    assert await first
