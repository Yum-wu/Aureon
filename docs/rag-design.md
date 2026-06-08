# RAG 知识库系统设计文档

## 架构

```
用户 → [RAG UI] → POST /api/rag/query → [FastAPI Backend]
                                              ↓
                                    [rag.qa_chain.rag_query()]
                                              ↓
                              ┌─────────────────┴─────────────────┐
                              ↓                                   ↓
                      [chroma: retrieve]                    [LLM: generate]
                              ↓                                   ↓
                        相似切片段 ← ─ ← ─ ← ─ ─ 拼接上下文 + 提问
                              ↓                                   ↓
                        [rag.retriever]                      [rag.qa_chain]
                              ↓                                   ↓
                        返回 sources                          返回 answer
                              └─────────────────┬─────────────────┘
                                                ↓
                                    POST /api/rag/query 响应
                                                ↓
                                     [RAG UI] 展示问答+来源
```

## 模块说明

### `app/rag/loader.py`
加载 MyBlog Markdown 博文，解析 YAML frontmatter，按章节切片。

### `app/rag/vector_store.py`
ChromaDB 初始化、文档索引、持久化管理。支持 BM25 + Vector 混合检索（RRF 融合）。

### `app/rag/retriever.py`
混合检索 + Reranker 精排（bge-reranker-v2-m3 cross-encoder），支持 top_k、自适应跳过、多样性重排。

### `app/rag/qa_chain.py`
RAG pipeline 主流程：检索 → 拼接上下文 → 调用 LLM 生成 → 返回带来源的答案。

### `app/rag/evaluator.py`
RAG 评估模块：Recall@k、MRR、nDCG@10、Faithfulness（LLM-as-judge 0-10 评分）、延迟统计（p50/p99/mean/min/max）。通过 `run_full_evaluation()` 统一运行。

### `app/rag/prompt_experiment.py`
Prompt 策略实验框架：三种 System Prompt 模板（Direct / CoT / Few-shot），`run_experiment()` 对同一组问题分别调用并输出对比表格。

### `app/rag/test_data.py`
评估数据集：从 `backend/data/articles/` 的 26 篇文章标注 192 组 Q&A 对（24 factual + 92 reasoning + 42 synthesis + 14 cross-article + 20 negative），含 `RETRIEVAL_EXPECTED` 映射用于 Recall 评估。

### `app/rag/models.py`
Pydantic 请求/响应模型。

## API

| 方法 | 路径 | 说明 |
| POST | /api/rag/query | 查询知识库，返回回答+来源 |
| POST | /api/rag/index | 重新索引博文，用于数据更新后 |
| POST | /api/rag/evaluate | 运行全量评估（Recall + Faithfulness + 延迟）|
| POST | /api/rag/experiment | 运行 Prompt 策略对比实验 |

## 评估结果（2026-06-08 v31）

### 检索质量

| 指标 | Hybrid | BM25 | Dense | 目标 |
|------|:---:|:---:|:---:|:---:|
| Recall@3 | 96.5% | 95.9% | 93.6% | ≥ 80% ✅ |
| Recall@5 | 100% | 97.1% | 94.8% | ≥ 90% ✅ |
| Recall@10 | 100% | 98.8% | 97.7% | ≥ 95% ✅ |
| MRR | 0.901 | 0.907 | 0.866 | ≥ 0.85 ✅ |
| nDCG@10 | 0.914 | — | — | ≥ 0.85 ✅ |

### 延迟性能

| 方法 | P50 | P99 | Mean |
|------|:---:|:---:|:---:|
| BM25 | 1.8ms | 2.7ms | 1.9ms |
| Vector | 142.9ms | 177.9ms | 143.9ms |
| Hybrid | 154.3ms | 191.4ms | 156.2ms |

### 分类检索表现

| 类型 | Recall@3 | 数量 |
|------|:---:|:---:|
| Reasoning | 97.8% | 92 |
| Synthesis | 97.6% | 42 |
| Factual | 95.8% | 24 |
| Cross-article | 85.7% | 14 |
| Negative | — | 20 (不参与 Recall) |

### 并发负载测试

| 并发数 | QPS | Mean Latency | P99 |
|:---:|:---:|:---:|:---:|
| 1 | 4.6 | 215ms | 178ms |
| 5 | 9.5 | 526ms | 775ms |
| 10 | 9.6 | 1,029ms | 1,526ms |
| 20 | 9.5 | 2,066ms | 2,794ms |

Recall 在并发下保持 96.5% 不退化。

## 关键决策

- **ChromaDB**：本地轻量，无需单独部署，适合入门学习
- **RecursiveCharacterTextSplitter**：chunk_size=500, overlap=50，适合中文 Markdown
- **Hybrid Search (RRF)**：BM25 关键词检索 + Vector 向量检索 → Reciprocal Rank Fusion 融合
- **Reranker 精排**：bge-reranker-v2-m3 cross-encoder，RRF 后精排，自适应跳过
- **sentence-transformers**：本地 Embedding fallback，避免 API 依赖
- **Adaptive Embedding**：CPU/GPU 自动调度（batch<4→CPU, batch≥4→GPU）
- **Agent Tool 集成**：`knowledge_retrieval` Tool 注册到 ALL_TOOLS，Agent 自动可调用
- **Chat + RAG 自动集成**：LangGraph 流式工作流，意图分类关键词匹配 → RAG/Chat 路由 → LLM 流式生成
- **192 QA 大规模测试集**：覆盖 factual/reasoning/synthesis/cross-article/negative 五类

## 评估方法

- Recall@k：对 192 个标注问题，检查 top-k 检索结果是否包含正确答案片段
- MRR：Mean Reciprocal Rank，衡量首个正确结果的排名
- nDCG@10：Normalized Discounted Cumulative Gain，综合排序质量
- Faithfulness：LLM-as-judge 评分（0-10），检查 LLM 回答是否忠实于检索到的上下文
- 并发负载：1/5/10/20 并发度下测试 QPS 和延迟稳定性
- 延迟：记录检索的端到端耗时，统计 p50/p99/mean
