"""Tests for report generator."""

import pytest
import json
from pathlib import Path
from app.benchmark.report_generator import generate_terminal_output, generate_markdown_report


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
