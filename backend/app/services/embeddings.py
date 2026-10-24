"""Embedding providers.

- `SentenceTransformerEmbeddings` (default): a real local model (BAAI/bge-small-en-v1.5,
  384 dims) running on the GPU when available, otherwise on the CPU.
- `HashEmbeddings`: a deterministic bag-of-words hashing embedder with no model download.
  Used by the test suite and as a documented fallback; retrieval quality is lexical only.

Model inference is CPU/GPU-bound and synchronous, so it runs in a worker thread
(`anyio.to_thread`) to keep the FastAPI event loop free, and a semaphore bounds how many
inference calls run at once so a traffic spike cannot exhaust memory or VRAM.
"""

import asyncio
import hashlib
import math
import re
from typing import Protocol

import anyio
import structlog

from app.core.device import DeviceInfo
from app.core.errors import ServiceUnavailableError

logger = structlog.get_logger(__name__)


class EmbeddingUnavailableError(ServiceUnavailableError):
    code = "EMBEDDING_UNAVAILABLE"
    message = "The embedding service is temporarily unavailable. Please try again shortly."


class EmbeddingProvider(Protocol):
    name: str
    model: str
    dim: int
    device: str

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    async def embed_query(self, text: str) -> list[float]: ...


class SentenceTransformerEmbeddings:
    name = "sentence-transformers"

    def __init__(
        self,
        model_name: str,
        device: DeviceInfo,
        expected_dim: int,
        query_instruction: str = "",
        max_concurrency: int = 2,
        batch_size: int = 32,
    ) -> None:
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.model = model_name
        self.device = device.device
        self._query_instruction = query_instruction
        self._batch_size = batch_size
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._model = SentenceTransformer(model_name, device=device.device)

        dim = self._model.get_sentence_embedding_dimension()
        if dim != expected_dim:
            raise RuntimeError(
                f"Embedding model {model_name} produces {dim}-d vectors but the database "
                f"is configured for {expected_dim}-d (EMBEDDING_DIM). Re-create the index first."
            )
        self.dim = dim
        logger.info("embedding_model_loaded", model=model_name, device=self.device, dim=dim)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._encode(texts)

    async def embed_query(self, text: str) -> list[float]:
        # bge models retrieve better when queries (not passages) carry an instruction prefix.
        return (await self._encode([self._query_instruction + text]))[0]

    async def _encode(self, texts: list[str]) -> list[list[float]]:
        async with self._semaphore:
            try:
                vectors = await anyio.to_thread.run_sync(self._encode_sync, texts)
            except Exception as exc:
                logger.exception("embedding_failed", model=self.model, device=self.device)
                raise EmbeddingUnavailableError() from exc
        return vectors

    def _encode_sync(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts,
            batch_size=self._batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vectors.tolist()


_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be by can do does for from has have how i if in is it its of on or "
    "our should so that the their there this to was we what when where which who why will "
    "with you your".split()
)


class HashEmbeddings:
    """Feature-hashing embedder: tokens are hashed into a fixed number of signed buckets.

    Texts sharing words get similar vectors, which is enough for deterministic tests and a
    no-download demo. It does not understand synonyms or paraphrases.
    """

    name = "hash"
    device = "cpu"

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.model = f"feature-hash-{dim}"

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        for token in _TOKEN.findall(text.lower()):
            if token in _STOPWORDS:
                continue
            token = token[:-1] if len(token) > 3 and token.endswith("s") else token  # crude plural folding
            digest = hashlib.blake2b(token.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vector))
        return [v / norm for v in vector] if norm else vector
