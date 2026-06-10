"""Tests for report generator."""

import json
import pytest
from pathlib import Path

from app.benchmark.report_generator import (
    COLORS,
    _check_mark,
    generate_markdown_report,
    generate_terminal_output,
    save_json_report,
)


def test_terminal_output_contains_sections():
    """Test terminal output contains all required sections."""
    results = {
        "metadata": {"mode": "railway", "vector_backend": "qdrant"},
        "quality": {"recall_at_5": 0.96, "mrr": 0.85},
        "latency": {"p50_ms": 18.5, "p99_ms": 125.3},
        "concurrency": [{"level": 100, "qps": 83.5, "success_rate": 0.97}],
        "cost": {"total_tokens": 125000, "estimated_cost_usd": 0.012},
    }

    output = generate_terminal_output(results)
    assert "Retrieval Quality" in output
    assert "Latency" in output
    assert "Concurrency" in output
    assert "Cost Analysis" in output


def test_markdown_report_generation(tmp_path):
    """Test Markdown report file creation."""
    results = {
        "metadata": {"timestamp": "2026-06-10T15:30:00Z", "mode": "railway"},
        "quality": {"recall_at_5": 0.96},
        "latency": {"p50_ms": 18.5},
        "concurrency": [],
        "cost": {"total_tokens": 1000},
    }

    output_file = tmp_path / "test_report.md"
    report = generate_markdown_report(results, str(output_file))

    assert output_file.exists()
    assert "# Railway Benchmark Report" in report
    assert "2026-06-10" in report


# ── _check_mark ascii_safe fallback (added in commit 7c48098) ──
# The bug-fix added an ascii_safe kwarg so that reports rendered on Windows
# GBK terminals (which can't encode ✅ / ❌) don't crash with
# UnicodeEncodeError. This regression test verifies both branches.


class TestCheckMark:
    def test_ascii_safe_pass(self):
        """ascii_safe=True with True value → literal [PASS]."""
        assert _check_mark(True, ascii_safe=True) == "[PASS]"

    def test_ascii_safe_fail(self):
        """ascii_safe=True with False value → literal [FAIL]."""
        assert _check_mark(False, ascii_safe=True) == "[FAIL]"

    def test_unicode_pass(self):
        """ascii_safe=False (default) with True value → green ✅."""
        mark = _check_mark(True, ascii_safe=False)
        assert "✅" in mark
        assert COLORS["green"] in mark

    def test_unicode_fail(self):
        """ascii_safe=False (default) with False value → red ❌."""
        mark = _check_mark(False, ascii_safe=False)
        assert "❌" in mark
        assert COLORS["red"] in mark

    def test_ascii_safe_output_is_gbk_encodable(self):
        """Regression: [PASS]/[FAIL] must be encodable by GBK (Windows default).

        This is the exact path that crashed the original generator with
        UnicodeEncodeError on Windows CN terminals.
        """
        for value in (True, False):
            mark = _check_mark(value, ascii_safe=True)
            mark.encode("gbk")  # would raise UnicodeEncodeError before the fix

    def test_unicode_output_requires_utf8(self):
        """✅/❌ must NOT be encodable in GBK — confirming the failure mode.

        This documents why the fallback exists: the unicode marks are
        fundamentally incompatible with non-UTF-8 Windows code pages.
        """
        mark = _check_mark(True, ascii_safe=False)
        with pytest.raises(UnicodeEncodeError):
            mark.encode("gbk")


# ── generate_terminal_output additional paths ──


class TestGenerateTerminalOutput:
    def test_no_concurrency_section_when_empty(self):
        """When concurrency list is empty, the Concurrency section is omitted.

        Earlier tests always passed a non-empty concurrency list, so this
        branch — the default for sparse benchmark runs — was never exercised.
        """
        results = {
            "metadata": {"mode": "local", "vector_backend": "chroma"},
            "quality": {"recall_at_5": 0.9, "mrr": 0.85, "ndcg_at_10": 0.8},
            "latency": {"p50_ms": 18, "p90_ms": 25, "p99_ms": 100},
            "concurrency": [],
            "cost": {"total_tokens": 0, "estimated_cost_usd": 0},
        }
        output = generate_terminal_output(results)
        assert "Concurrency" not in output
        # Quality/latency/cost sections should still be present
        assert "Retrieval Quality" in output
        assert "Latency" in output
        assert "Cost Analysis" in output

    def test_ascii_safe_flag_disables_unicode_marks(self):
        """ascii_safe=True must replace ✅/❌ globally in the rendered output."""
        results = {
            "metadata": {"mode": "railway"},
            "quality": {"recall_at_5": 0.99, "mrr": 0.9, "ndcg_at_10": 0.9},
            "latency": {"p50_ms": 5, "p99_ms": 10},
            "concurrency": [],
            "cost": {"total_tokens": 0, "estimated_cost_usd": 0},
        }
        output = generate_terminal_output(results, ascii_safe=True)
        assert "✅" not in output
        assert "❌" not in output
        # All four passed metrics should produce [PASS] markers
        assert output.count("[PASS]") >= 4

    def test_ascii_safe_output_is_gbk_safe(self):
        """The full rendered report with ascii_safe=True must round-trip through GBK.

        The original bug was a UnicodeEncodeError raised during *print()* on
        Windows code page 936. This test simulates that constraint.
        """
        results = {
            "metadata": {"mode": "railway"},
            "quality": {"recall_at_5": 0.99, "mrr": 0.9, "ndcg_at_10": 0.9},
            "latency": {"p50_ms": 5, "p99_ms": 10},
            "concurrency": [],
            "cost": {"total_tokens": 0, "estimated_cost_usd": 0},
        }
        output = generate_terminal_output(results, ascii_safe=True)
        # GBK encode must not raise
        output.encode("gbk")

    def test_falls_back_to_last_entry_when_target_level_missing(self):
        """Concurrency section falls back to the last entry if level=100 is absent.

        Guards the `next(..., concurrency[-1])` branch in generate_terminal_output.
        """
        results = {
            "metadata": {"mode": "railway"},
            "quality": {"recall_at_5": 0.9, "mrr": 0.8, "ndcg_at_10": 0.8},
            "latency": {"p50_ms": 5, "p99_ms": 10},
            "concurrency": [{"level": 10, "qps": 80, "success_rate": 0.99,
                             "p99_latency_ms": 200, "avg_latency_ms": 50}],
            "cost": {"total_tokens": 0, "estimated_cost_usd": 0},
        }
        output = generate_terminal_output(results)
        assert "Concurrency" in output
        # Header should reflect the level of the (only, last-resort) entry
        assert "10 concurrent" in output


# ── save_json_report (added in commit 7c48098) ──
# The bug-fix moved JSON/MD serialization to happen before terminal output
# so a crash during printing doesn't lose benchmark results.


class TestSaveJsonReport:
    def test_writes_file_with_pretty_json(self, tmp_path):
        results = {"metric": "ok", "nested": {"k": [1, 2, 3]}}
        out = tmp_path / "report.json"
        save_json_report(results, str(out))
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data == results

    def test_creates_parent_directories(self, tmp_path):
        """save_json_report must mkdir -p for the output path."""
        out = tmp_path / "nested" / "deeper" / "report.json"
        save_json_report({"k": "v"}, str(out))
        assert out.exists()
        assert json.loads(out.read_text(encoding="utf-8")) == {"k": "v"}

    def test_preserves_unicode_characters(self, tmp_path):
        """ensure_ascii=False → Chinese characters stay in the file as-is."""
        out = tmp_path / "report.json"
        save_json_report({"title": "RAG 检索增强生成"}, str(out))
        # The file should contain the Chinese characters directly, not \uXXXX escapes
        text = out.read_text(encoding="utf-8")
        assert "RAG 检索增强生成" in text
        assert "检索" in text

    def test_round_trip_with_full_benchmark_payload(self, tmp_path):
        """A typical benchmark payload should serialize and reload losslessly."""
        payload = {
            "metadata": {"mode": "railway", "vector_backend": "qdrant"},
            "quality": {"recall_at_5": 0.96, "mrr": 0.85, "ndcg_at_10": 0.91},
            "latency": {"p50_ms": 18.5, "p99_ms": 125.3},
            "concurrency": [
                {"level": 100, "qps": 83.5, "success_rate": 0.97}
            ],
            "cost": {"total_tokens": 125000, "estimated_cost_usd": 0.012},
        }
        out = tmp_path / "report.json"
        save_json_report(payload, str(out))
        assert json.loads(out.read_text(encoding="utf-8")) == payload
