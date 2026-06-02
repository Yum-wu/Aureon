from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration loaded from .env file."""

    # Primary LLM (DeepSeek)
    llm_api_key: str = ""
    llm_model: str = "deepseek-v4-flash"
    llm_base_url: str = "https://api.deepseek.com"

    # Fallback LLM (Zhipu AI, used when primary fails)
    fallback_api_key: str = ""
    fallback_model: str = "GLM-4-Flash-250414"
    fallback_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"

    # Embedding API — multi-provider fallback chain
    # Priority: local BGE (512d) → DashScope → SiliconFlow → Zhipu
    embedding_api_key: str = ""
    embedding_base_url: str = "https://open.bigmodel.cn/api/paas/v4/"
    embedding_model: str = "embedding-2"
    embedding_dimensions: int = 1024  # only used by APIs that support dimension control

    # DashScope (通义千问) — primary API fallback, supports 512d
    dashscope_api_key: str = ""
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "text-embedding-v3"
    dashscope_dimensions: int = 1024

    # SiliconFlow — secondary API fallback, hosts BGE models
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    siliconflow_model: str = "BAAI/bge-small-zh-v1.5"

    tavily_api_key: str = ""

    # Blog sync configuration
    blog_url: str = ""  # Personal blog URL for sync feature
    blog_sync_enabled: bool = False  # Enable/disable blog sync feature

    redis_url: str = ""

    # Vector store backend ("chroma" or "qdrant")
    vector_backend: str = "chroma"
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str = ""

    offload_max_chars: int = 1000
    session_max_messages: int = 500

    langchain_api_key: str = ""
    langchain_project: str = "chatbot-rag"

    # Elasticsearch BM25 backend
    es_url: str = "http://localhost:9200"
    es_index: str = "aureon"
    bm25_backend: str = "memory"

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
