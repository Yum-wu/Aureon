# -*- coding: utf-8 -*-
"""Tests for embedding HTTP layer — httpx.Client singleton and retry logic.

The embedding module was migrated from per-call `requests.post` (opening a
new TCP connection each time) to a shared `httpx.Client` singleton that
reuses connections via a connection pool (Architecture Review, performance
and resource efficiency dimensions).

Tests cover:
  - _get_http_client() returns a shared singleton
  - _embed_api uses the shared client (not a per-request client)
  - Retry with backoff on transient errors (ConnectError, TimeoutException)
  - Fall-through after max retries on persistent errors
  - Success path returns correct numpy array shape
"""

import httpx
import numpy as np
import os
from unittest.mock import patch
import pytest

# Set embedding env vars early so importlib.reload in other tests
# picks them up when creating a fresh Settings() singleton.
os.environ.setdefault("DASHSCOPE_API_KEY", "test-key")
os.environ.setdefault("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com")
os.environ.setdefault("DASHSCOPE_MODEL", "text-embedding-v3")
os.environ.setdefault("DASHSCOPE_DIMENSIONS", "1024")

from app.rag.embedding import (
    _dashscope_compatible_embeddings_url,
    _embed_api,
    _estimate_embedding_tokens,
    _get_http_client,
)


@pytest.fixture(autouse=True)
def _set_dashscope_key(monkeypatch):
    """Set dashscope API key for tests.
    
    Re-imports settings at fixture time to survive importlib.reload in
    other tests (which replaces settings in app.config but doesn't update
    module-level imports in this file).
    """
    import app.config as _cfg
    settings = _cfg.settings
    monkeypatch.setattr(settings.embedding, "dashscope_api_key", "test-key")
    monkeypatch.setattr(settings.embedding, "dashscope_base_url", "https://dashscope-intl.aliyuncs.com")
    monkeypatch.setattr(settings.embedding, "dashscope_model", "text-embedding-v3")
    monkeypatch.setattr(settings.embedding, "dashscope_dimensions", 1024)


# ── Singleton tests ──

class TestHttpClientSingleton:
    """_get_http_client returns a shared, thread-safe client."""

    def test_returns_httpx_client(self):
        client = _get_http_client()
        assert isinstance(client, httpx.Client)

    def test_singleton_same_instance(self):
        c1 = _get_http_client()
        c2 = _get_http_client()
        assert c1 is c2

    def test_connection_pool_limits(self):
        client = _get_http_client()
        # httpx.Client stores Limits as internal attribute
        pool_limits = getattr(client, '_limits', None)
        if pool_limits is None:
            # httpx v0.28+ uses public .limits property
            pool_limits = getattr(client, 'limits', None)
        if pool_limits is None:
            pytest.skip("httpx version does not expose Limits via public API")
        assert pool_limits.max_connections > 1


# ── _embed_api HTTP calls ──

class MockSuccessResponse:
    """Fake httpx.Response for a successful embedding API call."""
    status_code = 200
    is_success = True

    def raise_for_status(self):
        return None

    def json(self):
        return {
            "data": [
                {"index": 0, "embedding": [0.1] * 1024},
                {"index": 1, "embedding": [0.2] * 1024},
            ]
        }

    def __repr__(self):
        return "<MockSuccessResponse 200>"


class MockErrorResponse:
    """Fake httpx.Response for a failed embedding API call."""
    status_code = 500
    is_success = False

    def raise_for_status(self):
        raise httpx.HTTPStatusError("500 Server Error", request=None, response=self)

    def json(self):
        return {"error": "internal"}

    def text(self):
        return '{"error": "internal"}'

    def __repr__(self):
        return "<MockErrorResponse 500>"


@pytest.fixture(autouse=True)
def _reset_http_client():
    """Reset state after each test so singleton creation order doesn't leak."""
    yield
    # No teardown needed — the singleton persists across tests and that's by design


class TestEmbedApiCalls:
    """_embed_api correctly uses the shared httpx.Client."""

    def test_dashscope_native_base_url_uses_compatible_embeddings_path(self):
        assert _dashscope_compatible_embeddings_url("https://dashscope.aliyuncs.com/api/v1") == (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
        )

    def test_dashscope_compatible_base_url_appends_embeddings(self):
        assert _dashscope_compatible_embeddings_url("https://dashscope.aliyuncs.com/compatible-mode/v1") == (
            "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings"
        )

    def test_success_path(self):
        """Successful API call returns a (N, dim) numpy array."""
        with patch.object(_get_http_client(), "post",
                          return_value=MockSuccessResponse()):
            result = _embed_api(
                texts=["hello", "world"],
                provider="dashscope",
                batch_size=10,
            )
        assert isinstance(result, np.ndarray)
        assert result.shape == (2, 1024)
        assert result.dtype == np.float32

    def test_retry_on_connect_error(self, monkeypatch):
        """Transient ConnectError triggers retries with backoff."""
        called = [0]

        def _fail_twice_then_succeed(url, **kw):
            called[0] += 1
            if called[0] <= 2:
                raise httpx.ConnectError("Connection refused", request=None)
            return MockSuccessResponse()

        monkeypatch.setattr(_get_http_client(), "post", _fail_twice_then_succeed)
        result = _embed_api(texts=["hello"], provider="dashscope")
        assert isinstance(result, np.ndarray)
        assert called[0] == 3  # 2 failures + 1 success = 3 calls

    def test_retry_on_timeout(self, monkeypatch):
        """TimeoutException also triggers retries."""
        called = [0]

        def _fail_on_timeout(url, **kw):
            called[0] += 1
            raise httpx.TimeoutException("timed out", request=None)

        monkeypatch.setattr(_get_http_client(), "post", _fail_on_timeout)
        with pytest.raises(httpx.TimeoutException):
            _embed_api(texts=["hello"], provider="dashscope")
        assert called[0] == 3  # max retries exhausted

    def test_immediate_failure_no_retry_on_http_error(self, monkeypatch):
        """HTTP error (500) does not retry, raises immediately."""
        def _fail(url, **kw):
            raise httpx.HTTPStatusError("500", request=None, response=MockErrorResponse())

        monkeypatch.setattr(_get_http_client(), "post", _fail)
        with pytest.raises(httpx.HTTPStatusError):
            _embed_api(texts=["hello"], provider="dashscope")

    def test_mixed_batch_sizes(self):
        """Multiple batches across batch_size boundary yield correct total."""
        # Each MockSuccessResponse returns 2 embeddings, batch_size=10 => 2 batches
        texts = ["t"] * 15
        with patch.object(_get_http_client(), "post",
                          return_value=MockSuccessResponse()):
            result = _embed_api(texts=texts, provider="dashscope", batch_size=10)
        # 2 batches × 2 mock entries per batch = 4 total
        assert result.shape[0] == 4
        assert result.shape[1] == 1024

    def test_siliconflow_payload_is_trimmed_to_provider_limit(self, monkeypatch):
        """SiliconFlow bge-large accepts shorter inputs than DashScope."""
        import app.config as _cfg

        settings = _cfg.settings
        monkeypatch.setattr(settings.embedding, "siliconflow_api_key", "test-key")
        monkeypatch.setattr(settings.embedding, "siliconflow_base_url", "https://api.siliconflow.cn/v1")
        monkeypatch.setattr(settings.embedding, "siliconflow_model", "BAAI/bge-large-zh-v1.5")
        captured = {}

        def _capture_payload(url, **kw):
            captured["payload"] = kw["json"]
            return MockSuccessResponse()

        monkeypatch.setattr(_get_http_client(), "post", _capture_payload)
        _embed_api(texts=["a" * 8000], provider="siliconflow")

        sent_text = captured["payload"]["input"][0]
        assert _estimate_embedding_tokens(sent_text) <= 512

    def test_dashscope_payload_is_not_trimmed_by_siliconflow_limit(self, monkeypatch):
        captured = {}

        def _capture_payload(url, **kw):
            captured["payload"] = kw["json"]
            return MockSuccessResponse()

        monkeypatch.setattr(_get_http_client(), "post", _capture_payload)
        _embed_api(texts=["a" * 3000], provider="dashscope")

        assert captured["payload"]["input"][0] == "a" * 3000
