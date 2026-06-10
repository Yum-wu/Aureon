"""Tests for cost tracker."""

import pytest
from app.benchmark.cost_tracker import CostTracker, TokenUsage


def test_record_usage():
    """Test recording token usage."""
    tracker = CostTracker()
    usage = TokenUsage(embedding=1000, rerank=500, llm=200, total=1700)
    tracker.record(usage)
    assert len(tracker.usages) == 1


def test_summary_calculation():
    """Test cost summary calculation."""
    tracker = CostTracker()
    tracker.record(TokenUsage(embedding=10000, rerank=5000, llm=2000, total=17000))
    tracker.record(TokenUsage(embedding=10000, rerank=5000, llm=2000, total=17000))

    summary = tracker.summary()
    assert summary["total_tokens"] == 34000
    assert summary["queries"] == 2
    assert summary["avg_tokens_per_query"] == 17000
    assert summary["estimated_cost_usd"] > 0


def test_empty_tracker():
    """Test empty tracker returns zeros."""
    tracker = CostTracker()
    summary = tracker.summary()
    assert summary["total_tokens"] == 0
    assert summary["queries"] == 0
    assert summary["estimated_cost_usd"] == 0
