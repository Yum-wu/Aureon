# RAG 评估报告

**日期**: 2026-06-05T16:03:49.444160
**数据集**: 2026-06-04 (27 QA)
**RAG 版本**: main@4a9033d
**系统配置**: DashScope text-embedding-v3 / deepseek-v4-flash / chroma

**最近改动**:
- 4a9033d docs: update design spec and analysis report with actual DeepEval results
- 893f0f7 fix: DeepEval integration working with DeepSeek API
- c9c33df feat: enterprise RAG evaluation framework with DeepEval integration
- 14a8d3f feat: full E2E benchmark + DashScope index rebuild + vector threshold fix
- b1e370c feat: add Redis embedding cache to reduce API calls

## 检索质量

| 指标 | 分数 | 阈值 | 状态 |
|------|------|------|------|
| Recall@3 | 0.789 | ≥0.85 | ⚠️ |
| Recall@5 | 0.789 | ≥0.85 | ⚠️ |
| Context Precision | 0.704 | ≥0.70 | ✅ |
| Context Recall | 0.000 | ≥0.75 | ⚠️ |
| Context Relevancy | 0.374 | ≥0.70 | ⚠️ |

## 生成质量

| 指标 | 分数 | 阈值 | 状态 |
|------|------|------|------|
| Faithfulness | 0.963 | ≥0.70 | ✅ |
| Answer Relevancy | 0.878 | ≥0.60 | ✅ |
| Hallucination | 0.037 | ≤0.20 | ✅ |

## 延迟

| 指标 | 值 |
|------|-----|
| P50 | 4800ms |
| P99 | 6013ms |
| Mean | 4877ms |

## 总结

- **DeepEval Pass Rate**: 80%
- **评估耗时**: 247.3s