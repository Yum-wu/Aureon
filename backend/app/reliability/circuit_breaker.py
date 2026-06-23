# -*- coding: utf-8 -*-
"""
Circuit Breaker Pattern Implementation

Provides CircuitBreaker class and decorators for wrapping LLM API calls
with fast-fail and automatic recovery capabilities.

Features:
- Open/Close/Half-Open states
- Configurable failure threshold and timeout
- Async decorator @circuit_breaker
- Context manager support
- Detailed metrics and logging
"""

import asyncio
import functools
import time
from enum import Enum
from typing import Callable, Optional, TypeVar
from contextlib import asynccontextmanager

import structlog

logger = structlog.get_logger()

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"        # Normal state, allow execution
    OPEN = "open"            # Tripped state, fast fail
    HALF_OPEN = "half_open"  # Half-open state, allow one attempt


class CircuitBreakerError(Exception):
    """Circuit breaker exception"""
    pass


class CircuitBreaker:
    """Circuit breaker implementation
    
    Args:
        failure_threshold: Number of consecutive failures before opening
        recovery_timeout: Seconds to wait before half-open attempt
        name: Breaker name for logging and metrics
        expected_exceptions: Exception types to catch
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        name: str = "default",
        expected_exceptions: tuple = (Exception,),
        success_threshold: int = 3,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self.expected_exceptions = expected_exceptions
        self.success_threshold = success_threshold

        # State
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

        # Metrics
        self._total_calls = 0
        self._total_failures = 0
        self._total_successes = 0
        self._total_rejected = 0

    @property
    def state(self) -> CircuitState:
        """Get current circuit state (pure read, no side effects)."""
        return self._state

    def _check_timeout(self) -> None:
        """Check if OPEN timeout has elapsed, transition to HALF_OPEN."""
        if self._state == CircuitState.OPEN and self._last_failure_time:
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_success_count = 0

    @property
    def failure_count(self) -> int:
        """Get current consecutive failure count"""
        return self._failure_count

    @property
    def metrics(self) -> dict:
        """Get circuit breaker metrics"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "success_threshold": self.success_threshold,
            "half_open_success_count": self._half_open_success_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "total_rejected": self._total_rejected,
            "consecutive_failures": self._failure_count,
            "last_failure_time": self._last_failure_time,
        }

    async def _handle_success(self):
        """Handle successful call"""
        if self._state == CircuitState.HALF_OPEN:
            self._half_open_success_count += 1
            if self._half_open_success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._half_open_success_count = 0
                logger.info(
                    "circuit_breaker_closed_after_probes",
                    breaker=self.name,
                    success_threshold=self.success_threshold,
                )
            else:
                logger.debug(
                    "circuit_breaker_half_open_progress",
                    breaker=self.name,
                    successes=self._half_open_success_count,
                    threshold=self.success_threshold,
                )
        else:
            self._failure_count = 0
            self._state = CircuitState.CLOSED

        self._total_successes += 1

        logger.debug(
            "circuit_breaker_success",
            breaker=self.name,
            state=self._state.value,
        )

    async def _handle_failure(self, error: Exception):
        """Handle failed call"""
        if self._state == CircuitState.HALF_OPEN:
            # HALF_OPEN failure: reset counter and go back to OPEN
            self._half_open_success_count = 0
            self._state = CircuitState.OPEN
            self._last_failure_time = time.monotonic()
            self._failure_count = self.failure_threshold
            self._total_failures += 1
            logger.warning(
                "circuit_breaker_reopened_from_half_open",
                breaker=self.name,
                error=str(error),
            )
            return

        self._failure_count += 1
        self._total_failures += 1
        self._last_failure_time = time.monotonic()

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "circuit_breaker_opened",
                breaker=self.name,
                failure_count=self._failure_count,
                threshold=self.failure_threshold,
                error=str(error),
            )
        else:
            logger.debug(
                "circuit_breaker_failure",
                breaker=self.name,
                failure_count=self._failure_count,
                threshold=self.failure_threshold,
                error=str(error),
            )

    async def _handle_rejection(self):
        """Handle rejected call (circuit open)"""
        self._total_rejected += 1

        logger.warning(
            "circuit_breaker_rejected",
            breaker=self.name,
            state=self._state.value,
            total_rejected=self._total_rejected,
        )

    @asynccontextmanager
    async def context(self):
        """Context manager for circuit breaker protected calls"""
        self._check_timeout()
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                await self._handle_rejection()
                raise CircuitBreakerError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Failures: {self._failure_count}/{self.failure_threshold}. "
                    f"Retry after {self.recovery_timeout}s."
                )

            self._total_calls += 1

            if current_state == CircuitState.HALF_OPEN:
                logger.info(
                    "circuit_breaker_half_open_attempt",
                    breaker=self.name,
                )

        try:
            yield self
            async with self._lock:
                await self._handle_success()
        except self.expected_exceptions as e:
            async with self._lock:
                await self._handle_failure(e)
            raise
        except Exception as e:
            # Unexpected exceptions also count as failures
            async with self._lock:
                await self._handle_failure(e)
            raise

    def reset(self):
        """Reset circuit breaker to initial state"""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._half_open_success_count = 0
        self._last_failure_time = None
        logger.info("circuit_breaker_reset", breaker=self.name)


def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
    name: Optional[str] = None,
    expected_exceptions: tuple = (Exception,),
) -> Callable:
    """Decorator for circuit breaker protected async functions
    
    Args:
        failure_threshold: Number of consecutive failures before opening
        recovery_timeout: Seconds to wait before half-open attempt
        name: Breaker name (defaults to function name)
        expected_exceptions: Exception types to catch
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        breaker_name = name or func.__name__
        breaker = CircuitBreaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            name=breaker_name,
            expected_exceptions=expected_exceptions,
        )

        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            async with breaker.context():
                return await func(*args, **kwargs)

        # Attach breaker to wrapper for inspection
        wrapper._circuit_breaker = breaker
        return wrapper

    return decorator


# Global circuit breaker registry
_circuit_breakers: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str, **kwargs) -> CircuitBreaker:
    """Get or create a named circuit breaker"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name=name, **kwargs)
    return _circuit_breakers[name]


def get_all_circuit_breakers() -> dict[str, CircuitBreaker]:
    """Get all registered circuit breakers"""
    return _circuit_breakers.copy()


def reset_all_circuit_breakers():
    """Reset all registered circuit breakers"""
    for breaker in _circuit_breakers.values():
        breaker.reset()
    _circuit_breakers.clear()
    logger.info("all_circuit_breakers_reset")


# Pre-configured circuit breakers for common use cases
def create_llm_circuit_breaker(
    name: str = "llm_api",
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Create a circuit breaker for LLM API calls"""
    return CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        name=name,
        expected_exceptions=(
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )


# Singleton instances for common use cases
llm_circuit_breaker = create_llm_circuit_breaker()
embedding_circuit_breaker = create_llm_circuit_breaker(name="embedding_api")
reranker_circuit_breaker = create_llm_circuit_breaker(name="reranker_api")


async def wrap_llm_call(
    func: Callable[..., T],
    name: Optional[str] = None,
    **kwargs,
) -> T:
    """Wrap an LLM call with circuit breaker protection
    
    Args:
        func: Async function to call
        name: Circuit breaker name
        **kwargs: Additional arguments for circuit breaker
        
    Returns:
        Result of the function call
        
    Raises:
        CircuitBreakerError: If circuit is open
        Exception: Original exception if call fails
    """
    breaker_name = name or "llm_call"
    breaker = get_circuit_breaker(breaker_name, **kwargs)

    async with breaker.context():
        return await func()
