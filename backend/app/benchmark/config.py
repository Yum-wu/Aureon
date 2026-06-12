"""Benchmark configuration management."""

import os
from dataclasses import dataclass, field
from typing import Optional, Dict


@dataclass
class BenchmarkEnv:
    """Benchmark environment configuration."""
    mode: str  # "local" | "railway"
    base_url: Optional[str]
    api_key: Optional[str]
    vector_backend: str  # "qdrant" (default) | "chroma" (legacy)
    embedding_provider: str  # "local" | "dashscope" | "siliconflow"
    rerank_provider: str  # "api" | "local"


@dataclass
class ConcurrencyConfig:
    """Concurrency and connection pool configuration."""
    http_pool_limit: int = 100
    semaphores: Dict[str, int] = field(default_factory=dict)
    timeout_seconds: int = 120
    queue_timeout_seconds: int = 60

    def __post_init__(self):
        if not self.semaphores:
            from app.config import settings
            mode = settings.benchmark_mode.lower()
            if mode == "railway":
                self.semaphores = {
                    "qwen3.6-flash": int(os.getenv("LLM_SEMAPHORE_QWEN", "80")),
                    "dashscope-embedding": int(os.getenv("LLM_SEMAPHORE_EMBEDDING", "80")),
                    "rag_pipeline": int(os.getenv("RAG_SEMAPHORE", "80")),
                    "rerank": int(os.getenv("RERANK_SEMAPHORE", "40")),
                }
            else:
                self.semaphores = {
                    "qwen3.6-flash": 30,
                    "dashscope-embedding": 50,
                    "rag_pipeline": 40,
                    "rerank": 20,
                }


# Pricing table (USD per 1000 tokens)
PRICING = {
    "dashscope_embedding": 0.00007,   # $0.07/1M tokens
    "dashscope_rerank": 0.0001,       # $0.1/1M tokens
    "qwen_flash": 0.00028,            # 通义千问 Flash 定价
}


def detect_environment() -> BenchmarkEnv:
    """Auto-detect or configure benchmark environment."""
    mode = os.getenv("BENCHMARK_MODE", "local").lower()

    if mode == "railway":
        return BenchmarkEnv(
            mode="railway",
            base_url=os.getenv("RAILWAY_API_URL"),
            api_key=os.getenv("RAILWAY_API_KEY"),
            vector_backend=os.getenv("VECTOR_BACKEND", "qdrant"),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "dashscope"),
            rerank_provider=os.getenv("RERANK_PROVIDER", "dashscope"),
        )
    else:
        try:
            from app.config import settings
            return BenchmarkEnv(
                mode="local",
                base_url=None,
                api_key=None,
                vector_backend=settings.vector_backend,
                embedding_provider="local",
                rerank_provider="api",
            )
        except ImportError:
            return BenchmarkEnv(
                mode="local",
                base_url=None,
                api_key=None,
                vector_backend=os.getenv("VECTOR_BACKEND", "qdrant"),
                embedding_provider="local",
                rerank_provider="api",
            )
