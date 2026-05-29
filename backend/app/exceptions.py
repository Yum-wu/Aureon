"""Custom exceptions for Aureon API.

All custom exceptions inherit from AureonException which itself inherits
from FastAPI's HTTPException.  Each subclass carries a fixed status_code
and an ``error_type`` string that is included in the JSON response body
via the ``aureon_exception_handler`` registered in ``main.py``.
"""

from fastapi import HTTPException


class AureonException(HTTPException):
    """Base exception for all Aureon-specific errors.

    Subclasses must set ``status_code`` as a class attribute so the
    auto-registered handler can read it without instantiation side-effects.
    """

    error_type: str = "AureonException"

    def __init__(self, detail: str = "Internal server error"):
        super().__init__(status_code=500, detail=detail)


class RedisUnavailableError(AureonException):
    """Raised when Redis is unreachable or returns an error."""

    error_type = "RedisUnavailableError"

    def __init__(self, detail: str = "Redis service unavailable"):
        super().__init__(detail=detail)
        self.status_code = 503


class VectorStoreError(AureonException):
    """Raised when ChromaDB / vector store operations fail."""

    error_type = "VectorStoreError"

    def __init__(self, detail: str = "Vector store error"):
        super().__init__(detail=detail)
        self.status_code = 500
