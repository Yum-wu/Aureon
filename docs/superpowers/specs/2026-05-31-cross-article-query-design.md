# Cross-Article Query Enhancement

**Date:** 2026-05-31
**Status:** Approved
**Scope:** Backend RAG retrieval pipeline only

---

## Problem

Cross-article queries ("两篇文章的共同点是什么？", "比较 X 和 Y") fail because the current retrieval pipeline targets a single source article. Recall@3 drops from 97.4% to ~85% on these queries.

## Constraints

- Zero additional LLM API calls (default mode)
- Latency increase < 10ms over current ~4ms baseline
- No changes to existing simple query path
- Must be toggle-able via environment variable

## Design

### Architecture

```
Query → Intent Detection (rules, <1ms)
  ├── Simple → hybrid_retrieve(top_k) [existing path, unchanged]
  └── Cross-article → expand_queries(rules)
        → hybrid_retrieve(top_k*2) per variant [parallel]
        → RRF fusion across all variants
        → diversity select top_k
```

### 1. Intent Detection (`qa_chain.py`)

Rule-based detection, zero LLM cost. Bilingual patterns (zh + en):

```python
CROSS_ARTICLE_PATTERNS_ZH = [
    "比较", "对比", "区别", "差异", "异同",
    "共同点", "相同", "相似", "类似",
    "两篇", "多篇", "哪些文章", "所有文章",
    "综合", "总结", "汇总",
]

CROSS_ARTICLE_PATTERNS_EN = [
    "compare", "comparison", "difference", "differences",
    "common", "commonalities", "similarities", "similar",
    "between", "across articles", "across documents",
    "all articles", "all documents", "both articles",
    "summarize", "summarise", "overview",
]
```

Detection: lowercased query matched against either set → cross-article mode. Falls back to simple path otherwise.

### 2. Rule-Based Query Expansion (`query_rewriter.py`)

New function `expand_queries_rules(query) -> List[str]`:

- Split query at bilingual conjunction markers
  - ZH: "和", "与", "以及", "对比", "比较"
  - EN: "and", "vs", "versus", "compared to", "compared with"
- Extract named entities (article slugs from metadata, case-insensitive for EN)
- Generate keyword-focused variants (not full sentences)

Examples:
| Input | Variants |
|-------|----------|
| "两篇文章的共同点是什么" | ["技术实战经验", "具体数据问题清单"] |
| "比较 LangChain 和 LlamaIndex" | ["LangChain RAG", "LlamaIndex RAG"] |
| "compare LangChain and LlamaIndex RAG" | ["LangChain RAG", "LlamaIndex RAG"] |
| "differences between React and Vue" | ["React performance", "Vue performance"] |
| "所有文章的部署方案" | ["部署方案", "Docker Railway 部署"] |

If LLM mode enabled (`QUERY_EXPAND_LLM=true`): use existing `expand_queries()` with LLM.

### 3. Multi-Query Retrieval (`qa_chain.py`)

New function `multi_query_retrieve(query, top_k=3)`:

1. Detect intent
2. If cross-article: expand to 2-3 variants via rules
3. For each variant: run `hybrid_retrieve(top_k * 2)` in parallel
4. RRF fusion across all result sets
5. Diversity select (existing `_simple_diversity`) for final top_k

### 4. Integration Point

Modify `rag_query_astream()` and `rag_query()` in `qa_chain.py`:

```python
# Before (current)
chunks = hybrid_retrieve(query, top_k=top_k)

# After
chunks = multi_query_retrieve(query, top_k=top_k)
```

The `multi_query_retrieve` function internally calls `hybrid_retrieve` for simple queries (no-op path), so existing behavior is preserved.

## Files Changed

| File | Change |
|------|--------|
| `backend/app/rag/query_rewriter.py` | Add `expand_queries_rules()` function |
| `backend/app/rag/qa_chain.py` | Add `multi_query_retrieve()`, modify `rag_query`/`rag_query_astream` |
| `backend/app/rag/test_data.py` | Add 5-10 cross-article QA pairs |
| `backend/tests/test_rag_retrieval.py` | Add tests for multi-query retrieval |
| `目标.md` | Update Recall@3 metrics |

## Latency Budget

| Component | Simple Query | Cross-Article |
|-----------|-------------|---------------|
| Intent detection | <1ms | <1ms |
| Query expansion | 0 | <1ms (rules) |
| Retrieval | ~4ms (parallel BM25+Vector) | ~5ms (3 variants parallel, same wall clock) |
| RRF fusion | ~0.2ms | ~0.5ms |
| **Total** | **~4ms** | **~6-8ms** |

## Testing

1. Unit tests for `expand_queries_rules()` with various query patterns
2. Unit tests for `multi_query_retrieve()` mock path
3. Integration test: run full benchmark with new cross-article QA pairs
4. Latency regression test: ensure simple query path unchanged

## Rollback

Environment variable `MULTI_QUERY_ENABLED=false` (default: true) disables the feature entirely. All code paths revert to current behavior.
