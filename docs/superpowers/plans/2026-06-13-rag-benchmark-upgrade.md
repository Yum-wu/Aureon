# RAG Benchmark 升级实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [`) syntax for tracking.

**Goal:** 将 Railway benchmark 升级为完整的 6 维企业级评估体系，覆盖检索质量、生成质量、延迟性能、吞吐可用性、成本效率、用户体验

**Architecture:** 在现有 `run_benchmark.py` Railway 模式基础上，新增 TTFT/TPOT 流式延迟测量、Answer Relevancy 生成质量评估、Cache Hit Rate 统计，并升级 `report_generator.py` 展示完整 6 维指标

**Tech Stack:** Python, httpx (SSE), RAGAS (可选), LangFuse (已有)

---

## File Structure

| 文件 | 操作 | 职责 |
|------|------|------|
| `backend/tests/run_benchmark.py` | Modify | 新增 Phase 1b（流式延迟）、Phase 4（生成质量） |
| `backend/app/benchmark/report_generator.py` | Modify | 升级报告为 6 维指标体系 |
| `backend/app/benchmark/config.py` | Modify | 新增阈值常量 |
| `backend/app/benchmark/cost_tracker.py` | Modify | 新增 TPOT 计算 |

---

## Task 1: 新增 TTFT + TPOT 流式延迟测量

**Files:**
- Modify: `backend/tests/run_benchmark.py:301-430`

在 Phase 1 质量评估中，对每个查询额外调用 `/api/rag/query/stream`（SSE 端点），测量 TTFT 和 TPOT。

- [ ] **Step 1: 在 Phase 1 循环中新增流式延迟测量**

在 `run_railway_benchmark()` 的 Phase 1 循环中，对每个成功查询额外调用流式端点：

```python
# Phase 1b: 流式延迟测量（TTFT + TPOT）
ttft_ms = 0
tpot_ms = 0
output_tokens = 0

try:
    stream_start = time.perf_counter()
    async with client._client.stream(
        "POST",
        f"{client.base_url}/api/rag/query/stream",
        json={"query": query, "top_k": 3},
        headers=client.headers,
        timeout=60,
    ) as stream_resp:
        first_token_time = None
        last_token_time = None
        token_count = 0
        async for line in stream_resp.aiter_lines():
            if line.startswith("data: "):
                if first_token_time is None:
                    first_token_time = time.perf_counter()
                    ttft_ms = (first_token_time - stream_start) * 1000
                last_token_time = time.perf_counter()
                token_count += 1

        if first_token_time and last_token_time and token_count > 1:
            tpot_ms = ((last_token_time - first_token_time) / token_count) * 1000
            output_tokens = token_count
except Exception:
    pass  # 流式测量失败不影响主流程
```

- [ ] **Step 2: 收集流式延迟数据**

在 Phase 1 循环中新增列表：
```python
ttft_list = []
tpot_list = []
```

每次成功查询后追加：
```python
if ttft_ms > 0:
    ttft_list.append(ttft_ms)
if tpot_ms > 0:
    tpot_list.append(tpot_ms)
```

- [ ] **Step 3: 在 Phase 2 中合并流式延迟统计**

```python
# Phase 2: Latency Distribution (包含 TTFT/TPOT)
if ttft_list:
    ttft_sorted = sorted(ttft_list)
    latency_results["ttft"] = {
        "mean_ms": round(statistics.mean(ttft_sorted), 1),
        "p50_ms": round(ttft_sorted[len(ttft_sorted) // 2], 1),
        "p90_ms": round(ttft_sorted[int(len(ttft_sorted) * 0.9)], 1),
        "p99_ms": round(ttft_sorted[min(int(len(ttft_sorted) * 0.99), len(ttft_sorted) - 1)], 1),
        "samples": len(ttft_sorted),
    }

if tpot_list:
    tpot_sorted = sorted(tpot_list)
    latency_results["tpot"] = {
        "mean_ms": round(statistics.mean(tpot_sorted), 1),
        "p50_ms": round(tpot_sorted[len(tpot_sorted) // 2], 1),
        "samples": len(tpot_sorted),
    }
```

- [ ] **Step 4: 终端输出新增 TTFT/TPOT**

```python
if "ttft" in latency_results:
    print(f"  TTFT P50:    {latency_results['ttft']['p50_ms']}ms")
    print(f"  TTFT P90:    {latency_results['ttft']['p90_ms']}ms")
if "tpot" in latency_results:
    print(f"  TPOT mean:   {latency_results['tpot']['mean_ms']}ms/token")
```

- [ ] **Step 5: 运行测试验证**

```bash
cd backend && python -m pytest tests/test_rag_stats_extended.py -v --tb=short
```

---

## Task 2: 新增 Answer Relevancy 生成质量评估

**Files:**
- Modify: `backend/tests/run_benchmark.py:440-458`

在 Phase 1 质量评估中，对有答案的查询用 LLM-as-Judge 快速评估 Answer Relevancy。

- [ ] **Step 1: 新增 Answer Relevancy 评估函数**

```python
async def _evaluate_answer_relevancy(query: str, answer: str, client) -> float:
    """LLM-as-Judge: 评估答案是否切题（0-1 分）。"""
    if not answer or len(answer) < 10:
        return 0.0
    try:
        resp = await client._client.post(
            f"{client.base_url}/api/rag/query",
            json={
                "query": f"请评估以下回答是否切题。查询: {query[:100]} 回答: {answer[:200]} 只回答YES或NO",
                "top_k": 1,
            },
            headers=client.headers,
            timeout=30,
        )
        if resp.status_code == 200:
            result = resp.json().get("answer", "").upper()
            return 1.0 if "YES" in result else 0.0
    except Exception:
        pass
    return 0.5  # 默认中性分数
```

- [ ] **Step 2: 在 Phase 1 循环中调用评估**

对每个有答案的正例查询，异步评估 Answer Relevancy（采样 20% 以控制成本）：

```python
relevancy_scores = []
# 在 Phase 1 循环中：
if answer and not is_negative and i % 5 == 0:  # 采样 20%
    relevancy = await _evaluate_answer_relevancy(query, answer, client)
    relevancy_scores.append(relevancy)
```

- [ ] **Step 3: 在 quality_results 中新增指标**

```python
quality_results["answer_relevancy"] = (
    statistics.mean(relevancy_scores) if relevancy_scores else 0.0
)
quality_results["answer_relevancy_samples"] = len(relevancy_scores)
```

---

## Task 3: 升级报告生成器为 6 维指标体系

**Files:**
- Modify: `backend/app/benchmark/report_generator.py`

- [ ] **Step 1: 升级 `generate_terminal_output()`**

新增生成质量、TTFT/TPOT、缓存命中率的终端输出：

```python
# 生成质量
answer_rel = quality.get("answer_relevancy", 0)
if answer_rel > 0:
    lines.append(_colorize("> Generation Quality", "cyan"))
    lines.append(f"  Answer Relevancy: {answer_rel:.3f}  {_cm(answer_rel >= 0.75)} (target: ≥0.75)")
    lines.append(f"  Neg Detection:    {quality.get('negative_detection_rate', 0)*100:.1f}%  "
                 f"{_cm(quality.get('negative_detection_rate', 0) >= 0.80)} (target: ≥80%)")
    lines.append("")

# TTFT / TPOT
ttft = latency.get("ttft", {})
tpot = latency.get("tpot", {})
if ttft:
    lines.append(_colorize("> Streaming Latency", "cyan"))
    p50_ttft = ttft.get("p50_ms", 0)
    lines.append(f"  TTFT P50:      {p50_ttft:.0f}ms  {_cm(p50_ttft <= 2000)} (target: ≤2s)")
    p90_ttft = ttft.get("p90_ms", 0)
    lines.append(f"  TTFT P90:      {p90_ttft:.0f}ms")
    if tpot:
        mean_tpot = tpot.get("mean_ms", 0)
        lines.append(f"  TPOT mean:     {mean_tpot:.0f}ms/token  {_cm(mean_tpot <= 100)} (target: ≤100ms)")
    lines.append("")

# 缓存命中率
cache = results.get("cache", {})
if cache:
    hit_rate = cache.get("hit_rate", 0)
    lines.append(_colorize("> Cache Efficiency", "cyan"))
    lines.append(f"  Hit Rate:      {hit_rate*100:.1f}%  {_cm(hit_rate >= 0.30)} (target: ≥30%)")
    lines.append("")
```

- [ ] **Step 2: 升级 `generate_markdown_report()`**

在 Markdown 报告的 Summary 表中新增所有指标：

```markdown
## Summary

### Retrieval Quality
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Recall@5 | {recall_5:.1%} | ≥95% | ✅/❌ |
| MRR | {mrr:.3f} | ≥0.80 | ✅/❌ |
| nDCG@10 | {ndcg:.3f} | ≥0.80 | ✅/❌ |
| Negative Detection | {neg_rate:.1%} | ≥80% | ✅/❌ |

### Generation Quality
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| Answer Relevancy | {answer_rel:.3f} | ≥0.75 | ✅/❌ |

### Latency
| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| E2E P50 | {p50:.0f}ms | ≤5s | ✅/❌ |
| E2E P99 | {p99:.0f}ms | ≤15s | ✅/❌ |
| TTFT P50 | {ttft_p50:.0f}ms | ≤2s | ✅/❌ |
| TPOT mean | {tpot_mean:.0f}ms/tok | ≤100ms | ✅/❌ |

### Cost
| Metric | Value |
|--------|-------|
| Cost/Query | ${cost_per_query:.6f} |
| Total Tokens | {total_tokens:,} |
```

---

## Task 4: 更新配置阈值

**Files:**
- Modify: `backend/app/benchmark/config.py`

- [ ] **Step 1: 新增阈值常量**

```python
# 生成质量阈值
QUALITY_THRESHOLDS = {
    "faithfulness": 0.70,
    "answer_relevancy": 0.75,
    "context_precision": 0.70,
    "context_recall": 0.75,
    "hallucination_max": 0.20,
    "negative_detection": 0.80,
}

# 流式延迟阈值
STREAMING_THRESHOLDS = {
    "ttft_p50_ms": 2000,    # 首 token ≤2s
    "ttft_p99_ms": 5000,    # 首 token P99 ≤5s
    "tpot_mean_ms": 100,    # 每 token ≤100ms
}

# 缓存阈值
CACHE_THRESHOLDS = {
    "hit_rate_min": 0.30,
}
```

---

## Task 5: 更新 CostTracker 支持 qwen3.5-flash

**Files:**
- Modify: `backend/app/benchmark/cost_tracker.py`
- Modify: `backend/app/benchmark/config.py`

- [ ] **Step 1: 更新定价表**

```python
PRICING = {
    "dashscope_embedding": 0.00007,   # $0.07/1M tokens
    "dashscope_rerank": 0.0001,       # $0.1/1M tokens
    "qwen3.5-flash": 0.000073,        # $0.073/1M tokens (新加坡节点)
    "qwen3.6-flash": 0.00028,         # $0.28/1M tokens
    "qwen_flash": 0.00028,            # 默认
}
```

- [ ] **Step 2: 更新 cost_tracker 中的模型引用**

```python
model="qwen3.5-flash",  # 从 qwen3.6-flash 更新
```

---

## Task 6: 运行完整测试验证

- [ ] **Step 1: 运行单元测试**

```bash
cd backend && python -m pytest tests/test_vector_store.py tests/test_qa_chain.py tests/test_qdrant_store.py tests/test_benchmark_config.py -v --tb=short
```

- [ ] **Step 2: 运行 Railway benchmark（跳过并发）**

```bash
cd backend && python -m tests.run_benchmark --mode railway --output-dir data --skip-concurrency
```

- [ ] **Step 3: 验证报告格式**

检查 `data/benchmark_railway_*.json` 和 `.md` 文件包含所有 6 维指标。

---

## 执行顺序

1. Task 5（CostTracker 更新）— 无依赖，先改
2. Task 4（配置阈值）— 无依赖
3. Task 1（TTFT/TPOT）— 核心功能
4. Task 2（Answer Relevancy）— 核心功能
5. Task 3（报告升级）— 依赖 Task 1/2 的数据
6. Task 6（验证）— 最后运行
