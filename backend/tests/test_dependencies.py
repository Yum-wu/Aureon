"""Tests for FastAPI Redis dependency injection."""

import pytest
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

from app.dependencies import require_redis, get_redis_or_none


def test_require_redis_returns_client():
    """require_redis() returns the Redis client when Redis is available."""
    mock_client = MagicMock()
    with patch("app.dependencies._redis_getter", return_value=mock_client):
        result = require_redis()
    assert result is mock_client


def test_require_redis_raises_when_unavailable():
    """require_redis() raises HTTPException 503 when Redis is unavailable."""
    with patch("app.dependencies._redis_getter", return_value=None):
        with pytest.raises(HTTPException) as exc_info:
            require_redis()
    assert exc_info.value.status_code == 503


def test_require_redis_raises_when_false():
    """require_redis() raises HTTPException 503 when Redis returns False sentinel."""
    with patch("app.dependencies._redis_getter", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            require_redis()
    assert exc_info.value.status_code == 503


def test_get_redis_or_none_returns_client():
    """get_redis_or_none() returns the Redis client when Redis is available."""
    mock_client = MagicMock()
    with patch("app.dependencies._redis_getter", return_value=mock_client):
        result = get_redis_or_none()
    assert result is mock_client


def test_get_redis_or_none_returns_none_when_none():
    """get_redis_or_none() returns None when Redis returns None."""
    with patch("app.dependencies._redis_getter", return_value=None):
        result = get_redis_or_none()
    assert result is None


def test_get_redis_or_none_returns_none_when_false():
    """get_redis_or_none() returns None when Redis returns False sentinel."""
    with patch("app.dependencies._redis_getter", return_value=False):
        result = get_redis_or_none()
    assert result is None
