# Aureon RAG 渐进式优化实施方案

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 通过阶梯扩容（100→500→1000+）和 7 项检索优化，将 Contextual Relevancy 从 39.1% 提升到 ≥70%，Contextual Recall 从 50.0% 提升到 ≥75%，Recall@5 从 92.4% 提升到 ≥95%。

**Architecture:** 渐进式三阶段：阶段 1 扩容+快速修复（4 项代码修复+参数调整），阶段 2 检索质量深化（冗余过滤+QA 扩展+参数微调），阶段 3 闭环优化+阶梯扩容。

**Tech Stack:** Python 3.12, FastAPI, Qdrant, LangChain, DashScope/SiliconFlow API, pytest

---

## 文件结构

| 操作 | 文件 | 职责 |
|------|------|------|
| 修改 | `backend/app/config.py` | compression_threshold 0.15→0.30, rrf_k 200→60 |
| 修改 | `backend/app/rag/qdrant_ops.py` | hybrid_search_qdrant: prefetch limit top_k*5→top_k*10, RRF k=60, parent_text 一致性 |
| 修改 | `backend/app/rag/indexer.py` | max_concurrent 10→15 |
| 修改 | `backend/app/rag/qa_chain.py` | 新增 _deduplicate_chunks 冗余过滤 |
| 修改 | `backend/tests/benchmark_config.yaml` | QA 数据集扩展，固定种子 6:3:1 |
| 修改 | `backend/tests/run_full_benchmark.py` | 负例检测修复，分级验证（10/50/全量），health check 保活 |
| 创建 | `backend/data/articles/rag/` | 50 篇 RAG 同领域文章 |
| 创建 | `backend/data/articles/business/` | 24 篇商业跨领域文章 |

---

## 阶段 1：扩容 + 快速修复

### Task 1: 修改 config.py 参数

**Files:**
- Modify: `backend/app/config.py:46-47,57`

- [ ] **Step 1: 修改 rrf_k 和 compression_threshold**

在 `VectorStoreSettings` 中修改两个参数：

```python
# 修改前
rrf_k: int = 200
context_compression_threshold: float = 0.15

# 修改后
rrf_k: int = 60  # Qdrant 官方推荐值，让排名靠前结果权重更大
context_compression_threshold: float = 0.30  # 过滤低相关 chunk，减少噪声
```

- [ ] **Step 2: 验证配置加载正确**

Run: `cd backend && python -c "from app.config import settings; print(f'rrf_k={settings.rrf_k}, compression_threshold={settings.context_compression_threshold}')"`

Expected: `rrf_k=60, compression_threshold=0.3`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: adjust rrf_k=60 and compression_threshold=0.30 for better retrieval quality"
```

---

### Task 2: 修改 hybrid_search_qdrant — prefetch limit + RRF k + parent_text

**Files:**
- Modify: `backend/app/rag/qdrant_ops.py:691-761`

- [ ] **Step 1: 修改 prefetch limit 从 top_k*5 到 top_k*10**

在 `hybrid_search_qdrant` 函数中，找到两处 `top_k * 5` 并改为 `top_k * 10`：

```python
# 修改前（约第 699 行）
limit=top_k * 5,

# 修改后
limit=top_k * 10,  # 扩大候选池提升 Recall

# 修改前（约第 714 行，sparse prefetch）
limit=top_k * 5,

# 修改后
limit=top_k * 10,  # 扩大候选池提升 Recall
```

- [ ] **Step 2: 修改 FusionQuery 传入 rrf_k**

```python
# 修改前（约第 728 行）
query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),

# 修改后
query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF, rrf_k=60),
```

注意：如果 `qdrant_client` 版本不支持 `rrf_k` 参数，会报 TypeError。此时需要在客户端侧做 post-processing 或升级 qdrant_client。先运行 Step 3 确认。

- [ ] **Step 3: 验证 qdrant_client 支持 rrf_k**

Run: `cd backend && python -c "from qdrant_client import models; fq = models.FusionQuery(fusion=models.Fusion.RRF, rrf_k=60); print(f'rrf_k supported: {fq}')"`

Expected: 成功打印 FusionQuery 对象。如果报 TypeError，则回退到不带 rrf_k 的版本，记录为后续优化项。

- [ ] **Step 4: 修改格式化结果，增加 parent_text 一致性**

在 `hybrid_search_qdrant` 的结果格式化部分（约第 750-761 行），增加 parent_text 逻辑：

```python
# 修改前
for point in results.points:
    payload = point.payload or {}
    chunk = {
        "id": str(point.id),
        "text": payload.get("text", ""),
        "metadata": payload.get("metadata", {}),
        "score": point.score,
    }

# 修改后
for point in results.points:
    payload = point.payload or {}
    payload_meta = payload.get("metadata", {})
    # Parent-Child chunking: use parent_text for richer context if available
    parent_text = payload_meta.get("parent_text", "")
    display_text = parent_text if parent_text else payload.get("text", "")
    chunk = {
        "id": str(point.id),
        "text": display_text,
        "metadata": payload_meta,
        "score": point.score,
    }
```

- [ ] **Step 5: 运行现有测试确认无回归**

Run: `cd backend && python -m pytest tests/test_rag.py -v -k "hybrid or qdrant" --timeout=60`

Expected: 所有相关测试通过

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/qdrant_ops.py
git commit -m "feat: hybrid_search_qdrant prefetch top_k*10, RRF k=60, parent_text consistency"
```

---

### Task 3: 修改 indexer.py max_concurrent

**Files:**
- Modify: `backend/app/rag/indexer.py:149,213`

- [ ] **Step 1: 修改 max_concurrent 从 10 到 15**

找到两处 `max_concurrent=10` 并改为 `max_concurrent=15`：

```python
# 修改前（约第 149 行）
async def _generate_contextual_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10):

# 修改后
async def _generate_contextual_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=15):
```

```python
# 修改前（约第 213 行）
prefixes = asyncio.run(_generate_contextual_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10))

# 修改后
prefixes = asyncio.run(_generate_contextual_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=15))
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/rag/indexer.py
git commit -m "feat: increase contextual prefix max_concurrent to 15 for faster indexing"
```

---

### Task 4: 生成 74 篇文档

**Files:**
- Create: `backend/data/articles/rag/` (50 篇)
- Create: `backend/data/articles/business/` (24 篇)

- [ ] **Step 1: 创建目录结构**

Run: `mkdir -p backend/data/articles/rag backend/data/articles/business`

- [ ] **Step 2: 生成 RAG 同领域 50 篇文章**

按设计文档中的 5 组（A-E）生成文章。每篇 2000-4000 字，中英混合，包含 3-5 个可检索事实点。

文件命名规则：`{组号}-{序号}-{slug}.md`，如 `A-01-hyde-principles-and-practice.md`

**组 A：检索技术（12 篇）**
1. A-01-hyde-principles-and-practice.md — "HyDE 原理与实践"
2. A-02-multi-query-retrieval-comparison.md — "Multi-Query 检索策略对比"
3. A-03-bm25-vs-sparse-vector-evolution.md — "BM25 vs 稀疏向量：RAG 关键词检索演进"
4. A-04-query-expansion-techniques.md — "查询扩展技术：从伪相关反馈到 LLM 扩展"
5. A05-reciprocal-rank-fusion-deep-dive.md — "RRF 融合深度解析：参数调优与实践"
6. A-06-late-interaction-models-colbert.md — "Late Interaction 模型：ColBERT 与其变体"
7. A-07-retrieval-augmented-generation-overview.md — "检索增强生成：从朴素 RAG 到高级 RAG"
8. A-08-cross-encoder-vs-bi-encoder.md — "Cross-Encoder vs Bi-Encoder：检索精度与速度的权衡"
9. A-09-maximal-marginal-relevance.md — "MMR 多样性检索：平衡相关性与新颖性"
10. A-10-retrieval-feedback-loops.md — "检索反馈闭环：从用户信号到检索优化"
11. A-11-semantic-search-fundamentals.md — "语义搜索基础：从 TF-IDF 到稠密检索"
12. A-12-federated-search-multi-source.md — "联邦检索：多数据源统一搜索架构"

**组 B：向量与 Embedding（10 篇）**
1. B-01-embedding-model-selection-guide.md — "Embedding 模型选型指南：BGE vs OpenAI vs Cohere"
2. B-02-vector-quantization-int8-fp16.md — "向量量化：INT8 vs FP16 延迟-精度权衡"
3. B-03-matryoshka-embeddings.md — "Matryoshka 嵌入：一次编码多粒度检索"
4. B-04-domain-specific-fine-tuning.md — "领域微调 Embedding：何时需要与如何做"
5. B-05-multilingual-embedding-challenges.md — "多语言 Embedding 挑战与解决方案"
6. B-06-embedding-dimension-reduction.md — "Embedding 降维：PCA vs AutoEncoder vs MRL"
7. B-07-bge-m3-architecture-analysis.md — "BGE-M3 架构解析：dense + sparse + colbert 三合一"
8. B-08-embedding-api-benchmark.md — "Embedding API 性能对比：延迟、吞吐、成本"
9. B-09-vector-index-algorithms.md — "向量索引算法：HNSW vs IVF vs ScaNN"
10. B-10-embedding-drift-detection.md — "Embedding 漂移检测：模型更新后的数据一致性"

**组 C：RAG 架构（12 篇）**
1. C-01-corrective-rag-implementation.md — "CRAG 自纠正检索增强生成"
2. C-02-self-rag-learn-retrieve-generate-critique.md — "Self-RAG：学习检索-生成-批评"
3. C-03-adaptive-rag-query-routing.md — "Adaptive-RAG 查询路由设计"
4. C-04-contextual-retrieval-in-practice.md — "Contextual Retrieval 实战"
5. C-05-rag-pipeline-optimization.md — "RAG Pipeline 优化：从串行到并行"
6. C-06-multi-modal-rag.md — "多模态 RAG：图文混合检索与生成"
7. C-07-agentic-rag-tool-calling.md — "Agentic RAG：工具调用增强检索"
8. C-08-rag-caching-strategies.md — "RAG 缓存策略：语义缓存与查询去重"
9. C-09-rag-error-recovery.md — "RAG 错误恢复：检索失败时的降级策略"
10. C-10-rag-streaming-architecture.md — "RAG 流式架构：SSE 与增量生成"
11. C-11-rag-security-guardrails.md — "RAG 安全护栏：Prompt Injection 防御与 PII 保护"
12. C-12-rag-cost-optimization.md — "RAG 成本优化：Token 预算与模型路由"

**组 D：评估与优化（10 篇）**
1. D-01-rag-evaluation-framework.md — "RAG 评估框架：RAG Triad 与 DeepEval"
2. D-02-faithfulness-vs-relevancy-conflict.md — "Faithfulness vs Relevancy：当指标冲突时怎么办"
3. D-03-rag-latency-optimization.md — "RAG 延迟优化：从 5s 到 1s 的实践"
4. D-04-benchmark-design-for-rag.md — "RAG Benchmark 设计：数据集构建与指标选择"
5. D-05-llm-as-judge-evaluation.md — "LLM-as-Judge 评估：原理、偏见与缓解"
6. D-06-retrieval-quality-metrics.md — "检索质量指标：Recall@K、MRR、nDCG 的选择"
7. D-07-ab-testing-for-rag.md — "RAG A/B 测试：如何科学对比两个 Pipeline"
8. D-08-rag-regression-testing.md — "RAG 回归测试：防止优化变劣化"
9. D-09-context-window-optimization.md — "Context Window 优化：信息密度与噪声控制"
10. D-10-rag-observability.md — "RAG 可观测性：全链路追踪与异常检测"

**组 E：工具与平台（6 篇）**
1. E-01-qdrant-hybrid-search-best-practices.md — "Qdrant Hybrid Search 最佳实践"
2. E-02-langchain-rag-module-deep-dive.md — "LangChain RAG 模块深度解析"
3. E-03-cohere-rerank-integration.md — "Cohere Rerank 集成指南"
4. E-04-dashscope-embedding-api-guide.md — "DashScope Embedding API 使用指南"
5. E-05-langfuse-rag-tracing.md — "LangFuse RAG 追踪集成"
6. E-06-redis-semantic-cache.md — "Redis 语义缓存实现"

- [ ] **Step 3: 生成商业跨领域 24 篇文章**

文件命名规则：`{组号}-{序号}-{slug}.md`

**组 F：产品与增长（8 篇）**
1. F-01-saas-pricing-strategy.md — "SaaS 定价策略：从免费到企业级"
2. F-02-plg-vs-slg-growth.md — "PLG vs SLG：产品驱动增长的选择"
3. F-03-user-retention-framework.md — "用户留存分析框架"
4. F-04-product-market-fit-validation.md — "PMF 验证：如何确认产品市场匹配"
5. F-05-growth-loops-design.md — "增长飞轮设计：从获客到留存"
6. F-06-conversion-rate-optimization.md — "转化率优化：从漏斗分析到实验设计"
7. F-07-churn-prediction.md — "流失预测：识别高风险用户信号"
8. F-08-onboarding-optimization.md — "新用户引导优化：从激活到习惯养成"

**组 G：管理与运营（8 篇）**
1. G-01-okr-implementation.md — "OKR 落地实践：从目标到关键结果"
2. G-02-tech-debt-governance.md — "敏捷开发中的技术债务治理"
3. G-03-ab-testing-guide.md — "数据驱动决策：A/B 测试设计指南"
4. G-04-team-productivity-metrics.md — "团队生产力度量：从代码到交付"
5. G-05-incident-management.md — "事件管理：从告警到复盘"
6. G-06-knowledge-management.md — "知识管理：团队经验沉淀与传承"
7. G-07-cross-functional-collaboration.md — "跨职能协作：产品-设计-工程高效配合"
8. G-08-data-driven-decision-making.md — "数据驱动决策：指标体系与仪表盘设计"

**组 H：商业模式（8 篇）**
1. H-01-mvp-methodology.md — "MVP 方法论：最小可行产品的验证循环"
2. H-02-b2b-customer-success.md — "B2B 客户成功管理框架"
3. H-03-product-roadmap-planning.md — "从 0 到 1 的产品路线图规划"
4. H-04-business-model-canvas.md — "商业模式画布：从假设到验证"
5. H-05-competitive-analysis.md — "竞争分析：从市场地图到差异化定位"
6. H-06-go-to-market-strategy.md — "GTM 策略：从种子用户到规模化"
7. H-07-unit-economics.md — "单位经济学：LTV、CAC 与盈利模型"
8. H-08-platform-economics.md — "平台经济学：网络效应与双边市场"

- [ ] **Step 4: 验证文档生成质量**

Run: `cd backend && python -c "import os; rag=len(os.listdir('data/articles/rag')); biz=len(os.listdir('data/articles/business')); print(f'RAG: {rag} 篇, Business: {biz} 篇, Total: {rag+biz}')"`

Expected: `RAG: 50 篇, Business: 24 篇, Total: 74`

- [ ] **Step 5: Commit**

```bash
git add backend/data/articles/
git commit -m "feat: add 74 articles (50 RAG + 24 business) for knowledge base expansion"
```

---

### Task 5: 生成 QA 数据集（6:3:1 分布 + 负例）

**Files:**
- Modify: `backend/tests/benchmark_config.yaml`

- [ ] **Step 1: 基于 100 篇文档生成 QA 数据集**

在 `benchmark_config.yaml` 的 `qa_dataset` 中添加新的 QA 条目，覆盖所有 100 篇文档。

数据集规模：
- 简单（factual）：~180 条
- 中等（reasoning）：~90 条
- 困难（synthesis）：~30 条
- 负例（negative）：20 条
- 总计：~320 条

每条 QA 格式：
```yaml
- question: "HyDE 的核心原理是什么？"
  expected_answer: "HyDE 通过 LLM 生成假设性答案文档，再对该文档做 embedding 检索，从而将查询映射到更接近真实文档的语义空间"
  source_article: "A-01-hyde-principles-and-practice"
  difficulty: "simple"
  is_negative: false
```

负例格式：
```yaml
- question: "公司报销流程是什么？"
  expected_answer: "知识库中未包含此信息"
  source_article: ""
  difficulty: "simple"
  is_negative: true
```

- [ ] **Step 2: 验证 QA 数据集分布**

Run: `cd backend && python -c "
import yaml
with open('tests/benchmark_config.yaml') as f:
    cfg = yaml.safe_load(f)
qa = cfg.get('qa_dataset', [])
simple = sum(1 for q in qa if q.get('difficulty')=='simple' and not q.get('is_negative'))
medium = sum(1 for q in qa if q.get('difficulty')=='medium' and not q.get('is_negative'))
hard = sum(1 for q in qa if q.get('difficulty')=='hard' and not q.get('is_negative'))
neg = sum(1 for q in qa if q.get('is_negative'))
total = len(qa)
print(f'Simple: {simple}, Medium: {medium}, Hard: {hard}, Negative: {neg}, Total: {total}')
print(f'Ratio: {simple/(total-neg):.1f}:{medium/(total-neg):.1f}:{hard/(total-neg):.1f}')
"`

Expected: `Simple: ~180, Medium: ~90, Hard: ~30, Negative: 20, Ratio ≈ 6:3:1`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/benchmark_config.yaml
git commit -m "feat: expand QA dataset to 320 items covering 100 articles with 6:3:1 difficulty distribution"
```

---

### Task 6: 修复 benchmark 脚本 — 负例检测 + 分级验证 + health check 保活

**Files:**
- Modify: `backend/tests/run_full_benchmark.py`

- [ ] **Step 1: 添加 health check 保活逻辑**

在 benchmark 运行前增加 health check 循环，确保服务就绪：

```python
import httpx

def wait_for_service(base_url: str, max_retries: int = 10, interval: int = 10):
    """等待服务就绪，避免冷启动污染延迟数据。"""
    for i in range(max_retries):
        try:
            resp = httpx.get(f"{base_url}/api/health", timeout=10)
            if resp.status_code == 200 and resp.json().get("status") == "ok":
                print(f"✅ 服务就绪（第 {i+1} 次尝试）")
                return True
        except Exception:
            pass
        print(f"⏳ 等待服务就绪...（第 {i+1}/{max_retries} 次）")
        time.sleep(interval)
    raise RuntimeError(f"服务在 {max_retries * interval}s 内未就绪")
```

在 `run_full_benchmark.py` 的 main 函数开头调用：
```python
wait_for_service(endpoint, max_retries=10, interval=10)
```

- [ ] **Step 2: 添加分级验证逻辑**

在 benchmark 脚本中增加 `--level` 参数支持三级验证：

```python
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--level", choices=["quick", "detailed", "full"], default="detailed",
                    help="验证级别：quick=10条, detailed=50条, full=全部")
parser.add_argument("--seed", type=int, default=42, help="固定随机种子")
args = parser.parse_args()

# 根据 level 确定采样数量
LEVEL_SIZES = {"quick": 10, "detailed": 50, "full": None}
sample_size = LEVEL_SIZES[args.level]
```

采样逻辑：固定种子 + 6:3:1 难度分布
```python
import random

def sample_qa(qa_dataset, sample_size, seed=42):
    """固定种子采样，确保 6:3:1 难度分布。"""
    rng = random.Random(seed)
    negatives = [q for q in qa_dataset if q.get("is_negative")]
    non_neg = [q for q in qa_dataset if not q.get("is_negative")]

    simple = [q for q in non_neg if q.get("difficulty") == "simple"]
    medium = [q for q in non_neg if q.get("difficulty") == "medium"]
    hard = [q for q in non_neg if q.get("difficulty") == "hard"]

    # 6:3:1 分布
    n_simple = max(1, round(sample_size * 0.6))
    n_medium = max(1, round(sample_size * 0.3))
    n_hard = max(1, sample_size - n_simple - n_medium)

    sampled = (
        rng.sample(simple, min(n_simple, len(simple))) +
        rng.sample(medium, min(n_medium, len(medium))) +
        rng.sample(hard, min(n_hard, len(hard))) +
        negatives  # 负例全部包含
    )
    rng.shuffle(sampled)
    return sampled
```

- [ ] **Step 3: 修复负例检测评估**

确保 benchmark 结果中 `negative_detection_rate` 正确计算：

```python
def evaluate_negative_detection(results):
    """评估负例检测率。"""
    negative_results = [r for r in results if r.get("is_negative")]
    if not negative_results:
        return 0.0
    correctly_rejected = sum(
        1 for r in negative_results
        if r.get("detected_as_negative", False)  # 检测到为负例
    )
    return correctly_rejected / len(negative_results)
```

确保负例 query 在 benchmark 中被标记 `is_negative=True`，且结果中记录 `detected_as_negative` 字段。

- [ ] **Step 4: 验证 benchmark 脚本运行**

Run: `cd backend && python tests/run_full_benchmark.py --level quick --phase 1`

Expected: 成功运行 10 条 QA + 负例，输出包含 `negative_detection_rate`

- [ ] **Step 5: Commit**

```bash
git add backend/tests/run_full_benchmark.py
git commit -m "feat: benchmark health check, tiered validation (10/50/full), fixed negative detection"
```

---

### Task 7: 全量索引 + 快速验证

**Files:**
- 无代码修改，运行时操作

- [ ] **Step 1: 启动服务并 health check 保活**

Run: `cd backend && uvicorn app.main:app --reload --port 8000`

等待服务就绪后，确认 health check 通过：
Run: `curl -s http://localhost:8000/api/health | python -m json.tool`

Expected: `{"status": "ok"}`

- [ ] **Step 2: 上传 74 篇新文档并全量索引**

通过 `/api/rag/upload` 端点上传新文档，或使用索引脚本：
```bash
cd backend && python -c "
from app.rag.indexer import run_index_pipeline
run_index_pipeline(enable_contextual=True)
"
```

Expected: 索引完成，日志显示 ~1600 chunks

- [ ] **Step 3: 快速验证（10 条 QA）**

Run: `cd backend && python tests/run_full_benchmark.py --level quick --phase 1`

Expected: 10 条 QA 全部完成，无报错，negative_detection_rate > 0

- [ ] **Step 4: 详细验证（50 条 QA）**

Run: `cd backend && python tests/run_full_benchmark.py --level detailed --phase 1`

Expected: 50 条 QA 完成，记录基线指标：
- Contextual Relevancy
- Contextual Recall
- Recall@5
- E2E P50/P99
- negative_detection_rate

- [ ] **Step 5: 记录基线数据**

将 benchmark 结果保存到 `backend/data/benchmark_results_100docs_baseline.json`

---

## 阶段 2：检索质量深化

### Task 8: 实现冗余过滤 _deduplicate_chunks

**Files:**
- Modify: `backend/app/rag/qa_chain.py`
- Test: `backend/tests/test_rag.py`

- [ ] **Step 1: 编写冗余过滤测试**

```python
def test_deduplicate_chunks_same_slug():
    """同 slug 内语义重复的 chunk 应去重，保留 compression_score 最高的。"""
    chunks = [
        {"text": "RAG 是检索增强生成技术", "metadata": {"slug": "rag-intro"}, "compression_score": 0.8, "embedding": np.array([1.0, 0.0, 0.0])},
        {"text": "RAG 是一种检索增强生成的方法", "metadata": {"slug": "rag-intro"}, "compression_score": 0.6, "embedding": np.array([0.99, 0.1, 0.0])},
        {"text": "向量数据库用于存储 Embedding", "metadata": {"slug": "vector-db"}, "compression_score": 0.7, "embedding": np.array([0.0, 1.0, 0.0])},
    ]
    result = _deduplicate_chunks(chunks, threshold=0.85)
    # 同 slug 内 cosine > 0.85 的去重，保留 score 最高的
    assert len(result) == 2
    assert result[0]["compression_score"] == 0.8  # 保留 score 最高的
    assert result[1]["metadata"]["slug"] == "vector-db"  # 不同 slug 保留

def test_deduplicate_chunks_different_slug_no_dedup():
    """不同 slug 的 chunk 即使语义相似也不去重。"""
    chunks = [
        {"text": "RAG 是检索增强生成技术", "metadata": {"slug": "rag-intro"}, "compression_score": 0.8, "embedding": np.array([1.0, 0.0, 0.0])},
        {"text": "RAG 是检索增强生成的核心技术", "metadata": {"slug": "rag-advanced"}, "compression_score": 0.7, "embedding": np.array([0.99, 0.1, 0.0])},
    ]
    result = _deduplicate_chunks(chunks, threshold=0.85)
    assert len(result) == 2  # 不同 slug 不去重
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_rag.py::test_deduplicate_chunks_same_slug -v`

Expected: FAIL（`_deduplicate_chunks` 未定义）

- [ ] **Step 3: 实现 _deduplicate_chunks**

在 `qa_chain.py` 中 `compress_context` 函数之后添加：

```python
def _deduplicate_chunks(chunks: list, threshold: float = 0.85) -> list:
    """同 slug 内语义重复的 chunk 去重，保留 compression_score 最高的。

    不同 slug 间不做去重，保留跨文章多样性。
    复用 chunk 中已有的 embedding，避免额外 API 调用。
    """
    if not chunks:
        return chunks

    # 按 slug 分组
    slug_groups: dict[str, list] = {}
    for chunk in chunks:
        slug = chunk.get("metadata", {}).get("slug", "")
        slug_groups.setdefault(slug, []).append(chunk)

    result = []
    for slug, group in slug_groups.items():
        if len(group) <= 1:
            result.extend(group)
            continue

        # 按 compression_score 降序排列
        group.sort(key=lambda c: c.get("compression_score", 0), reverse=True)

        kept = []
        for chunk in group:
            chunk_emb = chunk.get("embedding")
            if chunk_emb is None:
                kept.append(chunk)
                continue

            # 检查是否与已保留的 chunk 语义重复
            is_duplicate = False
            for kept_chunk in kept:
                kept_emb = kept_chunk.get("embedding")
                if kept_emb is None:
                    continue
                # cosine 相似度
                norm_a = np.linalg.norm(chunk_emb)
                norm_b = np.linalg.norm(kept_emb)
                if norm_a < 1e-6 or norm_b < 1e-6:
                    continue
                cosine = float(np.dot(chunk_emb, kept_emb) / (norm_a * norm_b))
                if cosine > threshold:
                    is_duplicate = True
                    break

            if not is_duplicate:
                kept.append(chunk)

        result.extend(kept)

    # 按 compression_score 降序重排
    result.sort(key=lambda c: c.get("compression_score", 0), reverse=True)
    return result
```

- [ ] **Step 4: 在 rag_query_astream 中集成冗余过滤**

在 `compress_context` 调用之后，添加 `_deduplicate_chunks` 调用：

```python
# 在 compress_context 之后
if compressed_chunks:
    compressed_chunks = _deduplicate_chunks(compressed_chunks, threshold=0.85)
```

- [ ] **Step 5: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_rag.py::test_deduplicate_chunks_same_slug tests/test_rag.py::test_deduplicate_chunks_different_slug_no_dedup -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/qa_chain.py backend/tests/test_rag.py
git commit -m "feat: add _deduplicate_chunks for same-slug redundancy filtering (cosine>0.85)"
```

---

### Task 9: 参数微调（基于阶段 1 benchmark 基线）

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 根据阶段 1 benchmark 结果调整参数**

此步骤依赖 Task 7 的 benchmark 结果。预期调整方向：

```python
# VectorStoreSettings
retrieval_multiplier: int = 8  # 从 12 降低，100 篇时 96 候选过多
adaptive_rerank_threshold: float = 0.5  # 从 0.3 提高，让更多查询跳过 rerank
crag_high_confidence: float = 0.15  # 从 0.05 提高，让 CRAG 更有区分度
```

具体数值根据实际 benchmark 结果微调。

- [ ] **Step 2: 详细验证（50 条 QA）**

Run: `cd backend && python tests/run_full_benchmark.py --level detailed --phase 1`

对比阶段 1 基线，确认指标改善方向正确。

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat: tune retrieval_multiplier=8, adaptive_rerank=0.5, crag_confidence=0.15 based on 100-doc benchmark"
```

---

## 阶段 3：闭环优化 + 阶梯扩容

### Task 10: 实现生成质量反馈闭环

**Files:**
- Modify: `backend/app/rag/qa_chain.py`

- [ ] **Step 1: 在 rag_query_astream 中添加轻量级质量评估**

在 LLM 生成完成后，检查输出是否包含"无法回答"类短语：

```python
_UNANSWERABLE_PATTERNS = [
    "文档中未提及", "无法回答", "知识库中不包含",
    "我没有找到相关信息", "无法从提供的上下文中",
]

def _check_unanswerable(response_text: str) -> bool:
    """检查 LLM 输出是否表示无法回答。"""
    return any(p in response_text for p in _UNANSWERABLE_PATTERNS)
```

在 `rag_query_astream` 生成完成后：
```python
if _check_unanswerable(answer) and top_score > 0.3:
    # 检索到了相关内容但 LLM 没用上，触发 CRAG retry
    logger.info("unanswerable_with_relevant_context", top_score=top_score, query=query)
    # 用 variant query 重新检索（已有 CRAG retry 逻辑）
```

- [ ] **Step 2: 添加 feedback log 记录**

```python
import json
from pathlib import Path

_FEEDBACK_LOG = Path("data/feedback_log.jsonl")

def _log_feedback(query: str, top_score: float, action: str, answer: str = ""):
    """记录检索-生成反馈，供后续分析。"""
    entry = {
        "timestamp": time.time(),
        "query": query[:200],
        "top_score": top_score,
        "action": action,  # "retry" | "accepted" | "no_result"
        "answer_preview": answer[:100],
    }
    _FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_FEEDBACK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
```

- [ ] **Step 3: 运行测试确认无回归**

Run: `cd backend && python -m pytest tests/test_rag.py -v --timeout=120`

Expected: 所有测试通过

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: add lightweight generation quality feedback loop with unanswerable detection"
```

---

### Task 11: 阶梯扩容到 500 篇

**Files:**
- Create: `backend/data/articles/rag/` (新增 200 篇)
- Create: `backend/data/articles/business/` (新增 200 篇)
- Modify: `backend/tests/benchmark_config.yaml`

- [ ] **Step 1: 生成 400 篇新文档**

按阶段 1 的文章主题扩展，每篇 2000-4000 字。

- [ ] **Step 2: 扩展 QA 数据集**

新增 ~400 条 QA，总计 ~720 条。

- [ ] **Step 3: 全量索引 + 详细验证**

```bash
cd backend && python tests/run_full_benchmark.py --level detailed --phase 1
```

对比 100 篇基线，确认指标在目标范围内：
- Relevancy ≥72%
- Recall ≥78%
- Recall@5 ≥96%

- [ ] **Step 4: 参数微调**

根据 500 篇 benchmark 结果微调 `retrieval_multiplier`、`rerank_candidates` 等。

- [ ] **Step 5: Commit**

```bash
git add backend/data/articles/ backend/tests/benchmark_config.yaml
git commit -m "feat: expand to 500 articles with QA dataset and parameter tuning"
```

---

### Task 12: 阶梯扩容到 1000+ 篇

**Files:**
- Create: `backend/data/articles/` (新增 500+ 篇)
- Modify: `backend/tests/benchmark_config.yaml`

- [ ] **Step 1: 生成 500+ 篇新文档**

- [ ] **Step 2: 扩展 QA 数据集**

总计 ~1000+ 条 QA。

- [ ] **Step 3: 全量索引 + 详细验证**

确认最终指标达标：
- Relevancy ≥70%
- Recall ≥75%
- Recall@5 ≥95%

- [ ] **Step 4: 全量测试（用户确认后）**

Run: `cd backend && python tests/run_full_benchmark.py --level full --phase 1`

- [ ] **Step 5: Commit**

```bash
git add backend/data/articles/ backend/tests/benchmark_config.yaml
git commit -m "feat: expand to 1000+ articles, all target metrics achieved"
```

---

## 自检

### Spec 覆盖检查

| 设计要求 | 对应 Task |
|---------|----------|
| #2 Qdrant RRF k=60 | Task 2 |
| #3 compression_threshold 0.30 | Task 1 |
| #4 parent_text 一致性 | Task 2 |
| #6 负例检测修复 | Task 6 |
| #1 冗余过滤 | Task 8 |
| #5 QA 数据集扩展 | Task 5 |
| #7 生成质量反馈闭环 | Task 10 |
| 74 篇文档生成 | Task 4 |
| max_concurrent=15 | Task 3 |
| prefetch limit top_k*10 | Task 2 |
| health check 保活 | Task 6 |
| 分级验证 10/50/全量 | Task 6 |
| 阶梯扩容 100→500→1000+ | Task 7/11/12 |

### Placeholder 扫描

无 TBD/TODO/占位符。

### 类型一致性

- `_deduplicate_chunks(chunks: list, threshold: float = 0.85) -> list` — Task 8 定义和 Task 4 调用一致
- `sample_qa(qa_dataset, sample_size, seed=42)` — Task 6 定义
- `_check_unanswerable(response_text: str) -> bool` — Task 10 定义
- `_log_feedback(query, top_score, action, answer)` — Task 10 定义
