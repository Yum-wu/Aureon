# RAG 性能优化与测试基础设施升级设计

**日期**: 2026-06-06  
**状态**: Approved  
**作者**: AI Agent + User

## Context

当前 RAG 系统基于 ChromaDB + 同步 pipeline，存在以下关键瓶颈：

- **向量检索延迟 ~5155ms**：使用 DashScope API embedding 导致每次查询需网络往返
- **Negative Detection 0%**（benchmark_actual.json 记录）：实际测试已通过，但迁移后需重新验证
- **测试流程纯串行**：97 QA pairs 逐个执行，无法支撑 1000+ 文档扩展
- **ChromaDB 单节点限制**：不适合大规模生产环境

外部调研参考：
- RAGPerf 论文（arxiv 2603.10765）：端到端 RAG 性能基准框架
- Anyscale 生产指南：CPU/GPU 异构流水线，计算与存储解耦
- Sentence Transformers 官方基准：GPU fp16 可达 1.5-2x 加速，ONNX 可达 3x
- pytest-xdist：PyPI 测试套件并行化提速 81%

## 设计目标

1. 向量检索延迟从 ~5155ms 降至 ~15ms（GPU 本地推理）
2. 端到端 RAG 延迟从 ~400ms 降至 ~100ms（异步并行）
3. 测试执行时间缩短 60-80%（并发 benchmark + pytest-xdist）
4. 支持分阶段扩展：26 → 100 → 500 → 1000+ 文档
5. 所有核心指标不退化：Recall@3 ≥ 90%，MRR ≥ 0.85，Negative Detection ≥ 90%

## 架构设计

```
┌──────────────────────────────────────────────────────────┐
│                     请求入口层                            │
│  FastAPI (async) ─→ RAG Router ─→ Chat Router            │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│                  RAG Pipeline (全异步)                    │
│                                                          │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐            │
│  │ BM25     │   │ Vector   │   │ Reranker │            │
│  │ (CPU)    │   │ (GPU)    │   │ (GPU)    │            │
│  │ ~2ms     │   │ ~15ms    │   │ ~30ms    │            │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘            │
│       │              │              │                    │
│       └──────┬───────┘              │                    │
│              │ RRF Fusion           │                    │
│              └──────────┬───────────┘                    │
│                         │                                │
│  Context Compression → Negative Detection               │
│  → CRAG Self-Correction → LLM Generation                │
└──────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│  Qdrant (向量) ─ BM25 Index (内存) ─ Redis (缓存)       │
└──────────────────────────────────────────────────────────┘
                     │
┌────────────────────▼─────────────────────────────────────┐
│  pytest-xdist (并行) ─ asyncio.benchmark (并发)          │
│  RAGPerf-style E2E ─ DeepEval CI Gate                    │
└──────────────────────────────────────────────────────────┘
```

## 模块设计

### 1. Qdrant 替代 ChromaDB

**选择理由**：
- Rust 实现，单机性能优于 ChromaDB 10-100x
- 支持内存映射模式（mmap），1000+ 文档内存友好
- 原生支持 GPU 加速索引构建
- 已在项目中预留 Qdrant 接口（`save_index_qdrant`, `retrieve_qdrant`）

**实施方案**：
- docker-compose.yml 添加 `qdrant` 服务
- 向量维度：BGE-large-zh 1024d
- Collection：`aureon`，Cosine 距离
- 保留 ChromaDB 代码作为 fallback（`settings.vector_backend` 切换）

**关键文件**：
- `backend/app/rag/vector_store.py` — Qdrant 后端实现
- `docker-compose.yml` — Qdrant 服务配置
- `backend/app/config.py` — backend 切换配置

### 2. GPU Embedding 加速

**当前**：BGE-large-zh CPU fp32 编码  
**优化**：GPU fp16 编码，batch_size=64

```python
model = SentenceTransformer(
    "BAAI/bge-large-zh-v1.5",
    model_kwargs={"torch_dtype": "float16"}
)
model = model.to("cuda")
embeddings = model.encode(texts, batch_size=64, normalize_embeddings=True)
```

**预期性能**：
- CPU fp32: ~200ms/batch (10 texts)
- GPU fp16: ~15ms/batch (10 texts) = 13x 提速
- 1000 文档索引：4760 chunks → ~7.2s（当前 CPU ~95s）

**关键文件**：
- `backend/app/rag/vector_store.py` — `_embed_local()` 优化

### 3. GPU Reranker 加速

**当前**：bge-reranker-v2-m3 CPU 推理 ~300-600ms  
**优化**：GPU 推理 ~30ms

```python
model = CrossEncoder("BAAI/bge-reranker-v2-m3", device="cuda")
scores = model.predict(pairs)  # ~30ms for 20 pairs
```

**关键文件**：
- `backend/app/rag/vector_store.py` — `_get_reranker()` 优化

### 4. 全异步 RAG Pipeline

**核心改造**：
- `hybrid_retrieve()` → `async hybrid_retrieve_async()`
  - BM25 和 Vector 检索通过 `asyncio.gather` 并行执行
- `rag_query()` → `async rag_query_async()`
- `multi_query_retrieve()` → `async multi_query_retrieve_async()`
- `compress_context()` → `async compress_context_async()`

**并行检索示例**：
```python
async def hybrid_retrieve_async(query, top_k=3):
    bm25_task = asyncio.to_thread(retrieve_keyword, query, top_k * multiplier)
    vector_task = retrieve_qdrant_async(query, top_k * multiplier)
    bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)
    return _rrf_fusion(bm25_results, vector_results, top_k)
```

**预期延迟**：
- 当前串行：BM25 2.5ms + Vector 5155ms = 5157ms
- 异步并行：max(2.5ms, 15ms) = ~15ms
- 端到端：检索 15ms + LLM 300ms = ~100ms

**保持兼容**：保留同步版本，async 版本作为默认

**关键文件**：
- `backend/app/rag/qa_chain.py` — 核心 pipeline 异步化
- `backend/app/routers/rag.py` — Router 异步适配

### 5. 测试基础设施升级

#### 5a. 并发 Benchmark 框架

**新建**：`backend/tests/benchmark_concurrent.py`

```python
async def run_concurrent_benchmark(qa_pairs, concurrency=10):
    semaphore = asyncio.Semaphore(concurrency)
    async def eval_single(qa):
        async with semaphore:
            return await evaluate_qa_async(qa)
    results = await asyncio.gather(*[eval_single(qa) for qa in qa_pairs])
    return aggregate_results(results)
```

**测试维度**：
- 并发度压测：1/5/10/20/50 并发，测量 QPS 和 P99 延迟
- 文档规模压测：26 → 100 → 500 → 1000 逐步加载
- 混合负载：读写并发（参考 RAGPerf workload generator）

#### 5b. pytest-xdist 并行

**配置**：`pyproject.toml` 添加 `addopts = "-n auto"`

**隔离策略**：
- 每个 worker 独立的 Qdrant collection
- `tmp_path_factory` 创建隔离测试数据
- Mock 外部 API 调用

#### 5c. 文档扩展测试矩阵

| 阶段 | 文档数 | 预估 Chunks | 测试重点 |
|------|--------|-------------|---------|
| 阶段 1 | 26→100 | ~1800 | Qdrant 迁移验证，Recall 不退化 |
| 阶段 2 | 100→500 | ~9000 | 索引构建时间，查询延迟线性度 |
| 阶段 3 | 500→1000 | ~18000 | 内存占用，P99 延迟，QPS 上限 |

**验收标准**：
- Recall@3 ≥ 90%
- 向量检索延迟 P99 < 100ms
- 全流程延迟 P99 < 500ms
- Negative Detection ≥ 90%
- 索引构建时间 < 60s

### 6. Negative Detection 回归保障

- 迁移 Qdrant 后必须重新运行 benchmark
- 如 Negative Detection 退化，调优 Qdrant score threshold
- 保留关键词快速路径 + LLM 分类器混合策略

## 分阶段实施

### Phase 1: 基础设施升级（Qdrant + GPU）

| 任务 | 文件 | 预期耗时 |
|------|------|---------|
| Qdrant Docker 服务 | docker-compose.yml | 0.5h |
| Qdrant 后端完善 | backend/app/rag/vector_store.py | 3h |
| GPU embedding 优化 | backend/app/rag/vector_store.py | 1h |
| GPU reranker 优化 | backend/app/rag/vector_store.py | 1h |
| 迁移脚本 + 数据验证 | backend/app/rag/migration.py (new) | 1h |
| Benchmark 对比验证 | backend/tests/run_benchmark.py | 0.5h |

### Phase 2: 全异步 RAG Pipeline

| 任务 | 文件 | 预期耗时 |
|------|------|---------|
| async hybrid_retrieve | backend/app/rag/qa_chain.py | 2h |
| async rag_query | backend/app/rag/qa_chain.py | 2h |
| async multi_query_retrieve | backend/app/rag/qa_chain.py | 1h |
| RAG Router 异步适配 | backend/app/routers/rag.py | 1h |
| 全流程异步 benchmark | | 0.5h |

### Phase 3: 测试基础设施

| 任务 | 文件 | 预期耗时 |
|------|------|---------|
| 并发 benchmark 框架 | backend/tests/benchmark_concurrent.py (new) | 2h |
| pytest-xdist 配置 | pyproject.toml | 0.5h |
| 测试隔离策略 | backend/tests/conftest.py | 1h |
| 100 文档扩展数据 | backend/data/articles/ | 2h |
| 100 文档 benchmark | | 0.5h |

### Phase 4: 大规模验证（500→1000）

| 任务 | 文件 | 预期耗时 |
|------|------|---------|
| 500 文档数据准备 | backend/data/articles/ | 3h |
| 索引性能测试 | | 1h |
| 1000 文档验证 | | 2h |
| 性能回归报告 | backend/data/benchmark_report.json | 0.5h |

## 验证方案

1. **每个 Phase 完成后运行 benchmark**：`cd backend && python -m tests.run_benchmark`
2. **并发 benchmark**：`cd backend && python -m tests.benchmark_concurrent`
3. **CI 质量门**：`cd backend && python -m pytest tests/test_rag_quality.py -v --timeout=300`
4. **回归测试**：对比 `benchmark_actual.json` 和迁移后的结果

## 技术依赖

- `qdrant-client` — Python Qdrant SDK
- `sentence-transformers` — GPU embedding
- `pytest-xdist` — 并行测试
- `pytest-asyncio` — 异步测试
- CUDA toolkit（用户已有 GPU）

## 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| Qdrant 迁移后 Recall 退化 | 指标不达标 | 迁移后立即 benchmark 对比，保留 ChromaDB fallback |
| GPU 内存不足 | OOM 错误 | fp16 减半内存，batch_size 可配置 |
| 测试隔离不彻底 | 并行测试互相干扰 | 每个 worker 独立 collection + 临时目录 |
| 1000 文档数据不足 | 无法验证扩展性 | 使用现有 26 文档作为种子，生成合成变体 |

## 参考资料

- [RAGPerf: End-to-End Benchmarking Framework](https://arxiv.org/html/2603.10765v1)
- [Scale RAG for Production - Anyscale](https://docs.anyscale.com/rag/production-scalability)
- [Sentence Transformers Efficiency](https://sbert.net/docs/sentence_transformer/usage/efficiency.html)
- [Making PyPI's Test Suite 81% Faster](https://blog.trailofbits.com/2025/05/01/making-pypis-test-suite-81-faster/)
- [pytest-asyncio-concurrent](https://pypi.org/project/pytest-asyncio-concurrent/)
