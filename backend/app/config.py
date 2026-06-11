from typing import Optional

import os

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    llm_api_key: str = ""
    llm_model: str = "qwen3.5-flash"
    llm_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    fallback_api_key: str = ""
    fallback_model: str = "GLM-4-Flash-250414"
    fallback_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    langchain_api_key: str = ""
    langchain_project: str = "chatbot-rag"
    llm_semaphore_deepseek: int = 30
    llm_semaphore_reasoner: int = 10
    llm_semaphore_default: int = 20


class EmbeddingSettings(BaseModel):
    embedding_api_key: str = ""
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    embedding_model: str = "embedding-2"
    embedding_dim: int = 768
    embedding_batch_size: int = 64
    gpu_enabled: bool = False
    embed_gpu_threshold: int = 4
    skip_local_embed: bool = False
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "text-embedding-v4"
    dashscope_dimensions: int = 768
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "BAAI/bge-large-zh-v1.5"


class VectorStoreSettings(BaseModel):
    vector_backend: str = "qdrant"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "aureon"
    rrf_k: int = 200
    retrieval_multiplier: int = 7
    multi_query_enabled: bool = True
    semantic_chunking_enabled: bool = True
    min_relevance_score: float = 0.003
    vector_min_cosine: float = 0.001
    vector_max_contrib: int = 10
    vector_confidence_threshold: float = 0.01
    low_score_threshold: float = 0.004
    negative_detection_enabled: bool = True
    context_compression_enabled: bool = True
    context_compression_threshold: float = 0.15
    kw_min_raw_score: float = 0.15
    stats_cache_ttl: float = 60.0
    hyde_enabled: bool = False
    hyde_fallback_threshold: float = 0.01
    high_score_skip_threshold: float = 0.01
    classifier_cache_ttl: float = 3600.0


class RerankSettings(BaseModel):
    rerank_enabled: bool = True
    rerank_backend: str = "api"
    rerank_provider: str = "dashscope"
    rerank_candidates: int = 12
    reranker_device: str = "cpu"
    adaptive_rerank_enabled: bool = True
    adaptive_rerank_threshold: float = 0.5
    ensemble_rerank_enabled: bool = False
    ensemble_bge_weight: float = 0.6
    ensemble_cohere_weight: float = 0.3
    ensemble_jina_weight: float = 0.1
    cohere_api_key: Optional[str] = None
    cohere_rerank_model: str = "rerank-multilingual-v3.0"
    jina_api_key: Optional[str] = None
    dashscope_rerank_url: str = "https://dashscope-intl.aliyuncs.com/compatible-api/v1"
    dashscope_rerank_model: str = "qwen3-rerank"
    rerank_semaphore: int = 40


class AuthSettings(BaseModel):
    api_auth_key: str = ""


class CacheSettings(BaseModel):
    redis_url: str = ""
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.92
    semantic_cache_ttl: int = 86400
    semantic_cache_max_size: int = 10000
    semantic_cache_embedding_model: str = "BAAI/bge-large-zh-v1.5"


class DatabaseSettings(BaseModel):
    database_url: str = ""
    es_url: str = "http://localhost:9200"
    es_index: str = "aureon"
    es_password: str = ""
    bm25_backend: str = "memory"


class AppSettings(BaseModel):
    tavily_api_key: str = ""
    tenant_allowlist: str = ""
    blog_url: str = ""
    blog_sync_enabled: bool = False
    blog_sync_api_key: str = ""
    cors_origins: str = "http://localhost:5173"
    websocket_enabled: bool = True
    websocket_max_connections: int = 300
    websocket_heartbeat_interval: int = 30
    websocket_heartbeat_timeout: int = 300
    conversation_max_turns: int = 20
    conversation_max_context_tokens: int = 4000
    tool_calling_enabled: bool = True
    queue_timeout_seconds: float = 30.0
    llm_semaphore_embedding: int = 50
    rag_semaphore: int = 40
    crag_enabled: bool = False
    crag_high_confidence: float = 0.05
    crag_low_confidence: float = 0.01
    crag_ambiguous_threshold: float = 0.03
    reflection_enabled: bool = False
    offload_max_chars: int = 1000
    session_max_messages: int = 500
    auto_index_enabled: bool = True
    benchmark_mode: str = "local"


class Settings(BaseSettings):
    """Application configuration loaded from .env file.

    Nested sub-models group related settings by domain.
    Environment variables use __ delimiter: VECTOR_STORE__QDRANT_URL
    Flat field access maintained via __getattr__ for backward compat.
    """

    llm: LLMSettings = Field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = Field(default_factory=EmbeddingSettings)
    vector_store: VectorStoreSettings = Field(default_factory=VectorStoreSettings)
    rerank: RerankSettings = Field(default_factory=RerankSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    app: AppSettings = Field(default_factory=AppSettings)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context):
        """Re-read flat and nested (__-delimited) env vars into sub-models.

        Nested env vars take priority over flat env vars. Empty string values
        are skipped to avoid coercing them to invalid types (e.g. int("")).
        This avoids the pydantic-settings JSONDecodeError on empty
        DATABASE__DATABASE_URL, because we never ask pydantic-settings to
        parse nested env vars as JSON.
        """
        cls_fields = type(self).model_fields
        for sub_field in cls_fields:
            sub_model = getattr(self, sub_field)
            if isinstance(sub_model, BaseModel):
                updates = {}
                for field_name in sub_model.model_fields:
                    flat_name = field_name.upper()
                    nested_name = f"{sub_field.upper()}__{flat_name}"
                    nested_val = os.environ.get(nested_name, "")
                    flat_val = os.environ.get(flat_name, "")
                    if nested_val != "":
                        updates[field_name] = nested_val
                    elif flat_val != "":
                        updates[field_name] = flat_val
                if updates:
                    current = sub_model.model_dump()
                    current.update(updates)
                    object.__setattr__(
                        self, sub_field,
                        type(sub_model).model_validate(current),
                    )

    def __getattr__(self, name: str):
        cls_fields = type(self).model_fields
        for sub_field in cls_fields:
            sub_model = getattr(self, sub_field)
            if isinstance(sub_model, BaseModel) and hasattr(sub_model, name):
                return getattr(sub_model, name)
        msg = f"{type(self).__name__!r} object has no attribute {name!r}"
        raise AttributeError(msg)


settings = Settings()


def get_settings() -> Settings:
    """FastAPI dependency: returns the global Settings singleton.

    Usage in routers:
        from app.config import get_settings
        @router.post("/")
        async def handler(settings: Settings = Depends(get_settings)):
            ...
    """
    return settings


MODEL_REGISTRY = {
    "deepseek-chat": {
        "provider": "deepseek",
        "model": settings.llm.llm_model,
        "base_url": settings.llm.llm_base_url,
        "api_key": settings.llm.llm_api_key,
        "max_tokens": 8192,
    },
    "gpt-4o": {
        "provider": "openai",
        "model": "gpt-4o",
        "base_url": "https://api.openai.com/v1",
        "api_key": "",
        "max_tokens": 16384,
    },
    "claude-sonnet-4-20250514": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "base_url": "https://api.anthropic.com",
        "api_key": "",
        "max_tokens": 8192,
    },
}
