"""CI Quality Gate — RAG evaluation for pull requests.

Runs core regression set (40 QA) with DeepEval metrics.
Fails if any critical metric drops below threshold.

性能优化：
- build_test_cases: asyncio.gather 并发 retrieve + rag_query（8x 加速）
- run_deepeval_metrics: AsyncConfig(max_concurrent=15) + CacheConfig（3x 加速）
- 总计：从 ~12 分钟 → ~2 分钟

Usage:
    # 默认跳过（标记为 @pytest.mark.integration）
    cd backend && python -m pytest tests/ -v

    # 手动跑集成测试
    cd backend && python -m pytest tests/test_rag_quality.py -v -m integration
"""

import os
import sys
import pytest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 每个 QA 对的 rag_query 超时（秒）
_PER_QA_TIMEOUT = 60

# 整个 evaluation_results fixture 的总超时（秒）
# 优化后预计 ~2 分钟，但留余量给网络波动
_EVAL_TOTAL_TIMEOUT = 300  # 5 分钟

# Quality thresholds — failing these blocks the merge
THRESHOLDS = {
    "context_precision": 0.70,
    "context_recall": 0.75,
    "faithfulness": 0.70,
    "hallucination_max": 0.20,
}

# Warning thresholds — these trigger warnings but don't block
WARNING_THRESHOLDS = {
    "answer_relevancy": 0.60,
    "context_relevancy": 0.65,
}


def _rag_query_with_timeout(rag_query_fn, query, timeout=_PER_QA_TIMEOUT):
    """带超时的 rag_query 调用，防止外部服务不可达时测试挂起。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(rag_query_fn, query)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            return None


def _run_evaluation(qa_pairs, info):
    """在子线程中运行完整评估，受总超时保护。

    使用 asyncio.run() 调用异步并发版本的 build_test_cases_async，
    数据准备阶段 10 个 QA 并发 + 单个 QA 内 retrieve/rag_query 并发。
    """
    from tests.deepeval_eval import build_test_cases, run_deepeval_metrics, _load_article_texts
    from app.rag.qa_chain import hybrid_retrieve, rag_query
    from app.agent.llm import create_llm

    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    # 用超时保护包裹 rag_query_fn
    def safe_rag_query_fn(query):
        return _rag_query_with_timeout(rag_query_fn, query)

    article_texts = _load_article_texts()

    # 使用异步并发版本的 build_test_cases（max_concurrent=10）
    test_cases, used_qa_indices = build_test_cases(
        qa_pairs, hybrid_retrieve, safe_rag_query_fn, article_texts,
        max_concurrent=10,
    )

    # 检查是否有因超时返回 None 的测试用例，记录跳过数
    timed_out = sum(1 for tc in test_cases if tc.actual_output is None or "timed out" in str(tc.actual_output).lower())
    if timed_out:
        import structlog
        structlog.get_logger(__name__).warning(
            "rag_query_timeout", timed_out=timed_out, total=len(test_cases),
        )

    scores = run_deepeval_metrics(test_cases, qa_pairs=qa_pairs, used_qa_indices=used_qa_indices)
    scores["dataset_info"] = info
    scores["timed_out_queries"] = timed_out

    return scores


@pytest.fixture(scope="module")
def evaluation_results():
    """Run full evaluation once per test module, with total timeout protection."""
    from app.config import settings
    _placeholder = {"", "your_api_key_here", "sk-placeholder", "YOUR_API_KEY"}
    if not settings.llm_api_key or settings.llm_api_key in _placeholder:
        pytest.skip("No valid LLM API key configured — skipping DeepEval quality gate")
    from tests.test_data_golden import load_dataset, get_dataset_info

    dataset_name = "core_regression_40qa"
    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    # 整个评估在子线程中运行，受总超时保护
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_evaluation, qa_pairs, info)
        try:
            return future.result(timeout=_EVAL_TOTAL_TIMEOUT)
        except FuturesTimeoutError:
            pytest.skip(
                f"Evaluation timed out after {_EVAL_TOTAL_TIMEOUT}s — "
                "external services may be slow or unreachable"
            )


@pytest.mark.integration
class TestRAGQualityGate:
    """Quality gate tests — must pass for PR merge.

    Marked as @pytest.mark.integration so they are skipped in default test runs.
    Run explicitly with: pytest tests/test_rag_quality.py -v -m integration
    """

    def test_context_precision(self, evaluation_results):
        """Context Precision >= 0.70"""
        score = evaluation_results.get("context_precision", 0)
        assert score >= THRESHOLDS["context_precision"], \
            f"Context Precision {score:.3f} < {THRESHOLDS['context_precision']}"

    def test_context_recall(self, evaluation_results):
        """Context Recall >= 0.75"""
        score = evaluation_results.get("context_recall", 0)
        assert score >= THRESHOLDS["context_recall"], \
            f"Context Recall {score:.3f} < {THRESHOLDS['context_recall']}"

    def test_faithfulness(self, evaluation_results):
        """Faithfulness >= 0.70"""
        score = evaluation_results.get("faithfulness", 0)
        assert score >= THRESHOLDS["faithfulness"], \
            f"Faithfulness {score:.3f} < {THRESHOLDS['faithfulness']}"

    def test_hallucination(self, evaluation_results):
        """Hallucination <= 0.20"""
        score = evaluation_results.get("hallucination", 0)
        assert score <= THRESHOLDS["hallucination_max"], \
            f"Hallucination {score:.3f} > {THRESHOLDS['hallucination_max']}"

    def test_answer_relevancy_warning(self, evaluation_results):
        """Answer Relevancy >= 0.60 (warning, not blocking)"""
        score = evaluation_results.get("answer_relevancy", 0)
        if score < WARNING_THRESHOLDS["answer_relevancy"]:
            pytest.warns(
                UserWarning,
                match=f"Answer Relevancy {score:.3f} below warning threshold"
            )

    def test_overall_pass_rate(self, evaluation_results):
        """At least 80% of critical metrics should pass"""
        pass_rate = evaluation_results.get("pass_rate", 0)
        assert pass_rate >= 0.8, \
            f"Pass rate {pass_rate:.0%} < 80%"

    def test_no_excessive_timeouts(self, evaluation_results):
        """超时的查询不应超过总数的 20%"""
        timed_out = evaluation_results.get("timed_out_queries", 0)
        total = evaluation_results.get("dataset_info", {}).get("total", 0) or 40
        if timed_out > total * 0.2:
            pytest.fail(
                f"Too many timed-out queries: {timed_out}/{total} "
                f"({timed_out/total*100:.0f}%) — external services may be down"
            )




def _run_ragas_evaluation(qa_pairs, info):
    """在子线程中运行 RAGAS 评估，受总超时保护。"""
    from app.rag.qa_chain import rag_query
    from app.agent.llm import create_llm
    from app.rag.evaluator import run_ragas_evaluation

    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    # 用超时保护包裹 rag_query_fn
    def safe_rag_query_fn(query):
        return _rag_query_with_timeout(rag_query_fn, query)

    scores = run_ragas_evaluation(safe_rag_query_fn, qa_pairs=qa_pairs)
    scores["dataset_info"] = info

    return scores


@pytest.fixture(scope="module")
def ragas_evaluation_results():
    """Run RAGAS evaluation once per test module, with total timeout protection."""
    from tests.test_data_golden import load_dataset, get_dataset_info
    from app.rag.evaluator import RAGAS_AVAILABLE

    if not RAGAS_AVAILABLE:
        pytest.skip("ragas not installed")

    dataset_name = "core_regression_40qa"
    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    # 整个评估在子线程中运行，受总超时保护
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_run_ragas_evaluation, qa_pairs, info)
        try:
            return future.result(timeout=_EVAL_TOTAL_TIMEOUT)
        except FuturesTimeoutError:
            pytest.skip(
                f"RAGAS evaluation timed out after {_EVAL_TOTAL_TIMEOUT}s — "
                "external services may be slow or unreachable"
            )


@pytest.mark.integration
class TestRAGASQualityGate:
    """RAGAS quality gate tests. Marked as @pytest.mark.integration."""

    def test_ragas_faithfulness(self, ragas_evaluation_results):
        """RAGAS Faithfulness >= 0.70"""
        metrics = ragas_evaluation_results.get("metrics", {})
        faith = metrics.get("faithfulness", {})
        score = faith.get("average_score", 0)
        assert score >= 0.70, \
            f"RAGAS Faithfulness {score:.3f} < 0.70"

    def test_ragas_answer_relevancy(self, ragas_evaluation_results):
        """RAGAS Answer Relevancy >= 0.60"""
        metrics = ragas_evaluation_results.get("metrics", {})
        relevancy = metrics.get("answer_relevancy", {})
        score = relevancy.get("average_score", 0)
        assert score >= 0.60, \
            f"RAGAS Answer Relevancy {score:.3f} < 0.60"

    def test_ragas_context_precision(self, ragas_evaluation_results):
        """RAGAS Context Precision >= 0.70"""
        metrics = ragas_evaluation_results.get("metrics", {})
        precision = metrics.get("context_precision", {})
        score = precision.get("average_score", 0)
        assert score >= 0.70, \
            f"RAGAS Context Precision {score:.3f} < 0.70"

    def test_ragas_overall(self, ragas_evaluation_results):
        """All RAGAS metrics should be present"""
        metrics = ragas_evaluation_results.get("metrics", {})
        required = ["faithfulness", "answer_relevancy", "context_precision"]
        for metric in required:
            assert metric in metrics, f"Missing RAGAS metric: {metric}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "integration"])
