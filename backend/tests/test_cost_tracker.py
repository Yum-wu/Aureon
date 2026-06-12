"""Tests for cost tracker."""

import pytest
from app.benchmark.cost_tracker import CostTracker, TokenUsage
from app.benchmark.config import PRICING


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


# ── record_tokens (added in commit 7c48098) ──
# This convenience method is used by the HTTP cost estimator to record
# input/output token pairs without instantiating a TokenUsage manually.


class TestRecordTokens:
    def test_record_tokens_maps_to_llm_field(self):
        """input + output tokens are stored in the llm and total fields."""
        tracker = CostTracker()
        tracker.record_tokens(input_tokens=300, output_tokens=120, model="qwen3.6-flash")
        assert len(tracker.usages) == 1
        usage = tracker.usages[0]
        assert usage.embedding == 0
        assert usage.rerank == 0
        assert usage.llm == 420
        assert usage.total == 420

    def test_record_tokens_default_model_accepted(self):
        """The model kwarg is currently accepted-but-ignored; ensure no error."""
        tracker = CostTracker()
        # The signature accepts a model parameter; we accept any string and
        # simply use the qwen_flash pricing row. This guards against a
        # future change that would break callers passing the default.
        tracker.record_tokens(input_tokens=10, output_tokens=0, model="qwen3.6-flash")
        assert tracker.usages[0].llm == 10

    def test_record_tokens_zero_values(self):
        """Zero input and output should still record a (zero-cost) entry."""
        tracker = CostTracker()
        tracker.record_tokens(input_tokens=0, output_tokens=0)
        assert tracker.usages[0].llm == 0
        assert tracker.usages[0].total == 0

    def test_record_tokens_accumulates_in_summary(self):
        """Multiple record_tokens calls should sum into summary()."""
        tracker = CostTracker()
        tracker.record_tokens(input_tokens=1000, output_tokens=500)  # 1500 llm
        tracker.record_tokens(input_tokens=2000, output_tokens=500)  # 2500 llm
        summary = tracker.summary()
        assert summary["llm_tokens"] == 4000
        assert summary["total_tokens"] == 4000
        assert summary["queries"] == 2


# ── summary() LLM cost (added in commit 7c48098) ──
# The bug-fix commit added llm_cost = total.llm * PRICING["qwen_flash"] / 1000
# to the summary. Existing tests only asserted cost > 0; this asserts the
# exact arithmetic so a future pricing-table change cannot silently break it.


class TestSummaryLLMCost:
    def test_llm_cost_arithmetic_matches_pricing_table(self):
        """llm_cost must equal (llm_tokens * qwen_flash_price) / 1000."""
        tracker = CostTracker()
        tracker.record_tokens(input_tokens=1000, output_tokens=1000)  # 2000 llm tokens
        expected = 2000 * PRICING["qwen_flash"] / 1000
        summary = tracker.summary()
        assert summary["estimated_cost_usd"] == pytest.approx(round(expected, 4))

    def test_summary_separates_llm_tokens(self):
        """summary() must report llm_tokens distinct from embedding/rerank tokens."""
        tracker = CostTracker()
        tracker.record(TokenUsage(embedding=10, rerank=20, llm=30, total=60))
        summary = tracker.summary()
        assert summary["llm_tokens"] == 30
        assert summary["embedding_tokens"] == 10
        assert summary["rerank_tokens"] == 20
        assert summary["total_tokens"] == 60

    def test_summary_cost_per_query_when_multiple_queries(self):
        """cost_per_query_usd = round(total_cost / queries, 6).

        The expected value must be derived from the raw total_cost before
        the summary's 4-decimal rounding of estimated_cost_usd, otherwise
        a re-divided rounded value diverges from the actually stored value.
        """
        tracker = CostTracker()
        tracker.record(TokenUsage(embedding=0, rerank=0, llm=1000, total=1000))
        tracker.record(TokenUsage(embedding=0, rerank=0, llm=1000, total=1000))
        # Total cost is computed in summary() as llm * PRICING / 1000 = 0.00056
        raw_total_cost = 2000 * PRICING["qwen_flash"] / 1000
        summary = tracker.summary()
        assert summary["cost_per_query_usd"] == pytest.approx(round(raw_total_cost / 2, 6))

    def test_summary_aggregates_three_token_kinds(self):
        """All three cost components must be summed into total cost."""
        tracker = CostTracker()
        tracker.record(TokenUsage(embedding=1000, rerank=1000, llm=1000, total=3000))
        summary = tracker.summary()
        expected_total = (
            1000 * PRICING["dashscope_embedding"] / 1000
            + 1000 * PRICING["dashscope_rerank"] / 1000
            + 1000 * PRICING["qwen_flash"] / 1000
        )
        assert summary["estimated_cost_usd"] == pytest.approx(round(expected_total, 4))


# ── reset() ──


class TestReset:
    def test_reset_clears_usages(self):
        tracker = CostTracker()
        tracker.record(TokenUsage(embedding=100, total=100))
        tracker.record_tokens(input_tokens=50)
        assert len(tracker.usages) == 2
        tracker.reset()
        assert tracker.usages == []

    def test_reset_then_summary_returns_zeros(self):
        """After reset, summary must reflect the empty state."""
        tracker = CostTracker()
        tracker.record(TokenUsage(embedding=999, total=999))
        tracker.reset()
        summary = tracker.summary()
        assert summary["total_tokens"] == 0
        assert summary["queries"] == 0
        assert summary["estimated_cost_usd"] == 0
        assert summary["llm_tokens"] == 0
        assert summary["embedding_tokens"] == 0
        assert summary["rerank_tokens"] == 0

    def test_reset_on_empty_tracker_is_idempotent(self):
        tracker = CostTracker()
        tracker.reset()
        tracker.reset()
        assert tracker.usages == []
