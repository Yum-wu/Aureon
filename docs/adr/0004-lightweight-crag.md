# ADR-0004: 轻量评估器替代 LLM CRAG

## 状态：已批准

## 上下文

当前 CRAG 实现使用 LLM 调用评估检索质量，在流式路径（生产主路径）被禁用，注释 "too many false positives"。

问题分析：
- CRAG 阈值 `crag_high_confidence=0.05`, `crag_low_confidence=0.01` 极低
- 用 LLM 做评估器成本高（每次查询多 1 次 LLM 调用）+ 延迟大（+1-2s）
- CRAG 论文（arXiv:2401.15884）的评估器是轻量 T5 模型，不是大 LLM

## 决策

用 embedding 相似度做轻量评估器替代 LLM CRAG：

```python
def lightweight_crag_assess(query_embedding, chunk_embeddings, chunks):
    """基于 embedding 相似度的轻量 CRAG 评估器"""
    similarities = cosine_similarity(query_embedding, chunk_embeddings)
    max_sim = max(similarities)
    mean_sim = np.mean(top_k_similarities(similarities, k=3))

    if max_sim > HIGH_CONFIDENCE_THRESHOLD:  # e.g. 0.8
        return "correct", chunks  # 直接使用
    elif max_sim > LOW_CONFIDENCE_THRESHOLD:  # e.g. 0.5
        return "ambiguous", chunks  # 补充 web search 或扩展检索
    else:
        return "incorrect", []  # 丢弃，返回无结果
```

阈值需基于 benchmark 数据校准。

## 依据

- CRAG 论文（arXiv:2401.15884）核心是轻量评估器，不是 LLM 调用
- Embedding 相似度是检索质量的直接代理指标
- 延迟仅 +50-100ms（vs LLM 的 +1-2s）
- 无额外 API 成本（query embedding 已在检索时计算）

## 后果

- CRAG 可在生产流式路径启用
- 延迟从 +1-2s 降至 +50-100ms
- 无额外 LLM API 成本
- 需要基于 benchmark 数据校准阈值
- 精度略低于 LLM 评估（但比禁用 CRAG 好）
