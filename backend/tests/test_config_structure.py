"""Tests for nested config structure (TDD Phase 1.1)."""

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


class TestSettingsRailwayEnvCompat:
    """Settings() must not crash when PaaS providers set empty / scalar
    placeholders for nested sub-model env vars (e.g. Railway: DATABASE='')."""

    def test_empty_database_env_does_not_crash(self, monkeypatch, tmp_path):
        # Railway may export DATABASE='' or other PaaS placeholders that
        # pydantic-settings tries to json.loads() as a complex value.
        # The config must load successfully and fall back to defaults.
        monkeypatch.chdir(tmp_path)  # no .env file in tmp_path
        monkeypatch.setenv("DATABASE", "")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE__DATABASE_URL", raising=False)
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None
        # Default empty url is preserved, vector store stays usable.
        assert config_module.settings.database.database_url == ""
        assert config_module.settings.qdrant_url == "http://localhost:6333"

    def test_non_json_scalar_env_does_not_crash(self, monkeypatch, tmp_path):
        # Some hosts may export DATABASE='postgres' (non-JSON scalar) which
        # pydantic-settings would also try to json.loads() and fail on.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE", "postgres")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE__DATABASE_URL", raising=False)
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None
        # The malformed value should be ignored, defaults preserved.
        assert config_module.settings.database.database_url == ""

    def test_url_valued_submodel_env_does_not_crash(self, monkeypatch, tmp_path):
        # Railway may set DATABASE=postgres://user:pass@host:5432/db
        # which is a valid URL but not a JSON object.
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("DATABASE", "postgres://user:pass@host:5432/db")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE__DATABASE_URL", raising=False)
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None
        assert config_module.settings.database.database_url == ""

    def test_json_null_submodel_env_does_not_crash(self, monkeypatch):
        # Some PaaS set LLM=null — valid JSON but not a dict.
        # 关键是 settings 不崩溃，而非 llm_api_key 必须为空
        # （因为 .env 中的 LLM_API_KEY 仍会生效）
        monkeypatch.setenv("LLM", "null")
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None
        # 验证 llm 子模型存在且可访问
        assert hasattr(config_module.settings.llm, "llm_api_key")

    def test_json_bool_submodel_env_does_not_crash(self, monkeypatch):
        # LLM=true is valid JSON but not a dict.
        monkeypatch.setenv("LLM", "true")
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None

    def test_valid_json_dict_submodel_env_is_kept(self, monkeypatch, tmp_path):
        # A proper JSON object should be parsed and kept.
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE__DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE", '{"database_url": "sqlite:///test.db"}')
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None
        assert config_module.settings.database.database_url == "sqlite:///test.db"

    def test_multiple_malformed_submodel_envs(self, monkeypatch):
        # Multiple sub-model env vars set to non-JSON values simultaneously.
        # 关键是 settings 不崩溃，而非子模型字段必须为空
        # （因为 .env 中的具体字段仍会生效）
        monkeypatch.setenv("DATABASE", "postgres://host/db")
        monkeypatch.setenv("LLM", "sk-12345")
        monkeypatch.setenv("CACHE", "redis://host:6379")
        import importlib
        import app.config as config_module
        importlib.reload(config_module)
        assert config_module.settings is not None
        # 验证子模型存在且可访问（不崩溃即通过）
        assert hasattr(config_module.settings.database, "database_url")
        assert hasattr(config_module.settings.llm, "llm_api_key")
        assert hasattr(config_module.settings.cache, "redis_url")
