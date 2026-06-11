from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from .env file."""

    # Primary LLM (DashScope Qwen, Singapore OpenAI-compatible endpoint)
    llm_api_key: str = ""
    llm_model: str = "qwen3.6-flash"
    llm_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"

    # Fallback LLM (Zhipu AI, used when primary fails)
    fallback_api_key: str = ""
    fallback_model: str = "GLM-4-Flash-250414"
    fallback_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"

    # Embedding API — multi-provider fallback chain
    # Priority: local BGE (1024d) → DashScope (768d) → SiliconFlow → Zhipu
    embedding_api_key: str = ""
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    embedding_model: str = "embedding-2"

    # Global embedding dimension (used by vector store for index size)
    # Set to 768 when using DashScope text-embedding-v4 for smaller storage footprint
    embedding_dim: int = 768

    # DashScope (通义千问) — primary API fallback, supports adjustable dimensions
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "text-embedding-v4"
    dashscope_dimensions: int = 768

    # SiliconFlow — secondary API fallback, hosts BGE models
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "BAAI/bge-large-zh-v1.5"

    tavily_api_key: str = ""

    # Multi-tenant isolation
    # Allowed tenant IDs for X-Tenant-ID header validation (comma-separated)
    # Empty string means all values are accepted (no whitelist)
    tenant_allowlist: str = ""

    # Blog sync configuration
    blog_url: str = ""  # Personal blog URL for sync feature
    blog_sync_enabled: bool = False  # Enable/disable blog sync feature
    blog_sync_api_key: str = ""  # API key for blog sync authentication

    # Database (PostgreSQL, optional)
    database_url: str = ""

    redis_url: str = ""

    # API Authentication
    api_auth_key: str = ""  # Shared API key for authentication (empty = disabled)

    # Vector store backend ("qdrant" recommended; "chroma" deprecated)
    vector_backend: str = "qdrant"
    qdrant_url: str = "http://localhost:6333"  # env: QDRANT_URL
    qdrant_api_key: str = ""  # env: QDRANT_API_KEY
    qdrant_collection: str = "aureon"  # env: QDRANT_COLLECTION

    # GPU settings (auto-detect CUDA availability)
    gpu_enabled: bool = False  # Set True only when GPU confirmed
    embedding_batch_size: int = 64
    reranker_device: str = "cpu"  # "cuda" or "cpu"

    offload_max_chars: int = 1000
    session_max_messages: int = 500

    langchain_api_key: str = ""
    langchain_project: str = "chatbot-rag"

    # Elasticsearch BM25 backend
    es_url: str = "http://localhost:9200"
    es_index: str = "aureon"
    es_password: str = ""  # ES authentication password (empty = no auth)
    bm25_backend: str = "memory"

    # Semantic Cache
    semantic_cache_enabled: bool = True
    semantic_cache_threshold: float = 0.92
    semantic_cache_ttl: int = 86400
    semantic_cache_max_size: int = 10000
    semantic_cache_embedding_model: str = "BAAI/bge-large-zh-v1.5"

    # Auto index rebuild on startup when articles change
    auto_index_enabled: bool = True

    # RAG retrieval tuning
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
    context_compression_threshold: float = 0.35
    kw_min_raw_score: float = 0.15
    stats_cache_ttl: float = 60.0
    skip_local_embed: bool = False

    # GPU embed threshold
    embed_gpu_threshold: int = 4

    # HyDE (Hypothetical Document Embedding)
    hyde_enabled: bool = False
    hyde_fallback_threshold: float = 0.01

    # RAG classifier cache
    high_score_skip_threshold: float = 0.01
    classifier_cache_ttl: float = 3600.0

    # Benchmark
    benchmark_mode: str = "local"

    # CORS
    cors_origins: str = "http://localhost:5173"

    # Adaptive Re-ranking
    rerank_enabled: bool = True
    # Rerank backend: "local" (CrossEncoder) or "api" (remote API, safe for Railway)
    rerank_backend: str = "api"
    adaptive_rerank_enabled: bool = True
    ensemble_rerank_enabled: bool = False
    rerank_candidates: int = 12
    adaptive_rerank_threshold: float = 0.5

    # Ensemble Reranker Weights
    ensemble_bge_weight: float = 0.6
    ensemble_cohere_weight: float = 0.3
    ensemble_jina_weight: float = 0.1

    # External Reranker APIs
    cohere_api_key: Optional[str] = None
    cohere_rerank_model: str = "rerank-multilingual-v3.0"
    jina_api_key: Optional[str] = None

    # DashScope Reranker (qwen3-rerank, same platform as embedding)
    # Note: qwen3-rerank uses compatible-api (not compatible-mode) endpoint
    dashscope_rerank_url: str = "https://dashscope-intl.aliyuncs.com/compatible-api/v1"
    dashscope_rerank_model: str = "qwen3-rerank"
    # Rerank provider priority: "dashscope" → "siliconflow" → "cohere" → "jina"
    rerank_provider: str = "dashscope"

    # WebSocket Configuration
    websocket_enabled: bool = True
    websocket_max_connections: int = 300
    websocket_heartbeat_interval: int = 30
    websocket_heartbeat_timeout: int = 300

    # Conversation Configuration
    conversation_max_turns: int = 20
    conversation_max_context_tokens: int = 4000

    # Tool Calling Configuration
    tool_calling_enabled: bool = True

    # Concurrency limits
    queue_timeout_seconds: float = 30.0
    llm_semaphore_deepseek: int = 30
    llm_semaphore_reasoner: int = 10
    llm_semaphore_embedding: int = 50
    llm_semaphore_default: int = 20
    rag_semaphore: int = 40
    rerank_semaphore: int = 40

    # CRAG confidence thresholds
    crag_enabled: bool = False
    crag_high_confidence: float = 0.05
    crag_low_confidence: float = 0.01
    crag_ambiguous_threshold: float = 0.03

    # Post-generation reflection
    reflection_enabled: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()

MODEL_REGISTRY = {
    "deepseek-chat": {
        "provider": "deepseek",
        "model": settings.llm_model,
        "base_url": settings.llm_base_url,
        "api_key": settings.llm_api_key,
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
