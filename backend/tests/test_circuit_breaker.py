# -*- coding: utf-8 -*-
"""Circuit breaker pattern tests"""

import pytest
from app.reliability.circuit_breaker import (
    CircuitState,
    CircuitBreaker,
    CircuitBreakerError,
    circuit_breaker,
    get_circuit_breaker,
    get_all_circuit_breakers,
    reset_all_circuit_breakers,
    create_llm_circuit_breaker,
    wrap_llm_call,
)


@pytest.fixture
def breaker():
    """Create circuit breaker for testing"""
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=5,
        name="test_breaker",
        success_threshold=1,
    )


@pytest.mark.asyncio
async def test_circuit_breaker_closed_state(breaker):
    """Test circuit breaker closed state (normal operation)"""
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_open_after_failures(breaker):
    """Test circuit breaker opens after consecutive failures"""
    # Trigger consecutive failures
    for _ in range(3):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("test error")

    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_fast_fail_when_open(breaker):
    """Test circuit breaker fast fails when open"""
    # Open the circuit breaker
    for _ in range(3):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("test error")

    # Should fast fail when circuit is open
    with pytest.raises(CircuitBreakerError):
        async with breaker.context():
            pass  # Should not reach here


@pytest.mark.asyncio
async def test_circuit_breaker_half_open_after_timeout(breaker):
    """Test circuit breaker enters half-open after timeout"""
    # Open the circuit breaker
    for _ in range(3):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("test error")

    # Simulate timeout
    breaker._last_failure_time = breaker._last_failure_time - breaker.recovery_timeout - 1

    # _check_timeout() transitions OPEN → HALF_OPEN
    breaker._check_timeout()
    assert breaker.state == CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_circuit_breaker_recovery(breaker):
    """Test circuit breaker recovery"""
    # Open the circuit breaker
    for _ in range(3):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("test error")

    # Simulate timeout
    breaker._last_failure_time = breaker._last_failure_time - breaker.recovery_timeout - 1

    # Successful call should close the breaker
    async with breaker.context():
        pass  # Success

    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_circuit_breaker_decorator():
    """Test circuit breaker decorator"""
    call_count = 0

    @circuit_breaker(failure_threshold=2, recovery_timeout=5)
    async def unstable_function():
        nonlocal call_count
        call_count += 1
        if call_count <= 2:
            raise RuntimeError("service unavailable")
        return "success"

    # First two calls fail
    with pytest.raises(RuntimeError):
        await unstable_function()
    with pytest.raises(RuntimeError):
        await unstable_function()

    # Third call should be rejected by circuit breaker
    with pytest.raises(CircuitBreakerError):
        await unstable_function()


@pytest.mark.asyncio
async def test_get_circuit_breaker():
    """Test getting circuit breaker instance"""
    # Reset all circuit breakers
    reset_all_circuit_breakers()

    # Get circuit breaker
    breaker1 = get_circuit_breaker("test_service")
    breaker2 = get_circuit_breaker("test_service")

    # Should return the same instance
    assert breaker1 is breaker2
    assert breaker1.name == "test_service"


@pytest.mark.asyncio
async def test_get_all_circuit_breakers():
    """Test getting all circuit breakers"""
    # Reset all circuit breakers
    reset_all_circuit_breakers()

    # Create some circuit breakers
    get_circuit_breaker("service_a")
    get_circuit_breaker("service_b")
    get_circuit_breaker("service_c")

    # Get all circuit breakers
    all_breakers = get_all_circuit_breakers()

    assert len(all_breakers) >= 3
    assert "service_a" in all_breakers
    assert "service_b" in all_breakers
    assert "service_c" in all_breakers


@pytest.mark.asyncio
async def test_reset_all_circuit_breakers():
    """Test resetting all circuit breakers"""
    # Create some circuit breakers and trigger failures
    breaker1 = get_circuit_breaker("reset_test_1")
    breaker2 = get_circuit_breaker("reset_test_2")

    # Trigger failures
    for _ in range(3):
        with pytest.raises(ValueError):
            async with breaker1.context():
                raise ValueError("error")

    for _ in range(3):
        with pytest.raises(ValueError):
            async with breaker2.context():
                raise ValueError("error")

    # Reset all circuit breakers
    reset_all_circuit_breakers()

    # Verify reset
    new_breaker1 = get_circuit_breaker("reset_test_1")
    new_breaker2 = get_circuit_breaker("reset_test_2")

    assert new_breaker1.state == CircuitState.CLOSED
    assert new_breaker2.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_wrap_llm_call():
    """Test wrapping LLM calls"""
    # Reset circuit breakers to avoid conflicts
    reset_all_circuit_breakers()
    
    call_count = 0

    async def mock_llm_call():
        nonlocal call_count
        call_count += 1
        if call_count <= 5:
            raise ConnectionError("API timeout")
        return {"response": "success"}

    # First 5 calls fail (default threshold)
    for i in range(5):
        with pytest.raises(ConnectionError):
            await wrap_llm_call(mock_llm_call, name="test_llm_wrap")

    # 6th call should be rejected by circuit breaker
    with pytest.raises(CircuitBreakerError):
        await wrap_llm_call(mock_llm_call, name="test_llm_wrap")
    
    # Cleanup
    reset_all_circuit_breakers()


@pytest.mark.asyncio
async def test_create_llm_circuit_breaker():
    """Test creating custom LLM circuit breaker"""
    custom_breaker = create_llm_circuit_breaker(
        name="custom_llm",
        failure_threshold=10,
        recovery_timeout=120,
    )

    assert custom_breaker.name == "custom_llm"
    assert custom_breaker.failure_threshold == 10
    assert custom_breaker.recovery_timeout == 120


@pytest.mark.asyncio
async def test_circuit_breaker_metrics(breaker):
    """Test circuit breaker metrics"""
    # Trigger some calls
    for _ in range(2):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("error")

    # Successful call
    async with breaker.context():
        pass

    # Check metrics
    metrics = breaker.metrics
    assert metrics["total_calls"] == 3
    assert metrics["total_failures"] == 2
    assert metrics["total_successes"] == 1
    assert metrics["consecutive_failures"] == 0  # Reset after success
    assert metrics["success_threshold"] == 1
    assert metrics["half_open_success_count"] == 0


@pytest.mark.asyncio
async def test_half_open_needs_multiple_successes():
    """Test HALF_OPEN requires success_threshold consecutive successes to close."""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=1,
        name="multi_success_test",
        success_threshold=3,
    )

    # Open the breaker
    for _ in range(2):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("fail")

    assert breaker.state == CircuitState.OPEN

    # Simulate timeout
    breaker._last_failure_time -= 2

    # First success in HALF_OPEN — should NOT close yet
    async with breaker.context():
        pass
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker._half_open_success_count == 1

    # Second success — still not enough
    async with breaker.context():
        pass
    assert breaker.state == CircuitState.HALF_OPEN
    assert breaker._half_open_success_count == 2

    # Third success — now it should close
    async with breaker.context():
        pass
    assert breaker.state == CircuitState.CLOSED
    assert breaker.failure_count == 0


@pytest.mark.asyncio
async def test_half_open_failure_resets_counter():
    """Test HALF_OPEN failure resets counter and returns to OPEN."""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=1,
        name="half_open_fail_test",
        success_threshold=3,
    )

    # Open the breaker
    for _ in range(2):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("fail")

    # Simulate timeout
    breaker._last_failure_time -= 2

    # First success — counter increments
    async with breaker.context():
        pass
    assert breaker._half_open_success_count == 1

    # Failure — counter resets, back to OPEN
    with pytest.raises(ValueError):
        async with breaker.context():
            raise ValueError("fail again")

    assert breaker.state == CircuitState.OPEN
    assert breaker._half_open_success_count == 0


@pytest.mark.asyncio
async def test_pure_state_property():
    """Test state property is a pure read with no side effects."""
    breaker = CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=5,
        name="pure_state_test",
    )

    # Open the breaker
    for _ in range(2):
        with pytest.raises(ValueError):
            async with breaker.context():
                raise ValueError("fail")

    # Simulate timeout — but reading state should NOT transition
    breaker._last_failure_time -= 10
    _ = breaker.state
    assert breaker._state == CircuitState.OPEN  # Still OPEN, no side effect

    # Explicit _check_timeout() is required to transition
    breaker._check_timeout()
    assert breaker.state == CircuitState.HALF_OPEN
