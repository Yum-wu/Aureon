# Aureon — 项目上下文

## 领域语言

| 术语 | 含义 |
|---|---|
| Agent | LangGraph `CompiledStateGraph`，Tool Calling + 四层记忆 |
| L0-L3 | 对话原始记录 → 原子事实 → 场景总结 → 用户画像 |
| RAG | Qdrant 向量库 + Hybrid Search + Adaptive-RAG 查询路由 |
| Ingestion | 文档摄取管线：extractor → normalizer → chunk policy → quality gate → index writer |
| ChunkRecord | 分块后中间数据模型，`to_dict()` 转换后喂给 `add_to_index` |
| Quality Gate | `is_valid_chunk`(长) + `is_informative_chunk`(密度) + `deduplicate_chunks`(去重) |
| PII | Fernet 加密存储 SSO secret / LLM key |
| RBAC | JWT + `require_role()` 依赖，三角色：VIEWER / EDITOR / ADMIN |

## 项目结构要点

```
backend/app/rag/
  ingestion/          ← 本次新增的核心模块
    extractors.py     # 5 类型独立抽取
    normalizer.py     # 空白归一化
    models.py         # IngestedDocument / ChunkRecord
    policy.py         # 段落聚合分块 + section_path
    quality.py        # 质量门禁
    pipeline.py       # build_chunks / chunks_to_dicts
  loader.py           # load_single_document + 遗留包装函数
  indexer.py          # run_incremental_index / run_index_pipeline
  index_manager.py    # Qdrant add_to_index / delete_from_index
  qa_chain.py         # RAG 查询管线（HyDE → 检索 → CRAG → 生成）
```

## 关键架构决策

| 决策 | 理由 |
|---|---|
| ingestion 独立子包（不分摊到 loader） | 单一职责，易于替换和测试 |
| 类型分流抽取，不统一读入 | 保留结构信息（标题层级、表格、sheet） |
| `ChunkRecord` dataclass + `to_dict()` | 内部用类型安全对象，外部接口用 dict |
| 段落聚合分块（512 char） | 更稳定，可预测 |
| `run_index_pipeline` 保留旧路径 | 避免改动父块/子块/contextual prefix 链路风险 |
| ParentChildSplitter 统一 chunking（2026-06-30） | 替代 3 处内联 parent-child 循环，统一 parent_size=1500, child_size=512, overlap=80 |

## 已知限制

- PDF 页码元数据未保留（整页合并）
- DOCX 表格未单独成块
- XLSX sheet 名未保留
- `semantic_chunking` 代码路径已移除（2026-06-30，从未启用）

## 测试状态

后端 958 passed / 5 skipped（2026-06-30），前端 287 passed (35 files) / CI auto-run。
