"""Tests for nested config structure (TDD Phase 1.1)."""

import pytest
from app.config import Settings


class TestSettingsNestedAccess:
    """Settings should expose domain-grouped sub-models."""

    def test_llm_group(self):
        from app.config import settings
        assert hasattr(settings, "llm")
        assert hasattr(settings.llm, "llm_api_key")
        assert hasattr(settings.llm, "llm_model")
        assert hasattr(settings.llm, "llm_base_url")
        assert isinstance(settings.llm.llm_api_key, str)

    def test_vector_store_group(self):
        from app.config import settings
        assert hasattr(settings, "vector_store")
        assert hasattr(settings.vector_store, "qdrant_url")
        assert hasattr(settings.vector_store, "qdrant_collection")
        assert hasattr(settings.vector_store, "vector_backend")
        assert settings.vector_store.qdrant_url

    def test_rerank_group(self):
        from app.config import settings
        assert hasattr(settings, "rerank")
        assert hasattr(settings.rerank, "rerank_enabled")
        assert hasattr(settings.rerank, "rerank_provider")
        assert hasattr(settings.rerank, "rerank_candidates")

    def test_embedding_group(self):
        from app.config import settings
        assert hasattr(settings, "embedding")
        assert hasattr(settings.embedding, "embedding_model")
        assert hasattr(settings.embedding, "embedding_dim")
        assert hasattr(settings.embedding, "embedding_batch_size")

    def test_auth_group(self):
        from app.config import settings
        assert hasattr(settings, "auth")
        assert hasattr(settings.auth, "api_auth_key")

    def test_cache_group(self):
        from app.config import settings
        assert hasattr(settings, "cache")
        assert hasattr(settings.cache, "redis_url")
        assert hasattr(settings.cache, "semantic_cache_enabled")
        assert hasattr(settings.cache, "semantic_cache_ttl")

    def test_database_group(self):
        from app.config import settings
        assert hasattr(settings, "database")
        assert hasattr(settings.database, "database_url")
        assert hasattr(settings.database, "es_url")
        assert hasattr(settings.database, "es_index")


class TestSettingsEnvParsing:
    """Nested settings should be populated from env vars with __ delimiter."""

    def test_nested_env_var_vector_store(self, monkeypatch):
        monkeypatch.setenv("VECTOR_STORE__QDRANT_URL", "http://custom:6333")
        s = Settings(_env_file=None)
        assert s.vector_store.qdrant_url == "http://custom:6333"

    def test_nested_env_var_rerank(self, monkeypatch):
        monkeypatch.setenv("RERANK__RERANK_ENABLED", "false")
        s = Settings(_env_file=None)
        assert s.rerank.rerank_enabled is False

    def test_nested_env_var_cache(self, monkeypatch):
        monkeypatch.setenv("CACHE__SEMANTIC_CACHE_TTL", "3600")
        s = Settings(_env_file=None)
        assert s.cache.semantic_cache_ttl == 3600


class TestSettingsBackwardCompat:
    """Flat field access should still work via __getattr__ fallback."""

    def test_flat_access_vector_backend(self):
        from app.config import settings
        assert settings.vector_backend == settings.vector_store.vector_backend

    def test_flat_access_qdrant_url(self):
        from app.config import settings
        assert settings.qdrant_url == settings.vector_store.qdrant_url

    def test_flat_access_rerank_enabled(self):
        from app.config import settings
        assert settings.rerank_enabled == settings.rerank.rerank_enabled

    def test_flat_access_llm_api_key(self):
        from app.config import settings
        assert settings.llm_api_key == settings.llm.llm_api_key

    def test_flat_access_redis_url(self):
        from app.config import settings
        assert settings.redis_url == settings.cache.redis_url
