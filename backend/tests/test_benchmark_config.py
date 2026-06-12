"""Tests for benchmark configuration."""

import os
import pytest
from unittest.mock import patch


def test_detect_environment_local():
    """Test local environment detection."""
    with patch.dict(os.environ, {"BENCHMARK_MODE": "local"}, clear=False):
        from app.benchmark.config import detect_environment
        env = detect_environment()
        assert env.mode == "local"
        assert env.base_url is None
        assert env.api_key is None


def test_detect_environment_railway():
    """Test Railway environment detection."""
    import importlib
    import app.benchmark.config as benchmark_config
    with patch.dict(os.environ, {
        "BENCHMARK_MODE": "railway",
        "RAILWAY_API_URL": "https://test.up.railway.app",
        "RAILWAY_API_KEY": "test-key",
    }, clear=False):
        importlib.reload(benchmark_config)
        env = benchmark_config.detect_environment()
        assert env.mode == "railway"
        assert env.base_url == "https://test.up.railway.app"
        assert env.api_key == "test-key"


def test_concurrency_config_defaults():
    """Test default concurrency configuration."""
    from app.benchmark.config import ConcurrencyConfig
    config = ConcurrencyConfig()
    assert config.http_pool_limit == 100
    assert config.timeout_seconds == 120
    assert "qwen3.6-flash" in config.semaphores
