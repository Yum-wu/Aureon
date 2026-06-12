# RAG Benchmark 重构设计

**日期**: 2026-06-12
**状态**: 待审核

## 背景

当前 `backend/tests/` 下有 6 个 benchmark 文件 + 1 个质量门禁文件，功能大量重叠、维护成本高、与生产环境不一致。目标是构建面向 1000+ 文档规模的企业级 RAG 测试体系。

## 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| 文件结构 | 单文件 + YAML 配置 | 最简单，marker 分层灵活，YAML 支持数据集扩展 |
| 质量门禁 | 走完整 rag_query() pipeline | 与生产一致（HyDE/CRAG/压缩/负例检测） |
| 生产冒烟 | 新增 smoke marker | 部署后验证生产端点可达 |
| 评判框架 | 仅 DeepEval | 已集成，不加 RAGAS 避免双重维护 |
| CI 集成 | 仅单元测试 | benchmark/质量/冒烟本地手动触发 |

## 方案选择

### 方案 A：单文件分层（纯 marker）

1 个 `benchmark_enterprise.py`，内部用 `@pytest.mark` 分层。QA 数据和阈值硬编码。

**问题**：1000+ 文档时 QA 数据集不可维护。

### 方案 B：三文件分层

3 个文件按关注点拆分，共享 fixture 放 conftest.py。

**问题**：3 个文件 + conftest 维护点增多，与 marker 分层等价但多了文件管理成本。

### 方案 C：单文件 + 配置驱动

1 个文件 + 1 个 YAML，测试逻辑也配置化。

**问题**：测试逻辑变化频率低，配置化是过度抽象。

### 选择：方案 A+（单文件 + YAML 配置分离）

采用方案 A 的单文件分层结构，但从第一天起把 QA 数据集和阈值外置为 YAML。只有数据（QA/阈值）变化频率高才需要外置，测试逻辑保持代码化。

**渐进路径**：

| 阶段 | 规模 | 配置复杂度 |
|------|------|-----------|
| 现在 | ~10 文档 | YAML 存 QA + 阈值 |
| 中期 | 100-500 文档 | YAML 按领域分 section，加回归基线 |
| 远期 | 1000+ 文档 | 多 YAML 文件 + 历史指标对比脚本 |

## 文件结构

```
backend/tests/
├── benchmark_enterprise.py        # 统一测试文件（~350 行）
├── benchmark_config.yaml          # QA 数据集 + 阈值 + 端点配置
├── deepeval_eval.py               # DeepEval 评判逻辑（保留，微调）
├── conftest.py                    # 全局 fixture（保留）

# 删除的文件
├── benchmark_rag.py               ❌ 删除
├── benchmark_rag_full.py          ❌ 删除
├── benchmark_e2e.py               ❌ 删除
├── benchmark_concurrent.py        ❌ 删除
├── benchmark_semantic_cache.py    ❌ 删除
├── test_rag_quality.py            ❌ 删除
```

## 测试金字塔

```
                    ┌─────────────┐
                    │  生产冒烟    │  @pytest.mark.smoke
                    │  (3-5 测试)  │  每次部署后手动跑
                   ┌┴─────────────┴┐
                   │  质量门禁      │  @pytest.mark.quality
                   │  (DeepEval)   │  本地手动 / 合并前跑
                  ┌┴───────────────┴┐
                  │  性能基准        │  @pytest.mark.benchmark
                  │  (延迟/QPS/并发) │  本地手动跑
                 ┌┴─────────────────┴┐
                 │  单元测试          │  无 marker（CI 默认跑）
                 │  (753 tests)      │  每次 push 自动跑
                 └───────────────────┘
```

## Marker 体系

| Marker | 用途 | 运行环境 | CI |
|--------|------|---------|-----|
| （无） | 单元测试 | CI + 本地 | 自动跑 |
| `integration` | 需外部服务 | 本地 | 默认跳过 |
| `benchmark` | 检索性能 | 本地 | 跳过 |
| `quality` | DeepEval 质量门禁 | 本地 | 跳过 |
| `smoke` | 生产冒烟 | 本地/部署后 | 跳过 |

### pyproject.toml 配置

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short -m 'not integration and not benchmark and not quality and not smoke'"
markers = [
    "integration: 集成测试，需外部服务，默认跳过",
    "benchmark: 检索性能基准测试",
    "quality: DeepEval 质量门禁测试",
    "smoke: 生产环境冒烟测试",
]
```

## YAML 配置结构

```yaml
# benchmark_config.yaml
qa_dataset:
  - question: "Aureon 的核心功能是什么？"
    expected_answer: "Aureon 是一个 AI 聊天助手平台..."
    expected_sources: ["aureon_intro.md"]
    is_negative: false
  - question: "如何配置不存在的功能 XYZ？"
    expected_answer: ""
    is_negative: true

thresholds:
  retrieval:
    p50_ms: 200
    p99_ms: 1000
    recall_at_5: 0.8
    recall_at_10: 0.9
    mrr: 0.7
    qps_min: 5
  generation:
    p50_ms: 2000
    p99_ms: 5000
  quality:
    faithfulness: 0.7
    answer_relevancy: 0.75
    context_precision: 0.7
    context_recall: 0.7
  cache:
    hit_rate_min: 0.6
    latency_ratio_max: 0.5
  smoke:
    health_timeout_s: 10
    rag_query_timeout_s: 30

endpoints:
  production: "https://aureon-production-1247.up.railway.app"
  local: "http://localhost:8000"

concurrency:
  levels: [1, 5, 10]
  queries_per_level: 20
```

## benchmark_enterprise.py 内部结构

```python
"""企业级 RAG 基准测试套件 — 检索性能 + 质量门禁 + 生产冒烟"""

import asyncio, time, statistics, yaml
import httpx
import pytest
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# ─── 配置加载 ───
cfg = _load_config()

# ─── 共享 Fixture ───
@pytest.fixture(scope="module")
def qa_pairs():
    return cfg["qa_dataset"]

@pytest.fixture(scope="module")
def thresholds():
    return cfg["thresholds"]

@pytest.fixture(scope="module")
def llm():
    from app.agent.llm import create_llm
    return create_llm()

# ─── 第一层：检索性能基准 ───
@pytest.mark.benchmark
@pytest.mark.integration
class TestRetrievalPerformance:
    def test_retrieval_latency(self, qa_pairs, thresholds): ...
    def test_recall_at_k(self, qa_pairs, thresholds): ...
    def test_mrr(self, qa_pairs, thresholds): ...
    def test_throughput_qps(self, qa_pairs, thresholds): ...
    def test_concurrent_retrieval(self, qa_pairs, thresholds): ...

# ─── 第二层：质量门禁（走完整 rag_query pipeline）───
@pytest.mark.quality
@pytest.mark.integration
class TestQualityGate:
    @pytest.fixture(scope="class")
    def eval_results(self, qa_pairs, llm):
        from tests.deepeval_eval import build_test_cases, run_deepeval_metrics
        from app.rag.qa_chain import rag_query

        def rag_query_fn(query):
            return rag_query(query, llm_call_fn=lambda msgs: llm.invoke(msgs).content, top_k=3)

        test_cases, used_indices = build_test_cases(
            qa_pairs, rag_query_fn=rag_query_fn, max_concurrent=10,
        )
        return run_deepeval_metrics(test_cases, qa_pairs, used_indices)

    def test_faithfulness(self, eval_results, thresholds): ...
    def test_answer_relevancy(self, eval_results, thresholds): ...
    def test_context_precision(self, eval_results, thresholds): ...
    def test_context_recall(self, eval_results, thresholds): ...

# ─── 第三层：生产冒烟 ───
@pytest.mark.smoke
@pytest.mark.integration
class TestProductionSmoke:
    def test_health_endpoint(self, thresholds): ...
    def test_rag_query_endpoint(self, qa_pairs, thresholds): ...
    def test_chat_stream_endpoint(self, thresholds): ...
```

## 关键设计决策

### 1. 质量门禁走完整 rag_query()

之前分别调 `hybrid_retrieve` + `rag_query`，与生产不一致。改为只调 `rag_query_fn`，内部已包含 retrieve → HyDE → CRAG → 压缩 → 负例检测 → 生成。

`deepeval_eval.py` 的 `build_test_cases` 签名简化：移除 `retrieve_fn` 参数，只保留 `rag_query_fn`。

**retrieval_context 获取方式**：`rag_query()` 返回的 dict 包含 `sources` 字段（检索到的文档片段列表），`build_test_cases_async` 从返回值中提取 `sources` 作为 `retrieval_context`，提取 `answer` 作为 `actual_output`。不再单独调用 `hybrid_retrieve`。

### 2. 超时保护

- 单次 `rag_query`：`ThreadPoolExecutor` 60s 超时
- 整体 DeepEval 评估：`evaluation_results` fixture 300s 超时 → `pytest.skip`

### 3. 生产冒烟用 httpx 直接调

不依赖 TestClient，直接 HTTP 请求生产端点，验证真实可达性。

### 4. deepeval_eval.py 微调

- `build_test_cases` 简化：移除 `retrieve_fn`，只保留 `rag_query_fn`
- `build_test_cases_async` 内部：每个 QA 只调 `rag_query_fn`
- `run_deepeval_metrics` 保持不变（AsyncConfig + CacheConfig 已优化）

## 迁移映射

| 原文件 | 原功能 | 迁移到 |
|--------|--------|--------|
| `benchmark_rag.py` | 检索延迟、Recall@K、MRR | `TestRetrievalPerformance` |
| `benchmark_rag_full.py` | 97 QA 检索质量 | `TestRetrievalPerformance`（QA 从 YAML 读取） |
| `benchmark_e2e.py` | hybrid_retrieve + LLM 端到端 | `TestQualityGate`（改为走 rag_query） |
| `benchmark_concurrent.py` | 并发检索测试 | `TestRetrievalPerformance.test_concurrent_retrieval` |
| `benchmark_enterprise.py` | 8 维度企业级评估 | 三个 Test 类拆分 |
| `benchmark_semantic_cache.py` | 缓存性能 | `TestRetrievalPerformance` 内加 cache 测试 |
| `test_rag_quality.py` | DeepEval 质量门禁 | `TestQualityGate`（删除原文件） |
| `deepeval_eval.py` | 评判逻辑 | 保留，简化 `build_test_cases` 签名 |

## 运行方式

```bash
# CI 自动跑（单元测试，跳过所有 marker）
cd backend && python -m pytest tests/ -v

# 本地：仅检索性能
pytest tests/benchmark_enterprise.py -m benchmark -v

# 本地：仅质量门禁
pytest tests/benchmark_enterprise.py -m quality -v

# 本地：仅生产冒烟
pytest tests/benchmark_enterprise.py -m smoke -v

# 本地：全量（性能 + 质量 + 冒烟）
pytest tests/benchmark_enterprise.py -m "benchmark or quality or smoke" -v

# 本地：所有测试（含集成）
pytest tests/ -m "" -v
```

## 错误处理

| 场景 | 处理方式 |
|------|---------|
| YAML 配置缺失 | `_load_config()` 抛 `FileNotFoundError`，测试启动即失败 |
| 阈值字段缺失 | `thresholds.get("key", default)` 带默认值 |
| rag_query 超时 | `ThreadPoolExecutor` 60s 超时 → 该 QA 标记失败，不阻塞其他 |
| DeepEval 整体超时 | `evaluation_results` fixture 300s 超时 → `pytest.skip` |
| 生产冒烟网络错误 | `httpx.TimeoutException` → 断言失败，明确报错 |
| QA 数据集为空 | fixture 中 `assert qa_pairs`，提前失败 |
