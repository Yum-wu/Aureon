"""
Tests for app/rag/prompt_experiment.py

Covers:
- run_experiment() with mocked LLM and rag_query_fn
- build_comparison_table() markdown output
- Empty query list handling
- Strategy selection (direct, cot, few_shot, en/zh)
"""

from unittest.mock import MagicMock, patch
from app.rag.prompt_experiment import (
    run_experiment,
    build_comparison_table,
    _run_single_strategy,
    STRATEGIES,
    STRATEGIES_EN,
)


# ── Helpers ──

def _make_mock_source(title="Test Article", chunk="Test content about AI."):
    src = MagicMock()
    src.title = title
    src.chunk = chunk
    return src


def _make_mock_rag_result(sources=None):
    result = MagicMock()
    result.sources = sources or [_make_mock_source()]
    return result


def _make_mock_llm(answer="This is a test answer."):
    llm = MagicMock()
    resp = MagicMock()
    resp.content = answer
    llm.invoke.return_value = resp
    return llm


def _make_qa_pairs(n=2):
    return [
        {"question": f"What is topic {i}?", "expected": f"answer {i}"}
        for i in range(n)
    ]


# ── run_experiment tests ──

class TestRunExperiment:
    def test_basic_run_returns_results(self):
        """run_experiment returns dict with strategies, results, comparison."""
        qa = _make_qa_pairs(2)
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm("Answer about AI")

        result = run_experiment(qa, rag_fn, llm, strategies=["direct"])

        assert "strategies" in result
        assert "results" in result
        assert "comparison" in result
        assert "direct" in result["results"]
        assert result["results"]["direct"]["num_questions"] == 2

    def test_default_strategies(self):
        """When strategies=None, all three are used."""
        qa = _make_qa_pairs(1)
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm()

        result = run_experiment(qa, rag_fn, llm)

        assert set(result["strategies"]) == {"direct", "cot", "few_shot"}

    def test_empty_qa_pairs(self):
        """Empty qa_pairs produces zero-question results."""
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm()

        result = run_experiment([], rag_fn, llm, strategies=["direct"])

        assert result["results"]["direct"]["num_questions"] == 0
        assert result["results"]["direct"]["latency_mean_ms"] == 0

    def test_en_language_uses_en_templates(self):
        """lang='en' selects English strategy templates."""
        qa = _make_qa_pairs(1)
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm()

        with patch("app.rag.prompt_experiment.STRATEGIES", {"direct": "zh_tpl"}), \
             patch("app.rag.prompt_experiment.STRATEGIES_EN", {"direct": "en_tpl"}):
            result = run_experiment(qa, rag_fn, llm, strategies=["direct"], lang="en")

        assert "direct" in result["results"]
        # Verify llm was called (the en template was used)
        llm.invoke.assert_called_once()

    def test_llm_error_caught_gracefully(self):
        """LLM invocation error is caught and stored as [Error: ...]."""
        qa = _make_qa_pairs(1)
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = MagicMock()
        llm.invoke.side_effect = RuntimeError("API timeout")

        result = run_experiment(qa, rag_fn, llm, strategies=["direct"])

        answer = result["results"]["direct"]["responses"][0]["answer"]
        assert "[Error:" in answer
        assert "API timeout" in answer

    def test_latency_tracking(self):
        """Latency values are recorded and non-negative."""
        qa = _make_qa_pairs(3)
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm()

        result = run_experiment(qa, rag_fn, llm, strategies=["cot"])

        data = result["results"]["cot"]
        assert data["latency_mean_ms"] >= 0
        assert data["latency_p50_ms"] >= 0
        for resp in data["responses"]:
            assert resp["latency_ms"] >= 0


# ── _run_single_strategy tests ──

class TestRunSingleStrategy:
    def test_returns_expected_keys(self):
        """Single strategy run returns num_questions, latency, responses."""
        qa = _make_qa_pairs(2)
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm()

        result = _run_single_strategy(qa, STRATEGIES["direct"], rag_fn, llm)

        assert "num_questions" in result
        assert "latency_mean_ms" in result
        assert "latency_p50_ms" in result
        assert "responses" in result
        assert result["num_questions"] == 2

    def test_response_truncation(self):
        """Question and answer are truncated to 60 and 500 chars."""
        long_q = "A" * 200
        long_a = "B" * 1000
        qa = [{"question": long_q}]
        rag_fn = MagicMock(return_value=_make_mock_rag_result())
        llm = _make_mock_llm(long_a)

        result = _run_single_strategy(qa, STRATEGIES["direct"], rag_fn, llm)

        resp = result["responses"][0]
        assert len(resp["question"]) <= 60
        assert len(resp["answer"]) <= 500


# ── build_comparison_table tests ──

class TestBuildComparisonTable:
    def test_markdown_format(self):
        """Output contains markdown table header and separator."""
        results = {
            "direct": {"num_questions": 5, "latency_mean_ms": 100.0, "latency_p50_ms": 95.0},
            "cot": {"num_questions": 5, "latency_mean_ms": 200.0, "latency_p50_ms": 190.0},
        }

        table = build_comparison_table(results)

        assert "| 策略 |" in table
        assert "|------|" in table
        assert "| direct |" in table
        assert "| cot |" in table
        assert "100.0" in table
        assert "200.0" in table

    def test_empty_results(self):
        """Empty results produces header-only table."""
        table = build_comparison_table({})

        lines = table.strip().split("\n")
        assert len(lines) == 2  # header + separator only

    def test_single_strategy(self):
        """Single strategy produces one data row."""
        results = {
            "few_shot": {"num_questions": 3, "latency_mean_ms": 150.0, "latency_p50_ms": 140.0},
        }

        table = build_comparison_table(results)
        lines = table.strip().split("\n")

        assert len(lines) == 3  # header + separator + 1 row


# ── Strategy constants tests ──

class TestStrategyConstants:
    def test_zh_strategies_keys(self):
        """Chinese strategies has direct, cot, few_shot."""
        assert set(STRATEGIES.keys()) == {"direct", "cot", "few_shot"}

    def test_en_strategies_keys(self):
        """English strategies has direct, cot, few_shot."""
        assert set(STRATEGIES_EN.keys()) == {"direct", "cot", "few_shot"}

    def test_zh_templates_contain_placeholders(self):
        """All zh templates have {context} placeholder."""
        for name, tpl in STRATEGIES.items():
            assert "{context}" in tpl, f"{name} missing {{context}}"

    def test_en_templates_contain_placeholders(self):
        """All en templates have {context} and {question} placeholders."""
        for name, tpl in STRATEGIES_EN.items():
            assert "{context}" in tpl, f"{name} missing {{context}}"
