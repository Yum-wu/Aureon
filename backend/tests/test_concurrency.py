"""Tests for concurrency test suite."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_calculate_p99():
    """Test P99 latency calculation."""
    from app.benchmark.concurrency_test import ConcurrencyTestSuite

    suite = ConcurrencyTestSuite()
    results = [{"latency_ms": i * 10} for i in range(100)]
    p99 = suite._calculate_p99(results)
    assert p99 == 990.0  # 99th index = 990ms


@pytest.mark.asyncio
async def test_calculate_p99_empty():
    """Test P99 with empty results."""
    from app.benchmark.concurrency_test import ConcurrencyTestSuite

    suite = ConcurrencyTestSuite()
    p99 = suite._calculate_p99([])
    assert p99 == 0.0


@pytest.mark.asyncio
async def test_concurrency_levels():
    """Test that concurrency levels are defined."""
    from app.benchmark.concurrency_test import ConcurrencyTestSuite, CONCURRENCY_LEVELS

    assert 1 in CONCURRENCY_LEVELS
    assert 100 in CONCURRENCY_LEVELS
    assert len(CONCURRENCY_LEVELS) >= 4
