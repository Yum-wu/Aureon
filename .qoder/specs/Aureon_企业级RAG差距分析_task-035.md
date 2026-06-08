# Aureon 企业级 RAG 差距分析与优化方案

## Context

Aureon 是一个 FastAPI + React 19 的企业 AI 知识库平台，已实现混合检索（BM25+向量+RRF）、四层记忆、LangGraph 工作流、WebSocket 实时聊天等能力。通过对比 LlamaIndex、Dify、RAGFlow、Haystack、GraphRAG 等 10+ 企业级 RAG 框架，结合代码深度审查和架构审查，发现以下核心差距：

**当前指标**: Recall@3=95.1% | MRR=0.913 | QPS≈6 | P99≈3.8s | 26 文档 / 476 chunks

---

## 行业对标矩阵

| 维度 | Aureon 现状 | 行业标杆 | 差距等级 |
|------|-----------|---------|---------|
| 检索质量 | Hybrid+RRF+Rerank, Recall@3=95.1% | LlamaIndex: Hybrid+RRF+Cross-encoder, Recall 95%+ | **接近** |
| Chunking | 固定+语义分割 | Parent-Child / Hierarchical / Late Chunking | **中等** |
| 查询理解 | 简单 strip + multi-query | HyDE / Query Routing / Step-back / Self-RAG | **大** |
| 并发性能 | QPS≈6, 单进程 | Dify/RAGFlow: QPS 50-500, 水平扩展 | **极大** |
| 评估体系 | Recall+MRR+nDCG | RAGAS: Faithfulness+Answer Relevancy+Context Precision | **大** |
| 向量库 | ChromaDB (单 collection) | Qdrant/Pinecone: 多租户 partition, payload index | **大** |
| 企业治理 | 单 API Key | 多租户/RBAC/审计/SSO | **极大** |
| 可观测性 | structlog+Prometheus（未集成） | OpenTelemetry 全链路追踪 | **中等** |
| 文档处理 | Markdown only | PDF/Word/HTML/表格/OCR | **中等** |

---

## Phase 1: 代码质量修复（P0, 1-2 周）

修复审查中发现的 Critical 级别问题，消除生产隐患。

### Task 1.1: 线程安全 — 全局变量加锁
- **文件**: `backend/app/rag/vector_store.py`
- **问题**: `_embed_cache`, `_kw_docs`, `_kw_idf`, `_chroma_collection` 等全局变量无线程同步，并发请求存在数据竞争
- **修复**: 为关键全局变量添加 `threading.Lock`

### Task 1.2: save_index 双重 embedding
- **文件**: `backend/app/rag/vector_store.py` (L793-L843)
- **问题**: `save_index()` 接受 `embeddings` 参数但从未使用，ChromaDB 通过 `ZhipuEmbeddingFn` 重新计算所有 embedding，成本和延迟翻倍
- **修复**: 将预计算的 embeddings 传递给 `collection.add(embeddings=...)`

### Task 1.3: ChromaDB ID 碰撞
- **文件**: `backend/app/rag/vector_store.py` (L645-L646)
- **问题**: 使用 `f"chunk_{existing_count + i}"` 生成 ID，删除后 count 回退导致重复 ID 覆盖
- **修复**: 改用 content-hash 或 UUID 生成确定性唯一 ID

### Task 1.4: 事件循环阻塞
- **文件**: `backend/app/rag/qa_chain.py` (L1416), `backend/app/rag/vector_store.py` (L450)
- **问题**: `rag_query_async` 调用同步 `classify_query_answerable_sync`；`_embed_api` 使用 `requests.post` + `time.sleep` 在异步上下文中阻塞
- **修复**: 使用 `asyncio.to_thread` 包裹同步调用，或切换到 `httpx.AsyncClient`

### Task 1.5: SSE finally 中的 yield
- **文件**: `backend/app/routers/rag.py` (L273-L286)
- **问题**: `finally` 块中 `yield sse_event({'type': 'done'})` 在客户端断连时引发 `RuntimeError`
- **修复**: 将 `yield` 移出 `finally`，在 `try` 块正常退出路径发送

### Task 1.6: Jina Reranker Header 拼写
- **文件**: `backend/app/rag/ensemble_reranker.py` (L425)
- **问题**: `"Content--Type"` 双横线导致 API 调用失败，被 try/except 静默吞掉
- **修复**: 改为 `"Content-Type"`

### Task 1.7: MemoryManager 优雅关闭
- **文件**: `backend/app/memory/manager.py` (L120-L124)
- **问题**: `_periodic_cleanup` 在 `CancelledError` 时重启 task，导致关闭失败
- **修复**: 让 `CancelledError` 正常传播，不重启

### Task 1.8: Redis 重连永久停止
- **文件**: `backend/app/cache/redis_client.py` (L103-L138)
- **问题**: 连续失败 6 次后 `_redis_fail_count` 永远 >= `_RECONNECT_AFTER`，重连机制永久停止
- **修复**: 在 reset 路径中正确重置计数器

---

## Phase 2: 性能与并发优化（P1, 2-4 周）

### Task 2.1: SQLite → PostgreSQL 迁移
- **文件**: `backend/app/memory/db.py`, 新增 `backend/app/memory/pg.py`
- **问题**: SQLite 单写者模型，无法多实例扩展，100+ 并发写锁争用
- **方案**: 
  1. 引入 `SQLAlchemy[asyncio]` + `asyncpg`
  2. 优先迁移 `query_traces`、`conversations` 高频写表
  3. 保留 SQLite 仅用于本地 offload 缓存

### Task 2.2: ChromaDB → Qdrant 迁移
- **文件**: `backend/app/rag/vector_store.py`
- **问题**: ChromaDB 单 collection 无法支持多租户、payload filtering 性能差
- **方案**: 
  1. 将 Qdrant 设为主存储（已有代码骨架）
  2. 使用 payload index 实现 filter-based delete（替代 O(N) 全量扫描）
  3. 按 `tenant_id` 实现 collection 分区

### Task 2.3: Uvicorn 多 Worker + 自定义线程池
- **文件**: `backend/Dockerfile`, `docker-entrypoint.sh`
- **问题**: 单 Worker 限制并发；LangGraph 工作流每请求占 3-4 个线程
- **修复**: 配置 `--workers 4` + 自定义 `ThreadPoolExecutor(max_workers=64)`

### Task 2.4: 断路器模式
- **文件**: 新增 `backend/app/reliability/circuit_breaker.py`
- **问题**: LLM API 持续不可用时，每次请求仍重试 3 次（16 秒），100 并发 = 全部堆积
- **方案**: 引入 `pybreaker`，连续 5 次失败后 60 秒内快速失败

### Task 2.5: Agent 实例缓存
- **文件**: `backend/app/langgraph/nodes/agent.py`
- **问题**: 每次请求创建新 LLM + Agent 实例
- **修复**: 参考 `chat.py` 的 `_get_agent()` 缓存模式

---

## Phase 3: 检索质量与评估体系升级（P1, 2-4 周）

### Task 3.1: 集成 RAGAS 评估框架
- **文件**: `backend/app/rag/evaluator.py`, `backend/tests/test_rag_quality.py`
- **问题**: 缺少 Faithfulness、Answer Relevance、Context Precision 量化数据
- **方案**: 
  1. 安装 `ragas` 库
  2. 实现 `evaluate_faithfulness()`, `evaluate_answer_relevance()`, `evaluate_context_precision()`
  3. 集成到 CI 的 `rag-quality.yml` 工作流

### Task 3.2: 查询理解增强
- **文件**: `backend/app/rag/query_rewriter.py`
- **问题**: 当前仅简单 strip 停用词 + multi-query，缺少 HyDE、Self-RAG、Query Routing
- **方案**:
  1. 实现 HyDE（Hypothetical Document Embedding）：LLM 先生成假设答案，用答案 embedding 检索
  2. 实现 Query Classification：区分 factual / analytical / creative 类型，路由不同策略
  3. 修复 `_ZH_STRIP` 中文停用词过于激进的问题

### Task 3.3: Parent-Child Chunking
- **文件**: `backend/app/rag/semantic_splitter.py`, `backend/app/rag/vector_store.py`
- **问题**: 当前固定 + 语义分割，缺少层级检索
- **方案**: 
  1. 实现 Parent-Child 索引：大 chunk 存储 + 小 chunk 检索
  2. 检索时先匹配小 chunk，返回对应的大 chunk 作为上下文

### Task 3.4: 流式检索异步化
- **文件**: `backend/app/rag/qa_chain.py` (L763)
- **问题**: `rag_query_astream` 内部调用同步 `multi_query_retrieve`，embedding API 阻塞首 token
- **修复**: 切换到 `hybrid_retrieve_async` + `asyncio.to_thread`

### Task 3.5: compress_context embedding 复用
- **文件**: `backend/app/rag/qa_chain.py` (L96-L120)
- **问题**: 每次查询重新计算 chunk embeddings（检索阶段已计算过）
- **修复**: 在 chunk dict 中保存 `_embedding`，compress 阶段复用

---

## Phase 4: 企业治理能力建设（P2, 4-8 周）

### Task 4.1: 多租户隔离
- **文件**: 全局改动
- **方案**:
  1. 认证层引入 `tenant_id`
  2. 向量存储按 `tenant_id` 分区（Qdrant payload filtering）
  3. 缓存 key 添加 `tenant_id` 前缀
  4. BM25 索引按租户隔离

### Task 4.2: RBAC 权限体系
- **文件**: `backend/app/security/`, `backend/app/main.py`
- **方案**:
  1. JWT 认证中间件替代单一 API Key
  2. 角色权限矩阵: viewer(只读) / editor(+上传) / admin(+索引重建/配置)
  3. 连接 SSO 模块到核心认证路径

### Task 4.3: 审计日志系统
- **文件**: 新增 `backend/app/audit/`
- **方案**:
  1. `audit_logs` 表: (tenant_id, user_id, action, resource_type, resource_id, metadata, ip, created_at)
  2. 装饰器自动记录所有写操作
  3. append-only，不可删除

### Task 4.4: 数据血缘追踪
- **文件**: `backend/app/observability/__init__.py`, `backend/app/rag/models.py`
- **问题**: `QueryTracer` 已实现但未集成到请求路径；`SourceItem` 缺少 chunk_id
- **修复**:
  1. 在 RAG/Chat 端点中集成 QueryTracer
  2. `SourceItem` 添加 `chunk_id` 和 `chunk_text_snippet`

---

## Phase 5: 可观测性与部署加固（P2, 2-3 周）

### Task 5.1: OpenTelemetry 集成
- 添加 span: HTTP → 检索 → 重排 → LLM → 缓存
- request_id 传播到所有子调用

### Task 5.2: API 版本控制
- 所有路由迁移至 `/api/v1/` 前缀
- 列表端点添加分页

### Task 5.3: 部署加固
- 后端容器添加 HEALTHCHECK
- docker-compose 添加资源限制 (memory: 4g, cpus: 2.0)
- 修复 docker-compose 默认密码
- 移除 query param API Key 传递
- WebSocket 添加认证 + 连接数限制

### Task 5.4: 统一错误响应
- HTTPException 统一迁移到 AureonException 子类
- 错误格式: `{"error": "...", "detail": "...", "request_id": "..."}`

---

## 验证方案

### 代码质量验证
```bash
# 后端单元测试
cd backend && python -m pytest tests/ -v

# 类型检查
cd backend && python -m mypy app/ --ignore-missing-imports
```

### 性能验证
```bash
# 并发 benchmark
cd backend && python tests/benchmark_e2.py --concurrency 10,20,50

# 目标: QPS >= 20 (并发10), P99 <= 2s (并发10)
```

### RAG 质量验证
```bash
# RAGAS 评估
cd backend && python -m pytest tests/test_rag_quality.py -v

# 目标: Faithfulness >= 0.85, Answer Relevance >= 0.80
```

### 企业特性验证
- 多租户: 创建 2 个 tenant，验证数据隔离
- RBAC: viewer 角色尝试删除文件应返回 403
- 审计: 检查 audit_logs 表是否有完整操作记录

---

## 优先级总结

| 阶段 | 时间 | 核心目标 | 阻塞项 |
|------|------|---------|--------|
| **Phase 1** | 1-2 周 | 修复 Critical Bug | 无 — 可立即开始 |
| **Phase 2** | 2-4 周 | QPS 50+, 水平扩展 | 依赖 Phase 1 |
| **Phase 3** | 2-4 周 | RAGAS 评估 + 高级检索 | 可与 Phase 2 并行 |
| **Phase 4** | 4-8 周 | 多租户/RBAC/审计 | 依赖 Phase 2 (PG 迁移) |
| **Phase 5** | 2-3 周 | 可观测性+部署加固 | 可与 Phase 4 并行 |

**全流程**: 约 12-20 周