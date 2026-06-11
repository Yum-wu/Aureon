# -*- coding: utf-8 -*-
"""Custom exceptions for Aureon API.

All custom exceptions inherit from AureonException which itself inherits
from FastAPI's HTTPException.  Each subclass carries a fixed status_code
and an ``error_type`` string that is included in the JSON response body
via the ``aureon_exception_handler`` registered in ``main.py``.

Unified error format::

    {
        "error": "<error_type>",
        "detail": "<human-readable message>",
        "request_id": "<uuid from structlog contextvars>",
        "error_type": "<error_type>"
    }
"""


from fastapi import HTTPException


class AureonException(HTTPException):
    """Base exception for all Aureon-specific errors.

    Subclasses must set ``status_code`` as a class attribute so the
    auto-registered handler can read it without instantiation side-effects.
    """

    error_type: str = "AureonException"

    def __init__(self, status_code: int = 500, detail: str = "Internal server error"):
        super().__init__(status_code=status_code, detail=detail)


# Authentication & Authorization

class AuthenticationError(AureonException):
    """Raised when authentication fails (invalid / missing credentials)."""

    error_type = "AuthenticationError"

    def __init__(self, detail: str = "Authentication required"):
        super().__init__(status_code=401, detail=detail)


class AuthorizationError(AureonException):
    """Raised when the authenticated user lacks the required role / permission."""

    error_type = "AuthorizationError"

    def __init__(self, detail: str = "Insufficient permissions"):
        super().__init__(status_code=403, detail=detail)


# Resource Errors

class NotFoundError(AureonException):
    """Raised when a requested resource does not exist."""

    error_type = "NotFoundError"

    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status_code=404, detail=detail)


# Rate Limiting

class RateLimitError(AureonException):
    """Raised when the client exceeds the allowed request rate."""

    error_type = "RateLimitError"

    def __init__(self, detail: str = "Rate limit exceeded. Please try again later."):
        super().__init__(status_code=429, detail=detail)


# LLM / External Service Errors

class LLMServiceError(AureonException):
    """Raised when an LLM or upstream AI service call fails."""

    error_type = "LLMServiceError"

    def __init__(self, detail: str = "LLM service unavailable"):
        super().__init__(status_code=503, detail=detail)


# Existing Subclasses (kept for backwards compatibility)

class RedisUnavailableError(AureonException):
    """Raised when Redis is unreachable or returns an error."""

    error_type = "RedisUnavailableError"

    def __init__(self, detail: str = "Redis service unavailable"):
        super().__init__(status_code=503, detail=detail)


class VectorStoreError(AureonException):
    """Raised when ChromaDB / vector store operations fail."""

    error_type = "VectorStoreError"

    def __init__(self, detail: str = "Vector store error"):
        super().__init__(status_code=500, detail=detail)
