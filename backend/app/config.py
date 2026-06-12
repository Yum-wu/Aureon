from typing import Optional

import os

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseModel):
    llm_api_key: str = ""
    llm_model: str = "qwen3.6-flash"
    llm_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    fallback_api_key: str = ""
    fallback_model: str = "GLM-4-Flash-250414"
    fallback_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    langchain_api_key: str = ""
    langchain_project: str = "chatbot-rag"
    llm_semaphore_qwen: int = 30
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
    hnsw_m: int = 32
    hnsw_ef_construct: int = 200
    hnsw_ef_search: int = 128
    quantization_enabled: bool = True
    vectors_on_disk: bool = True


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
    environment: str = "production"  # "dev" or "production"


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
        env_nested_delimiter="__",
        # Treat empty env vars as unset so Railway / PaaS placeholders
        # (e.g. DATABASE='') don't crash pydantic-settings when it tries
        # to json.loads() them as complex sub-model values.
        env_ignore_empty=True,
    )

    def model_post_init(self, __context):
        """Re-read flat env vars into sub-models for backward compat.

        Only applies flat env var when the corresponding nested
        (__-delimited) env var is NOT set, so nested takes priority.
        """
        cls_fields = type(self).model_fields
        for sub_field in cls_fields:
            sub_model = getattr(self, sub_field)
            if isinstance(sub_model, BaseModel):
                updates = {}
                for field_name in type(sub_model).model_fields:
                    flat_name = field_name.upper()
                    nested_name = f"{sub_field.upper()}__{flat_name}"
                    if flat_name in os.environ and nested_name not in os.environ:
                        updates[field_name] = os.environ[flat_name]
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


def _sanitize_submodel_env() -> list[tuple[str, str]]:
    """Remove env vars matching sub-model names that aren't valid JSON dicts.

    PaaS platforms (Railway, Render, Heroku) may set env vars like
    DATABASE=postgres://... or LLM=null which pydantic-settings tries to
    json.loads() as complex sub-model values, causing SettingsError.
    Only valid JSON object values (e.g. DATABASE='{"database_url":"..."}')
    are kept; everything else is stripped so defaults take over.
    """
    import json as _json

    removed: list[tuple[str, str]] = []
    for _sub_field in Settings.model_fields:
        _env_name = _sub_field.upper()
        if _env_name not in os.environ:
            continue
        _val = os.environ[_env_name]
        _keep = False
        if _val:
            try:
                _parsed = _json.loads(_val)
                _keep = isinstance(_parsed, dict)
            except (_json.JSONDecodeError, ValueError):
                pass
        if not _keep:
            removed.append((_env_name, _val))
            os.environ.pop(_env_name)
    return removed


# Proactively sanitize before first Settings() creation so the normal path
# never hits a SettingsError from non-JSON sub-model env vars.
_sanitize_submodel_env()

try:
    settings = Settings()
except Exception as _init_err:
    # Safety net: if Settings() still fails (e.g. a nested __ env var with
    # an invalid value, or a validation error), strip ALL sub-model-related
    # env vars and retry with pure defaults.
    import warnings

    warnings.warn(
        f"Settings init failed ({type(_init_err).__name__}), "
        "removing all sub-model env vars and retrying with defaults",
        stacklevel=2,
    )
    _saved_env: dict[str, str] = {}
    for _key in list(os.environ.keys()):
        for _sub_field in Settings.model_fields:
            _prefix = _sub_field.upper() + "__"
            if _key.upper() == _sub_field.upper() or _key.upper().startswith(_prefix):
                _saved_env[_key] = os.environ.pop(_key)
    try:
        settings = Settings()
    finally:
        # Restore env vars so other code (e.g. model_post_init flat reads)
        # and downstream services can still access them.
        os.environ.update(_saved_env)


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
    "qwen3.6-flash": {
        "provider": "dashscope",
        "model": settings.llm.llm_model,
        "base_url": settings.llm.llm_base_url,
        "api_key": settings.llm.llm_api_key,
        "max_tokens": 8192,
    },
}
