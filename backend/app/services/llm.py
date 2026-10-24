"""LLM providers for grounded answer generation.

- `OllamaLLM` (default): a local model served by Ollama over HTTP. Uses the GPU when the
  Ollama container has one, otherwise the CPU.
- `MockLLM`: no model at all. Builds an extractive answer from the retrieved passages and
  labels it clearly as demo output. For reviewers who cannot download a model.

Resilience on the LLM call path (the slowest and most expensive dependency):
- explicit connect/read timeouts on every request,
- a concurrency cap with a bounded wait, so excess load gets a fast 503 instead of an
  ever-growing queue (backpressure),
- bounded retries with exponential backoff + jitter, only for failures that are likely
  transient (connection errors, 5xx, 429). Read timeouts are NOT retried: a model that
  is too slow once will usually be too slow again, and retrying multiplies the load.
"""

import asyncio
import math
import random
from dataclasses import dataclass
from typing import Protocol

import httpx
import structlog

from app.core.errors import AppError, ServiceUnavailableError, UpstreamTimeoutError

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ContextPassage:
    number: int
    title: str
    content: str


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str
    passages: list[ContextPassage]


class LLMUnavailableError(ServiceUnavailableError):
    code = "LLM_UNAVAILABLE"
    message = "The answer service is temporarily unavailable. Please try again shortly."


class LLMRateLimitedError(ServiceUnavailableError):
    """The upstream provider throttled us. This is not the client's fault, so we return
    503 (with Retry-After) rather than passing the provider's 429 through."""

    code = "LLM_RATE_LIMITED"
    message = "The answer service is busy. Please retry in a moment."


class LLMBusyError(ServiceUnavailableError):
    code = "LLM_BUSY"
    message = "Too many questions are being answered right now. Please retry in a moment."


class LLMModelNotReadyError(ServiceUnavailableError):
    code = "LLM_MODEL_NOT_READY"
    message = "The language model is not available yet (it may still be downloading)."


class LLMTimeoutError(UpstreamTimeoutError):
    code = "LLM_TIMEOUT"
    message = "The answer took too long to generate. Please try again."


class LLMProvider(Protocol):
    name: str
    model: str

    async def generate(self, prompt: Prompt) -> str: ...

    async def health(self) -> str: ...

    async def aclose(self) -> None: ...


@dataclass
class _Failure:
    error: AppError
    retryable: bool
    delay_s: float | None = None  # provider-requested wait (Retry-After), else backoff


class OllamaLLM:
    name = "ollama"

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_s: float = 120.0,
        connect_timeout_s: float = 3.0,
        max_retries: int = 2,
        max_concurrency: int = 4,
        queue_timeout_s: float = 10.0,
        temperature: float = 0.1,
        max_output_tokens: int = 512,
        backoff_base_s: float = 0.5,
        max_retry_after_s: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model
        self._max_retries = max_retries
        self._queue_timeout_s = queue_timeout_s
        self._temperature = temperature
        self._max_output_tokens = max_output_tokens
        self._backoff_base_s = backoff_base_s
        self._max_retry_after_s = max_retry_after_s
        self._semaphore = asyncio.Semaphore(max_concurrency)
        # One pooled client for the process: connection reuse, bounded connections.
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout_s, connect=connect_timeout_s),
            limits=httpx.Limits(max_connections=max_concurrency * 2, max_keepalive_connections=max_concurrency),
            transport=transport,
        )

    async def generate(self, prompt: Prompt) -> str:
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._queue_timeout_s)
        except TimeoutError as exc:
            logger.warning("llm_queue_full", model=self.model)
            raise LLMBusyError(headers={"Retry-After": "5"}) from exc
        try:
            return await self._chat_with_retries(prompt)
        finally:
            self._semaphore.release()

    async def _chat_with_retries(self, prompt: Prompt) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": prompt.system},
                {"role": "user", "content": prompt.user},
            ],
            "options": {"temperature": self._temperature, "num_predict": self._max_output_tokens},
        }
        attempt = 0
        while True:
            result = await self._attempt(payload, attempt)
            if isinstance(result, str):
                return result
            if not result.retryable or attempt >= self._max_retries:
                raise result.error
            delay = result.delay_s if result.delay_s is not None else self._backoff(attempt)
            attempt += 1
            logger.info("llm_retry", model=self.model, attempt=attempt, delay_s=round(delay, 2))
            await asyncio.sleep(delay)

    async def _attempt(self, payload: dict, attempt: int) -> str | _Failure:
        try:
            response = await self._client.post("/api/chat", json=payload)
        except httpx.ReadTimeout as exc:
            logger.error("llm_timeout", model=self.model, attempt=attempt)
            raise LLMTimeoutError() from exc
        except httpx.TransportError as exc:  # refused/reset connection, DNS, connect timeout
            logger.warning("llm_transport_error", model=self.model, attempt=attempt, error=type(exc).__name__)
            return _Failure(LLMUnavailableError(), retryable=True)

        if response.status_code == 200:
            return self._parse(response)
        return self._classify(response, attempt)

    def _classify(self, response: httpx.Response, attempt: int) -> _Failure:
        status = response.status_code
        # Log the upstream status and a truncated body for diagnosis; never return it.
        logger.warning("llm_http_error", model=self.model, status=status, attempt=attempt, body=response.text[:300])

        if status == 429:
            retry_after = _parse_retry_after(response.headers.get("Retry-After"))
            error = LLMRateLimitedError(headers={"Retry-After": str(math.ceil(retry_after or 5))})
            if retry_after is None:
                return _Failure(error, retryable=True)
            # Wait in-process only for short pauses; otherwise tell the client when to retry.
            return _Failure(error, retryable=retry_after <= self._max_retry_after_s, delay_s=retry_after)
        if status == 404:
            return _Failure(LLMModelNotReadyError(), retryable=False)
        if status >= 500:
            return _Failure(LLMUnavailableError(), retryable=True)
        return _Failure(LLMUnavailableError(code="LLM_BAD_REQUEST"), retryable=False)

    def _parse(self, response: httpx.Response) -> str:
        try:
            content = response.json()["message"]["content"].strip()
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            logger.error("llm_bad_response", model=self.model, body=response.text[:300])
            raise LLMUnavailableError(code="LLM_BAD_RESPONSE") from exc
        if not content:
            raise LLMUnavailableError(code="LLM_EMPTY_RESPONSE")
        return content

    def _backoff(self, attempt: int) -> float:
        # Exponential backoff with "full jitter" to avoid synchronized retry storms.
        return random.uniform(0, self._backoff_base_s * (2**attempt))

    async def health(self) -> str:
        response = await self._client.get("/api/tags", timeout=2.0)
        response.raise_for_status()
        models = {m.get("name") for m in response.json().get("models", [])}
        if self.model in models or f"{self.model}:latest" in models:
            return "ok"
        return "model_missing"

    async def aclose(self) -> None:
        await self._client.aclose()


class MockLLM:
    """Demo fallback: quotes the most relevant passages instead of generating text."""

    name = "mock"
    model = "mock-extractive"

    async def generate(self, prompt: Prompt) -> str:
        lines = ["[DEMO MODE - no language model was called] The most relevant passages say:"]
        for passage in prompt.passages[:2]:
            lines.append(f"- {_first_sentences(passage.content, 2)} [{passage.number}]")
        return "\n".join(lines)

    async def health(self) -> str:
        return "ok"

    async def aclose(self) -> None:
        return None


def _first_sentences(text: str, count: int) -> str:
    sentences = text.replace("\n", " ").split(". ")
    snippet = ". ".join(sentences[:count]).strip()
    return snippet if snippet.endswith((".", "!", "?")) else snippet + "."


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        return None  # HTTP-date form is rare for APIs; fall back to our default
