from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables (or a local .env file).

    Every value has a safe local default so the service starts without any configuration.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- Application ---
    app_name: str = "Mini Knowledge Assistant"
    environment: Literal["local", "test", "staging", "production"] = "local"
    log_level: str = "INFO"
    log_json: bool = True
    # Comma-separated list; only needed when the API is called directly from a browser
    # (the bundled frontend goes through the Vite proxy and is same-origin).
    cors_origins: str = "http://localhost:5173"
    max_request_bytes: int = Field(default=1_000_000, ge=1_024)

    # --- PostgreSQL (metadata, content, chunks, vectors, question history) ---
    database_url: str = "postgresql+asyncpg://knowledge:knowledge@localhost:5433/knowledge"
    db_pool_size: int = Field(default=10, ge=1)
    db_max_overflow: int = Field(default=10, ge=0)
    db_pool_timeout_s: float = Field(default=5.0, gt=0)
    db_statement_timeout_ms: int = Field(default=5_000, ge=100)

    # --- Redis (shared rate-limit counters) ---
    redis_url: str | None = "redis://localhost:6380/0"
    redis_timeout_s: float = Field(default=0.5, gt=0)

    # --- Chunking ---
    chunk_size: int = Field(default=800, ge=100, le=8_000)
    chunk_overlap: int = Field(default=150, ge=0)

    # --- Embeddings ---
    # "local": sentence-transformers model on GPU/CPU. "hash": no-download lexical fallback.
    embedding_provider: Literal["local", "hash"] = "local"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_device: Literal["auto", "cuda", "cpu"] = "auto"
    embedding_query_instruction: str = "Represent this sentence for searching relevant passages: "
    embedding_max_concurrency: int = Field(default=2, ge=1)

    @model_validator(mode="after")
    def _check_chunking(self) -> "Settings":
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
