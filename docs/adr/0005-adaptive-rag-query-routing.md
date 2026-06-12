# ADR-0005: 查询路由 Adaptive-RAG

## 状态：已批准

## 上下文

当前所有查询都走 `multi_query_retrieve → hybrid_retrieve` 完整 pipeline，即使是简单的关键词查询也走完整流程，导致：
- 简单查询延迟高（300-500ms vs 可达 <10ms）
- 不必要的 LLM 调用（multi_query 生成变体查询）
- 不必要的 API 成本

项目已有 `query_classifier.py` 但未用于路由决策。

## 决策

基于 Adaptive-RAG 论文（arXiv:2403.14403）实现查询路由：

```python
def route_query(query, complexity):
    if complexity == "simple":    # 事实型：纯 sparse/BM25
        return sparse_retrieve(query, top_k=3)       # <10ms
    elif complexity == "medium":  # 分析型：hybrid retrieve
        return hybrid_retrieve(query, top_k=5)        # 100-200ms
    else:                         # 推理型：完整 pipeline
        return multi_query_retrieve(query, top_k=7)   # 300-500ms
```

复用现有 `query_classifier.py` 的复杂度分类结果。

## 依据

- Adaptive-RAG 论文（arXiv:2403.14403）：基于查询复杂度的自适应检索路由
- Self-RAG 论文（arXiv:2310.11511）：[retrieve]/[no-retrieve] reflection token
- 简单查询占生产流量 ~50%，路由可节省大量延迟和成本

## 后果

- 简单查询延迟降低 80%（300ms → <10ms）
- 减少 ~50% 的 LLM 调用（简单查询不走 multi_query）
- 需要校准 query_classifier 的分类阈值
- 需要监控路由准确率，避免简单查询被误判为复杂
