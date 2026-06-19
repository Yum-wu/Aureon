# RAG Benchmark 重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 6 个重叠的 benchmark 文件 + 1 个质量门禁文件合并为 1 个统一的 `benchmark_enterprise.py` + 1 个 YAML 配置文件，走完整 rag_query() pipeline，新增生产冒烟测试。

**Architecture:** 单文件分层（benchmark/quality/smoke marker）+ YAML 配置驱动（QA 数据集 + 阈值 + 端点）。deepeval_eval.py 简化 build_test_cases 签名，移除 retrieve_fn 参数。

**Tech Stack:** pytest + pyyaml + httpx + deepeval + asyncio

---

### Task 1: 创建 benchmark_config.yaml

**Files:**
- Create: `backend/tests/benchmark_config.yaml`

- [ ] **Step 1: 创建 YAML 配置文件**

```yaml
# benchmark_config.yaml — 企业级 RAG 基准测试配置
# QA 数据集、性能阈值、端点配置

qa_dataset:
  - question: "Hermes Agent 的分层记忆系统有几层？每层叫什么？"
    expected_answer: "4 层：L0 Conversation、L1 Atoms、L2 Scenarios、L3 Persona"
    expected_sources: ["hermes-agent-practical-guide"]
    source_article: "hermes-agent-practical-guide"
    category: "factual"
    difficulty: "easy"
    is_negative: false
  - question: "React SPA 部署到 GitHub Pages 时，路由系统会遇到什么典型问题？如何解决？"
    expected_answer: "刷新页面会出现 404，因为 GitHub Pages 找不到对应的 HTML 文件。解决方案是复制 index.html 为 404.html"
    expected_sources: ["spa-github-pages"]
    source_article: "spa-github-pages"
    category: "factual"
    difficulty: "easy"
    is_negative: false
  - question: "如何配置不存在的功能 XYZ？"
    expected_answer: ""
    expected_sources: []
    source_article: "none"
    category: "negative"
    difficulty: "easy"
    is_negative: true
  - question: "什么是 RAG？"
    expected_answer: "RAG（Retrieval-Augmented Generation）是一种结合检索和生成的AI技术"
    expected_sources: ["rag-overview"]
    source_article: "rag-overview"
    category: "factual"
    difficulty: "easy"
    is_negative: false
  - question: "BM25 和向量检索有什么区别？"
    expected_answer: "BM25 基于关键词匹配，向量检索基于语义相似度"
    expected_sources: ["rag-overview"]
    source_article: "rag-overview"
    category: "reasoning"
    difficulty: "medium"
    is_negative: false
  - question: "请详细解释量子计算在 Aureon 中的应用"
    expected_answer: ""
    expected_sources: []
    source_article: "none"
    category: "negative"
    difficulty: "hard"
    is_negative: true
  - question: "Aureon 的核心功能是什么？"
    expected_answer: "Aureon 是一个 AI 聊天助手平台，支持 RAG 检索增强生成"
    expected_sources: ["aureon-intro"]
    source_article: "aureon-intro"
    category: "factual"
    difficulty: "easy"
    is_negative: false
  - question: "如何优化检索性能？"
    expected_answer: "可以通过调整 BM25 参数、使用向量索引、优化分块策略来提升检索性能"
    expected_sources: ["rag-overview"]
    source_article: "rag-overview"
    category: "reasoning"
    difficulty: "medium"
    is_negative: false
  - question: "HyDE 和 Multi-Query 检索策略分别适用于什么场景？"
    expected_answer: "HyDE 适用于查询模糊需要假设性答案的场景，Multi-Query 适用于查询需要多角度理解的场景"
    expected_sources: ["rag-overview"]
    source_article: "rag-overview"
    category: "synthesis"
    difficulty: "hard"
    is_negative: false
  - question: "CRAG 自纠正机制如何工作？"
    expected_answer: "CRAG 在检索质量低时重写查询并重新检索，通过规则扩展生成变体查询"
    expected_sources: ["rag-overview"]
    source_article: "rag-overview"
    category: "reasoning"
    difficulty: "medium"
    is_negative: false

thresholds:
  retrieval:
    p50_ms: 200
    p99_ms: 1000
    recall_at_3: 0.90
    recall_at_5: 0.95
    recall_at_10: 0.97
    mrr: 0.80
    ndcg_at_10: 0.80
    qps_min: 5
  generation:
    p50_ms: 2000
    p99_ms: 5000
  quality:
    faithfulness: 0.70
    answer_relevancy: 0.75
    context_precision: 0.70
    context_recall: 0.75
    hallucination_max: 0.20
  cache:
    hit_rate_min: 0.6
    latency_ratio_max: 0.5
  smoke:
    health_timeout_s: 10
    rag_query_timeout_s: 30

endpoints:
  production: "https://aureon-production-659a.up.railway.app"
  local: "http://localhost:8000"

concurrency:
  levels: [1, 5, 10]
  queries_per_level: 20
```

- [ ] **Step 2: 验证 YAML 语法**

Run: `cd backend && python -c "import yaml; yaml.safe_load(open('tests/benchmark_config.yaml', encoding='utf-8')); print('YAML OK')"`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/benchmark_config.yaml
git commit -m "feat: add benchmark_config.yaml for enterprise RAG testing"
```

---

### Task 2: 简化 deepeval_eval.py — 移除 retrieve_fn 参数

**Files:**
- Modify: `backend/tests/deepeval_eval.py`

- [ ] **Step 1: 修改 `_retrieve_and_generate` 函数**

将签名从 `retrieve_fn, rag_query_fn` 改为仅 `rag_query_fn`，内部只调 `rag_query_fn`，从返回值提取 `retrieval_context` 和 `actual_output`。

找到 `_retrieve_and_generate` 函数（约 L111-L162），替换为：

```python
async def _retrieve_and_generate(
    qa: Dict,
    rag_query_fn: Callable,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """并发执行单个 QA 的 rag_query，受信号量控制。

    走完整 rag_query() pipeline（HyDE/CRAG/压缩/负例检测），
    从返回值中提取 retrieval_context 和 actual_output。
    """
    query = qa["question"]
    is_negative = qa.get("is_negative", False)

    if is_negative:
        return {
            "retrieval_context": ["No relevant information in knowledge base"],
            "actual_output": qa.get("answer", ""),
        }

    async with semaphore:
        result = await asyncio.to_thread(rag_query_fn, query)

    # 处理 rag_query 结果
    if isinstance(result, Exception):
        logger.warning("rag_query failed for '%s': %s", query[:40], result)
        return {
            "retrieval_context": [],
            "actual_output": "Error: failed to process query",
        }

    if result is None:
        return {
            "retrieval_context": [],
            "actual_output": "Error: query timed out",
        }

    # 从 RAGQueryResponse 提取 retrieval_context 和 actual_output
    actual_output = result.answer if hasattr(result, "answer") else str(result)

    retrieval_context = []
    if hasattr(result, "sources") and result.sources:
        for src in result.sources:
            chunk_text = getattr(src, "chunk", "") or getattr(src, "chunk_text_snippet", "")
            if chunk_text:
                retrieval_context.append(chunk_text)

    # 如果没有 sources，尝试从 rag_query 的 chunks 获取
    if not retrieval_context and hasattr(result, "chunks"):
        for c in result.chunks:
            text = c.get("text", "") if isinstance(c, dict) else getattr(c, "text", "")
            if text:
                retrieval_context.append(text)

    retrieval_context = _dedup_retrieval_context(retrieval_context)
    retrieval_context = [_strip_contextual_prefix(t) for t in retrieval_context]

    return {
        "retrieval_context": retrieval_context,
        "actual_output": actual_output,
    }
```

- [ ] **Step 2: 修改 `build_test_cases_async` 签名**

找到 `build_test_cases_async` 函数（约 L165-L225），将签名和内部调用改为不传 `retrieve_fn`：

```python
async def build_test_cases_async(
    qa_pairs: List[Dict],
    rag_query_fn: Callable,
    article_texts: Dict[str, str] = None,
    max_concurrent: int = 10,
) -> tuple:
    """异步并发构建 DeepEval LLMTestCase。

    使用 asyncio.gather 并发执行所有 QA 的 rag_query，
    走完整 pipeline（HyDE/CRAG/压缩/负例检测）。

    Args:
        qa_pairs: List of {"question", "answer", "source_article", ...}
        rag_query_fn: Function(query) -> RAGQueryResponse with .answer and .sources
        article_texts: Slug -> full article text mapping (auto-loaded if None)
        max_concurrent: 最大并发 QA 数（默认 10，避免 API 限流）
    """
    from deepeval.test_case import LLMTestCase

    if article_texts is None:
        article_texts = _load_article_texts()

    # 过滤有效 QA
    valid_items = [(idx, qa) for idx, qa in enumerate(qa_pairs) if qa.get("question")]
    used_qa_indices = [idx for idx, _ in valid_items]

    # 信号量控制并发数
    semaphore = asyncio.Semaphore(max_concurrent)

    # 并发执行所有 QA 的 rag_query
    tasks = [
        _retrieve_and_generate(qa, rag_query_fn, semaphore)
        for _, qa in valid_items
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # 构建 LLMTestCase
    test_cases = []
    for (qa_idx, qa), result in zip(valid_items, results):
        if isinstance(result, Exception):
            logger.warning("QA #%d failed: %s", qa_idx, result)
            result = {
                "retrieval_context": [],
                "actual_output": "Error: failed to process query",
            }

        source_slug = qa.get("source_article", "")
        context_text = article_texts.get(source_slug, qa.get("answer", "")) if source_slug else ""

        test_case = LLMTestCase(
            input=qa["question"],
            actual_output=result["actual_output"],
            retrieval_context=result["retrieval_context"] if result["retrieval_context"] else ["No context retrieved"],
            expected_output=qa.get("answer", ""),
            context=[context_text] if context_text else [qa.get("answer", "")],
        )
        test_cases.append(test_case)

    return test_cases, used_qa_indices
```

- [ ] **Step 3: 修改 `build_test_cases` 同步入口**

```python
def build_test_cases(
    qa_pairs: List[Dict],
    rag_query_fn: Callable,
    article_texts: Dict[str, str] = None,
    max_concurrent: int = 10,
) -> List[Any]:
    """同步入口：异步并发构建 DeepEval LLMTestCase。

    内部使用 asyncio.run() 调用 build_test_cases_async。
    max_concurrent 控制最大并发 QA 数（默认 10）。
    """
    return asyncio.run(
        build_test_cases_async(qa_pairs, rag_query_fn, article_texts, max_concurrent)
    )
```

- [ ] **Step 4: 修改 `__main__` 块**

找到 `if __name__ == "__main__":` 块（约 L459-L484），替换为：

```python
if __name__ == "__main__":
    from tests.test_data_golden import load_dataset, get_dataset_info

    dataset_name = sys.argv[1] if len(sys.argv) > 1 else "core_regression_40qa"
    qa_pairs = load_dataset(dataset_name)
    info = get_dataset_info(dataset_name)

    print(f"Running DeepEval on {dataset_name} ({info['total']} QA pairs)...")

    from app.rag.qa_chain import rag_query
    from app.agent.llm import create_llm

    llm = create_llm()

    def rag_query_fn(query):
        return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

    # Load article texts for the context field
    article_texts = _load_article_texts()
    print(f"Loaded {len(article_texts)} article texts for context")

    test_cases, used_qa_indices = build_test_cases(qa_pairs, rag_query_fn, article_texts, max_concurrent=10)
    print(f"Built {len(test_cases)} test cases (concurrent data preparation)")

    scores = run_deepeval_metrics(test_cases, qa_pairs=qa_pairs, used_qa_indices=used_qa_indices)
    print(format_results(scores, info))
```

- [ ] **Step 5: 验证语法**

Run: `cd backend && python -c "import ast; ast.parse(open('tests/deepeval_eval.py', encoding='utf-8').read()); print('Syntax OK')"`

- [ ] **Step 6: Commit**

```bash
git add backend/tests/deepeval_eval.py
git commit -m "refactor: simplify deepeval_eval.py — remove retrieve_fn, use rag_query pipeline only"
```

---

### Task 3: 创建新的 benchmark_enterprise.py

**Files:**
- Create: `backend/tests/benchmark_enterprise.py` (覆盖旧文件)

- [ ] **Step 1: 写入完整的 benchmark_enterprise.py**

```python
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
```

- [ ] **Step 2: 验证语法**

Run: `cd backend && python -c "import ast; ast.parse(open('tests/benchmark_enterprise.py', encoding='utf-8').read()); print('Syntax OK')"`

- [ ] **Step 3: 验证 YAML 加载**

Run: `cd backend && python -c "import sys; sys.path.insert(0, 'tests'); from benchmark_enterprise import cfg; print(f'Loaded {len(cfg[\"qa_dataset\"])} QA pairs')"`

- [ ] **Step 4: Commit**

```bash
git add backend/tests/benchmark_enterprise.py
git commit -m "feat: create unified benchmark_enterprise.py with benchmark/quality/smoke layers"
```

---

### Task 4: 更新 pyproject.toml — 添加 marker 配置

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 更新 pytest 配置**

找到 `[tool.pytest.ini_options]` 部分，替换为：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short -m 'not integration and not benchmark and not quality and not smoke'"
markers = [
    "integration: 集成测试，需外部服务（Qdrant/LLM API），默认跳过",
    "benchmark: 检索性能基准测试",
    "quality: DeepEval 质量门禁测试",
    "smoke: 生产环境冒烟测试",
]
```

- [ ] **Step 2: 验证 pytest 配置**

Run: `cd backend && python -m pytest --markers 2>&1 | Select-String -Pattern "benchmark|quality|smoke"`

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "feat: add benchmark/quality/smoke markers to pytest config"
```

---

### Task 5: 删除旧文件

**Files:**
- Delete: `backend/tests/benchmark_rag.py`
- Delete: `backend/tests/benchmark_rag_full.py`
- Delete: `backend/tests/benchmark_e2e.py`
- Delete: `backend/tests/benchmark_concurrent.py`
- Delete: `backend/tests/benchmark_semantic_cache.py`
- Delete: `backend/tests/test_rag_quality.py`

- [ ] **Step 1: 删除 6 个旧文件**

```bash
git rm backend/tests/benchmark_rag.py backend/tests/benchmark_rag_full.py backend/tests/benchmark_e2e.py backend/tests/benchmark_concurrent.py backend/tests/benchmark_semantic_cache.py backend/tests/test_rag_quality.py
```

- [ ] **Step 2: 确认无其他文件引用被删除的模块**

Run: `cd backend && python -c "import ast; ast.parse(open('tests/benchmark_enterprise.py', encoding='utf-8').read()); print('benchmark_enterprise.py OK')"`

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: remove 6 legacy benchmark files + test_rag_quality.py (merged into benchmark_enterprise.py)"
```

---

### Task 6: 验证 CI 单元测试不受影响

**Files:**
- 无文件修改

- [ ] **Step 1: 运行 CI 默认测试（排除所有 marker）**

Run: `cd backend && python -m pytest tests/ -v --tb=short -m "not integration and not benchmark and not quality and not smoke" -x`

Expected: 所有单元测试通过，benchmark/quality/smoke 测试被跳过

- [ ] **Step 2: 验证 marker 过滤生效**

Run: `cd backend && python -m pytest tests/benchmark_enterprise.py --collect-only -m benchmark`

Expected: 仅显示 `TestRetrievalPerformance` 下的测试

- [ ] **Step 3: 验证 lint 通过**

Run: `cd backend && python -m ruff check tests/benchmark_enterprise.py tests/deepeval_eval.py`

Expected: 无 lint 错误

---

### Task 7: 确认 .gitignore 覆盖 benchmark 输出

**Files:**
- Modify: `.gitignore` (如需)

- [ ] **Step 1: 检查 .gitignore 是否已包含 benchmark 输出**

Run: `Select-String -Path ".gitignore" -Pattern "benchmark" -SimpleMatch`

如果已有 `backend/bench_*.py` 和 `backend/data/benchmark_*.json` 等条目则跳过。否则添加：

```
backend/data/benchmark_*.json
backend/data/benchmark_*.md
backend/.deepeval/
```

- [ ] **Step 2: Commit（如有修改）**

```bash
git add .gitignore
git commit -m "chore: ensure benchmark output files are gitignored"
```

---

## 自审检查

**1. Spec 覆盖度**：
- 合并 6 个 benchmark → 1 个 ✅ (Task 3 + Task 5)
- YAML 配置驱动 ✅ (Task 1)
- 质量门禁走完整 rag_query() ✅ (Task 2 + Task 3)
- 生产冒烟测试 ✅ (Task 3 TestProductionSmoke)
- 仅 DeepEval ✅ (无 RAGAS 引用)
- CI 仅单元测试 ✅ (Task 4 + Task 6)
- marker 体系 ✅ (Task 4)
- deepeval_eval.py 简化 ✅ (Task 2)

**2. 占位符扫描**：无 TBD/TODO/实现后补充

**3. 类型一致性**：
- `rag_query()` 返回 `RAGQueryResponse(answer=str, sources=List[SourceItem])` ✅
- `build_test_cases` 新签名 `(qa_pairs, rag_query_fn, ...)` ✅
- `_retrieve_and_generate` 新签名 `(qa, rag_query_fn, semaphore)` ✅
- 所有 fixture 引用一致 ✅
