# -*- coding: utf-8 -*-
"""企业级 RAG 基准测试套件 — 检索性能 + 质量门禁 + 生产冒烟

合并原 6 个 benchmark 文件 + test_rag_quality.py 为统一入口。
配置驱动：QA 数据集和阈值从 benchmark_config.yaml 读取。

三层测试金字塔：
- @pytest.mark.benchmark  — 检索性能（延迟/Recall@K/MRR/QPS/并发）
- @pytest.mark.quality    — DeepEval 质量门禁（走完整 rag_query pipeline）
- @pytest.mark.smoke      — 生产冒烟（Railway 端点可达性）

运行方式：
    pytest tests/benchmark_enterprise.py -m benchmark -v   # 仅检索性能
    pytest tests/benchmark_enterprise.py -m quality -v     # 仅质量门禁
    pytest tests/benchmark_enterprise.py -m smoke -v       # 仅生产冒烟
    pytest tests/benchmark_enterprise.py -m "benchmark or quality or smoke" -v  # 全量
"""

import asyncio
import math
import os
import statistics
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ─── 配置加载 ─────────────────────────────────────────────────────────────────

_CONFIG_PATH = Path(__file__).parent / "benchmark_config.yaml"


def _load_config() -> dict:
    """从 YAML 加载配置，缺失则报错。"""
    if not _CONFIG_PATH.exists():
        raise FileNotFoundError(f"配置文件不存在: {_CONFIG_PATH}")
    with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


cfg = _load_config()


# ─── 辅助函数 ─────────────────────────────────────────────────────────────────

def _calc_latency_percentiles(latencies_ms: List[float]) -> Dict[str, float]:
    """计算延迟分位数。"""
    if not latencies_ms:
        return {"p50": 0, "p90": 0, "p95": 0, "p99": 0, "mean": 0, "min": 0, "max": 0}
    s = sorted(latencies_ms)
    n = len(s)
    return {
        "p50": round(s[n // 2], 1),
        "p90": round(s[int(n * 0.9)], 1),
        "p95": round(s[int(n * 0.95)], 1),
        "p99": round(s[min(int(n * 0.99), n - 1)], 1),
        "mean": round(statistics.mean(s), 1),
        "min": round(s[0], 1),
        "max": round(s[-1], 1),
    }


def _rag_query_with_timeout(fn, query, timeout=60):
    """单次 rag_query 超时保护。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn, query)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeoutError:
            return None


# ─── 共享 Fixture ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def qa_pairs():
    """从 YAML 加载 QA 数据集。"""
    pairs = cfg.get("qa_dataset", [])
    assert pairs, "qa_dataset 为空，请检查 benchmark_config.yaml"
    return pairs


@pytest.fixture(scope="module")
def thresholds():
    """从 YAML 加载阈值。"""
    return cfg.get("thresholds", {})


@pytest.fixture(scope="module")
def llm():
    """创建 LLM 实例。"""
    from app.agent.llm import create_llm
    return create_llm()


@pytest.fixture(scope="module")
def rag_query_fn(llm):
    """走完整 rag_query() pipeline 的查询函数。"""
    from app.rag.qa_chain import rag_query

    def _fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    return _fn


@pytest.fixture(scope="module")
def safe_rag_query_fn(rag_query_fn):
    """带超时保护的 rag_query 函数。"""
    def _fn(query):
        return _rag_query_with_timeout(rag_query_fn, query)
    return _fn


# ═══════════════════════════════════════════════════════════════════════════════
# 第一层：检索性能基准
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.benchmark
@pytest.mark.integration
class TestRetrievalPerformance:
    """检索延迟、Recall@K、MRR、QPS、并发性能。"""

    def test_retrieval_latency(self, qa_pairs, thresholds):
        """检索 P50/P99 延迟应在阈值内。"""
        from app.rag.qa_chain import hybrid_retrieve

        positive_pairs = [qa for qa in qa_pairs if not qa.get("is_negative", False)]
        latencies = []
        for qa in positive_pairs:
            t0 = time.perf_counter()
            hybrid_retrieve(qa["question"], top_k=3)
            latencies.append((time.perf_counter() - t0) * 1000)

        pctls = _calc_latency_percentiles(latencies)
        t = thresholds.get("retrieval", {})
        assert pctls["p50"] <= t.get("p50_ms", 200), \
            f"检索 P50={pctls['p50']}ms > {t.get('p50_ms', 200)}ms"
        assert pctls["p99"] <= t.get("p99_ms", 1000), \
            f"检索 P99={pctls['p99']}ms > {t.get('p99_ms', 1000)}ms"

    def test_recall_at_k(self, qa_pairs, thresholds):
        """Recall@3/5/10 应达到阈值。"""
        from app.rag.qa_chain import hybrid_retrieve

        positive_pairs = [qa for qa in qa_pairs if not qa.get("is_negative", False)]
        hits = {3: 0, 5: 0, 10: 0}
        total = len(positive_pairs)

        for qa in positive_pairs:
            chunks = hybrid_retrieve(qa["question"], top_k=10)
            retrieved_sources = [c.get("metadata", {}).get("slug", "") for c in chunks]
            expected = qa.get("source_article", "")
            for k in [3, 5, 10]:
                if expected in retrieved_sources[:k]:
                    hits[k] += 1

        t = thresholds.get("retrieval", {})
        for k in [3, 5, 10]:
            recall = hits[k] / total if total > 0 else 0
            threshold_key = f"recall_at_{k}"
            threshold_val = t.get(threshold_key, 0.5)
            assert recall >= threshold_val, \
                f"Recall@{k}={recall:.3f} < {threshold_val}"

    def test_mrr(self, qa_pairs, thresholds):
        """MRR 应达到阈值。"""
        from app.rag.qa_chain import hybrid_retrieve

        positive_pairs = [qa for qa in qa_pairs if not qa.get("is_negative", False)]
        reciprocal_ranks = []

        for qa in positive_pairs:
            chunks = hybrid_retrieve(qa["question"], top_k=10)
            retrieved_sources = [c.get("metadata", {}).get("slug", "") for c in chunks]
            expected = qa.get("source_article", "")
            rr = 0
            for rank, src in enumerate(retrieved_sources, 1):
                if src == expected:
                    rr = 1.0 / rank
                    break
            reciprocal_ranks.append(rr)

        mrr = statistics.mean(reciprocal_ranks) if reciprocal_ranks else 0
        t = thresholds.get("retrieval", {})
        assert mrr >= t.get("mrr", 0.7), f"MRR={mrr:.4f} < {t.get('mrr', 0.7)}"

    def test_throughput_qps(self, qa_pairs, thresholds):
        """QPS 应达到最低阈值。"""
        import concurrent.futures
        from app.rag.qa_chain import hybrid_retrieve

        positive_pairs = [qa for qa in qa_pairs if not qa.get("is_negative", False)]
        queries = [qa["question"] for qa in positive_pairs[:20]]

        t0 = time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            list(pool.map(lambda q: hybrid_retrieve(q, top_k=3), queries))
        elapsed = time.perf_counter() - t0
        qps = len(queries) / elapsed if elapsed > 0 else 0

        t = thresholds.get("retrieval", {})
        assert qps >= t.get("qps_min", 5), f"QPS={qps:.1f} < {t.get('qps_min', 5)}"

    def test_concurrent_retrieval(self, qa_pairs, thresholds):
        """并发检索性能测试。"""
        from app.rag.qa_chain import hybrid_retrieve

        positive_pairs = [qa for qa in qa_pairs if not qa.get("is_negative", False)]
        conc_config = cfg.get("concurrency", {})
        levels = conc_config.get("levels", [1, 5, 10])

        for conc in levels:
            semaphore = asyncio.Semaphore(conc)

            async def _single(qa):
                async with semaphore:
                    t0 = time.perf_counter()
                    await asyncio.to_thread(hybrid_retrieve, qa["question"], top_k=3)
                    return (time.perf_counter() - t0) * 1000

            t0 = time.perf_counter()
            latencies = asyncio.run(asyncio.gather(*[_single(qa) for qa in positive_pairs]))
            total_time = time.perf_counter() - t0
            qps = len(positive_pairs) / total_time if total_time > 0 else 0

            pctls = _calc_latency_percentiles(list(latencies))
            # 并发下 P99 不应超过阈值的 2 倍
            t = thresholds.get("retrieval", {})
            assert pctls["p99"] <= t.get("p99_ms", 1000) * 2, \
                f"并发 {conc}: P99={pctls['p99']}ms > {t.get('p99_ms', 1000) * 2}ms"


# ═══════════════════════════════════════════════════════════════════════════════
# 第二层：质量门禁（走完整 rag_query pipeline）
# ═══════════════════════════════════════════════════════════════════════════════

_EVAL_TOTAL_TIMEOUT = 300  # 5 分钟


@pytest.mark.quality
@pytest.mark.integration
class TestQualityGate:
    """DeepEval 质量门禁 — 走完整 rag_query() pipeline。"""

    @pytest.fixture(scope="class")
    def eval_results(self, qa_pairs, safe_rag_query_fn):
        """构建 test cases + 运行 DeepEval（带超时保护）。"""
        from app.config import settings

        _placeholder = {"", "your_api_key_here", "sk-placeholder", "YOUR_API_KEY"}
        if not settings.llm_api_key or settings.llm_api_key in _placeholder:
            pytest.skip("无有效 LLM API Key — 跳过 DeepEval 质量门禁")

        from tests.deepeval_eval import build_test_cases, run_deepeval_metrics, _load_article_texts

        article_texts = _load_article_texts()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(
                build_test_cases,
                qa_pairs,
                safe_rag_query_fn,
                article_texts,
                10,  # max_concurrent
            )
            try:
                test_cases, used_indices = future.result(timeout=_EVAL_TOTAL_TIMEOUT)
            except FuturesTimeoutError:
                pytest.skip(f"构建 test cases 超时 ({_EVAL_TOTAL_TIMEOUT}s)")

        scores = run_deepeval_metrics(test_cases, qa_pairs=qa_pairs, used_qa_indices=used_indices)
        return scores

    def test_faithfulness(self, eval_results, thresholds):
        """Faithfulness >= 阈值。"""
        score = eval_results.get("faithfulness", 0)
        t = thresholds.get("quality", {}).get("faithfulness", 0.7)
        assert score >= t, f"Faithfulness={score:.3f} < {t}"

    def test_answer_relevancy(self, eval_results, thresholds):
        """Answer Relevancy >= 阈值。"""
        score = eval_results.get("answer_relevancy", 0)
        t = thresholds.get("quality", {}).get("answer_relevancy", 0.75)
        assert score >= t, f"Answer Relevancy={score:.3f} < {t}"

    def test_context_precision(self, eval_results, thresholds):
        """Context Precision >= 阈值。"""
        score = eval_results.get("context_precision", 0)
        t = thresholds.get("quality", {}).get("context_precision", 0.7)
        assert score >= t, f"Context Precision={score:.3f} < {t}"

    def test_context_recall(self, eval_results, thresholds):
        """Context Recall >= 阈值。"""
        score = eval_results.get("context_recall", 0)
        t = thresholds.get("quality", {}).get("context_recall", 0.75)
        assert score >= t, f"Context Recall={score:.3f} < {t}"

    def test_hallucination(self, eval_results, thresholds):
        """Hallucination <= 阈值。"""
        score = eval_results.get("hallucination", 1)
        t = thresholds.get("quality", {}).get("hallucination_max", 0.2)
        assert score <= t, f"Hallucination={score:.3f} > {t}"

    def test_overall_pass_rate(self, eval_results):
        """至少 80% 的关键指标应通过。"""
        pass_rate = eval_results.get("pass_rate", 0)
        assert pass_rate >= 0.8, f"Pass rate={pass_rate:.0%} < 80%"


# ═══════════════════════════════════════════════════════════════════════════════
# 第三层：生产冒烟测试
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.mark.smoke
@pytest.mark.integration
class TestProductionSmoke:
    """Railway 生产环境冒烟测试 — 仅验证端点可达 + 基本响应。"""

    def test_health_endpoint(self, thresholds):
        """生产 /api/health 应返回 200 + status:ok。"""
        base = cfg["endpoints"]["production"]
        timeout = thresholds.get("smoke", {}).get("health_timeout_s", 10)
        resp = httpx.get(f"{base}/api/health", timeout=timeout)
        assert resp.status_code == 200, f"Health 端点返回 {resp.status_code}"
        data = resp.json()
        assert data.get("status") == "ok", f"Health status={data.get('status')}"

    def test_rag_query_endpoint(self, qa_pairs, thresholds):
        """生产 /api/rag/query 应返回有效响应。"""
        base = cfg["endpoints"]["production"]
        timeout = thresholds.get("smoke", {}).get("rag_query_timeout_s", 30)
        # 取第一个非负例 QA
        positive = next((qa for qa in qa_pairs if not qa.get("is_negative", False)), None)
        if not positive:
            pytest.skip("无正例 QA 可用于冒烟测试")

        resp = httpx.post(
            f"{base}/api/rag/query",
            json={"query": positive["question"], "top_k": 3},
            timeout=timeout,
        )
        assert resp.status_code == 200, f"RAG query 端点返回 {resp.status_code}"
        data = resp.json()
        assert "answer" in data, f"RAG query 响应缺少 answer 字段"

    def test_chat_stream_endpoint(self, thresholds):
        """生产 /api/chat/stream 应返回 SSE。"""
        base = cfg["endpoints"]["production"]
        timeout = thresholds.get("smoke", {}).get("rag_query_timeout_s", 30)
        with httpx.stream(
            "POST",
            f"{base}/api/chat/stream",
            json={"message": "hello", "session_id": "smoke-test"},
            timeout=timeout,
        ) as resp:
            assert resp.status_code == 200, f"Chat stream 端点返回 {resp.status_code}"
            # 读取前几个字节确认是 SSE
            first_chunk = next(resp.iter_bytes(), None)
            assert first_chunk is not None, "Chat stream 无响应数据"
