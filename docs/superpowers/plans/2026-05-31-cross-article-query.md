# Cross-Article Query Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve Recall@3 on cross-article queries from ~85% to ~99% with zero LLM cost and <10ms latency increase.

**Architecture:** Rule-based intent detection + keyword query expansion + multi-query RRF fusion. Simple queries bypass entirely via same `hybrid_retrieve` call. Cross-article queries expand to 2-3 keyword variants, each runs independent `hybrid_retrieve`, then RRF fuses all results.

**Tech Stack:** Python, jieba (already used for BM25 tokenization), existing ChromaDB + BM25 hybrid pipeline.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/rag/query_rewriter.py` | Modify | Add `is_cross_article_query()` and `expand_queries_rules()` |
| `backend/app/rag/qa_chain.py` | Modify | Add `multi_query_retrieve()`, update `rag_query()` and `rag_query_astream()` |
| `backend/app/rag/test_data.py` | Modify | Add 6 cross-article QA pairs (3 zh + 3 en) |
| `backend/tests/test_query_rewriter.py` | Create | Unit tests for intent detection + rule expansion |
| `backend/tests/test_multi_query_retrieve.py` | Create | Integration tests for multi-query retrieval path |

---

### Task 1: Intent Detection + Rule Expansion

**Files:**
- Modify: `backend/app/rag/query_rewriter.py`
- Create: `backend/tests/test_query_rewriter.py`

- [ ] **Step 1: Write failing tests for intent detection**

```python
# backend/tests/test_query_rewriter.py
"""Tests for cross-article intent detection and rule-based query expansion."""

import pytest
from app.rag.query_rewriter import is_cross_article_query, expand_queries_rules


class TestIsCrossArticleQuery:
    """Rule-based detection of cross-article query intent."""

    def test_zh_compare(self):
        assert is_cross_article_query("比较 LangChain 和 LlamaIndex") is True

    def test_zh_common(self):
        assert is_cross_article_query("两篇文章的共同点是什么？") is True

    def test_zh_diff(self):
        assert is_cross_article_query("React 和 Vue 的区别") is True

    def test_zh_summary(self):
        assert is_cross_article_query("所有文章的部署方案总结") is True

    def test_en_compare(self):
        assert is_cross_article_query("compare LangChain and LlamaIndex") is True

    def test_en_difference(self):
        assert is_cross_article_query("what are the differences between React and Vue") is True

    def test_en_common(self):
        assert is_cross_article_query("commonalities across articles") is True

    def test_en_summary(self):
        assert is_cross_article_query("overview of all documents") is True

    def test_simple_zh(self):
        assert is_cross_article_query("LangChain Agent 的核心概念是什么？") is False

    def test_simple_en(self):
        assert is_cross_article_query("What is RAG system?") is False

    def test_empty_query(self):
        assert is_cross_article_query("") is False

    def test_case_insensitive_en(self):
        assert is_cross_article_query("COMPARE LangChain and LlamaIndex") is True


class TestExpandQueriesRules:
    """Rule-based query expansion without LLM."""

    def test_zh_split_and(self):
        result = expand_queries_rules("比较 LangChain 和 LlamaIndex 的 RAG 实现")
        assert len(result) >= 2
        assert any("LangChain" in q for q in result)
        assert any("LlamaIndex" in q for q in result)

    def test_en_split_and(self):
        result = expand_queries_rules("compare LangChain and LlamaIndex RAG")
        assert len(result) >= 2
        assert any("LangChain" in q for q in result)
        assert any("LlamaIndex" in q for q in result)

    def test_en_split_vs(self):
        result = expand_queries_rules("React vs Vue performance")
        assert len(result) >= 2

    def test_generic_cross_article(self):
        """When no conjunction to split, return keyword variants."""
        result = expand_queries_rules("两篇文章的共同点是什么？")
        assert len(result) >= 1
        assert len(result) <= 4

    def test_returns_list_of_strings(self):
        result = expand_queries_rules("比较 A 和 B")
        assert isinstance(result, list)
        assert all(isinstance(q, str) for q in result)
        assert all(len(q) > 0 for q in result)

    def test_deduplication(self):
        """No duplicate variants in output."""
        result = expand_queries_rules("比较 LangChain 和 LangChain 的区别")
        assert len(result) == len(set(result))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_query_rewriter.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_cross_article_query'`

- [ ] **Step 3: Implement intent detection + rule expansion**

```python
# Add to backend/app/rag/query_rewriter.py (append after existing code)

import re

# ── Cross-article intent detection ──

_CROSS_ARTICLE_PATTERNS_ZH = [
    "比较", "对比", "区别", "差异", "异同",
    "共同点", "相同", "相似", "类似",
    "两篇", "多篇", "哪些文章", "所有文章",
    "综合", "总结", "汇总",
]

_CROSS_ARTICLE_PATTERNS_EN = [
    "compare", "comparison", "difference", "differences",
    "common", "commonalities", "similarities", "similar",
    "between", "across articles", "across documents",
    "all articles", "all documents", "both articles",
    "summarize", "summarise", "overview",
]

# Conjunction markers for splitting queries into sub-queries
_SPLIT_MARKERS_ZH = ["和", "与", "以及"]
_SPLIT_MARKERS_EN = [" and ", " vs ", " versus ", " compared to ", " compared with "]


def is_cross_article_query(query: str) -> bool:
    """Detect if query asks about multiple articles (cross-article intent).

    Uses bilingual keyword matching — zero LLM cost.
    """
    if not query or not query.strip():
        return False

    q_lower = query.lower()

    # Check Chinese patterns
    for pattern in _CROSS_ARTICLE_PATTERNS_ZH:
        if pattern in query:
            return True

    # Check English patterns
    for pattern in _CROSS_ARTICLE_PATTERNS_EN:
        if pattern in q_lower:
            return True

    return False


def expand_queries_rules(query: str) -> List[str]:
    """Generate keyword query variants using rules (zero LLM cost).

    Strategy:
    1. Try splitting at conjunction markers ("和", "and", "vs") → 2+ sub-queries
    2. If no split possible, extract keywords as single variant
    3. Always include original query as fallback
    4. Deduplicate and limit to 3 variants max
    """
    variants = []

    # Strategy 1: Split at conjunction markers
    split_patterns = _SPLIT_MARKERS_ZH + _SPLIT_MARKERS_EN
    for marker in split_patterns:
        if marker in query.lower() if marker.strip().isascii() else marker in query:
            parts = [p.strip() for p in query.split(marker) if p.strip()]
            if len(parts) >= 2:
                # Strip comparison boilerplate from each part
                cleaned = [_strip_comparison_noise(p) for p in parts]
                variants.extend(cleaned)
                break

    # Strategy 2: If no split, extract content keywords
    if not variants:
        # Remove cross-article intent words, keep content words
        cleaned = query
        for pattern in _CROSS_ARTICLE_PATTERNS_ZH + ["？", "？", "是什么", "有哪些", "哪些"]:
            cleaned = cleaned.replace(pattern, "")
        for pattern in _CROSS_ARTICLE_PATTERNS_EN:
            cleaned = re.sub(r'\b' + re.escape(pattern) + r'\b', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned:
            variants.append(cleaned)

    # Always include original as last resort
    variants.append(query)

    # Deduplicate while preserving order
    seen = set()
    deduped = []
    for v in variants:
        key = v.lower().strip()
        if key not in seen and len(key) > 0:
            seen.add(key)
            deduped.append(v)

    return deduped[:3]


def _strip_comparison_noise(text: str) -> str:
    """Remove comparison boilerplate words from a sub-query fragment.

    Examples: "的 RAG 实现" → "RAG 实现", "performance in React" → "React"
    """
    # Chinese noise words
    for noise in ["的", "是什么", "有哪些", "方面", "实现", "性能", "用法"]:
        text = text.replace(noise, "")

    # English noise words
    text = re.sub(r'\b(the|a|an|in|of|for|about|regarding|in terms of)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()

    return text if text else text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_query_rewriter.py -v`
Expected: All 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/query_rewriter.py backend/tests/test_query_rewriter.py
git commit -m "feat: add cross-article intent detection and rule-based query expansion"
```

---

### Task 2: Multi-Query Retrieval

**Files:**
- Modify: `backend/app/rag/qa_chain.py:20-133`
- Create: `backend/tests/test_multi_query_retrieve.py`

- [ ] **Step 1: Write failing tests for multi_query_retrieve**

```python
# backend/tests/test_multi_query_retrieve.py
"""Tests for multi-query retrieval with cross-article support."""

import pytest
from unittest.mock import patch, MagicMock
from app.rag.qa_chain import multi_query_retrieve


def _make_chunk(slug: str, text: str = "test content", score: float = 0.5):
    """Helper to create mock retrieval chunks."""
    return {
        "text": text,
        "metadata": {"slug": slug, "title": f"Article {slug}", "source": slug},
        "score": score,
    }


class TestMultiQueryRetrieve:
    """multi_query_retrieve should route cross-article queries through expanded retrieval."""

    @patch("app.rag.qa_chain.hybrid_retrieve")
    def test_simple_query_bypasses_expansion(self, mock_hybrid):
        """Simple queries go directly to hybrid_retrieve without expansion."""
        mock_hybrid.return_value = [_make_chunk("react-tips")]

        result = multi_query_retrieve("React.memo 的作用是什么？", top_k=3)

        assert len(result) == 1
        assert result[0]["metadata"]["slug"] == "react-tips"
        # Called exactly once (no expansion)
        assert mock_hybrid.call_count == 1

    @patch("app.rag.qa_chain.hybrid_retrieve")
    def test_cross_article_query_expands(self, mock_hybrid):
        """Cross-article queries expand to multiple variants."""
        mock_hybrid.side_effect = [
            [_make_chunk("langchain", score=0.8)],
            [_make_chunk("llamaindex", score=0.7)],
        ]

        result = multi_query_retrieve("比较 LangChain 和 LlamaIndex 的 RAG 实现", top_k=3)

        # Should have called hybrid_retrieve for each variant + original
        assert mock_hybrid.call_count >= 2
        # Results should contain chunks from both sources
        slugs = {c["metadata"]["slug"] for c in result}
        assert "langchain" in slugs or "llamaindex" in slugs

    @patch("app.rag.qa_chain.hybrid_retrieve")
    def test_cross_article_rrf_fusion(self, mock_hybrid):
        """Multiple variants' results are fused via RRF."""
        mock_hybrid.side_effect = [
            [_make_chunk("a", score=0.9), _make_chunk("b", score=0.6)],
            [_make_chunk("b", score=0.8), _make_chunk("c", score=0.5)],
        ]

        result = multi_query_retrieve("比较 A 和 B 的区别", top_k=3)

        # Chunk b appears in both variant results → should rank high via RRF
        slugs = [c["metadata"]["slug"] for c in result]
        assert "b" in slugs

    @patch("app.rag.qa_chain.hybrid_retrieve")
    def test_empty_results(self, mock_hybrid):
        """No results from any variant returns empty list."""
        mock_hybrid.return_value = []

        result = multi_query_retrieve("比较不存在的内容", top_k=3)
        assert result == []

    @patch("app.rag.qa_chain.hybrid_retrieve")
    def test_respects_top_k(self, mock_hybrid):
        """Final result never exceeds top_k."""
        mock_hybrid.side_effect = [
            [_make_chunk(f"doc-{i}", score=0.9 - i * 0.1) for i in range(5)],
            [_make_chunk(f"doc-{i}", score=0.8 - i * 0.1) for i in range(5)],
        ]

        result = multi_query_retrieve("比较所有文章的共同点", top_k=2)
        assert len(result) <= 2

    @patch("app.rag.qa_chain.hybrid_retrieve")
    def test_disabled_via_env(self, mock_hybrid):
        """MULTI_QUERY_ENABLED=false bypasses multi-query path."""
        mock_hybrid.return_value = [_make_chunk("react-tips")]

        with patch("app.rag.qa_chain.MULTI_QUERY_ENABLED", False):
            result = multi_query_retrieve("比较 LangChain 和 LlamaIndex", top_k=3)

        # Should go through simple path (1 call)
        assert mock_hybrid.call_count == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_multi_query_retrieve.py -v`
Expected: FAIL — `ImportError: cannot import name 'multi_query_retrieve'`

- [ ] **Step 3: Implement multi_query_retrieve in qa_chain.py**

Add the following **after** the import block and **before** `hybrid_retrieve` (around line 10):

```python
from app.rag.query_rewriter import is_cross_article_query, expand_queries_rules

MULTI_QUERY_ENABLED = os.getenv("MULTI_QUERY_ENABLED", "true").lower() == "true"
```

Add the `multi_query_retrieve` function **after** `hybrid_retrieve` (after line 132):

```python
def multi_query_retrieve(query: str, top_k: int = 3, lang_filter: str = None) -> List[Dict[str, Any]]:
    """Multi-query retrieval: detect cross-article intent, expand, retrieve, fuse.

    For simple queries: delegates directly to hybrid_retrieve (zero overhead).
    For cross-article queries: generates keyword variants, runs hybrid_retrieve
    per variant, fuses via RRF, then diversity-selects top_k.

    Args:
        query: 查询文本
        top_k: 返回结果数量
        lang_filter: 语言过滤
    """
    if not MULTI_QUERY_ENABLED or not is_cross_article_query(query):
        return hybrid_retrieve(query, top_k=top_k, lang_filter=lang_filter)

    # Expand query into keyword variants
    variants = expand_queries_rules(query)

    # Collect results from all variants (using top_k*2 per variant for better fusion)
    all_results: List[Dict[str, Any]] = []
    for variant in variants:
        chunks = hybrid_retrieve(variant, top_k=top_k * 2, lang_filter=lang_filter)
        all_results.extend(chunks)

    if not all_results:
        return []

    # RRF fusion across all variant results
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict] = {}

    def _doc_key(doc: Dict) -> str:
        return doc.get("metadata", {}).get("slug", "") or doc.get("text", "")[:50]

    # Process results from each variant — each variant's results are independently ranked
    chunk_size = top_k * 2
    for variant_idx in range(len(variants)):
        start = variant_idx * chunk_size
        end = start + chunk_size
        variant_results = all_results[start:end]

        for rank, doc in enumerate(variant_results, 1):
            key = _doc_key(doc)
            rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
            if key not in doc_map:
                doc_map[key] = doc

    # Sort by RRF score
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Diversity selection: one per unique article, then fill
    selected = []
    seen_slugs = set()
    for key, _ in ranked:
        doc = doc_map[key]
        slug = doc.get("metadata", {}).get("slug", "")
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            selected.append(doc)
            if len(selected) >= top_k:
                break
    if len(selected) < top_k:
        for key, _ in ranked:
            doc = doc_map[key]
            if doc not in selected:
                selected.append(doc)
                if len(selected) >= top_k:
                    break

    return selected
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_multi_query_retrieve.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/qa_chain.py backend/tests/test_multi_query_retrieve.py
git commit -m "feat: add multi_query_retrieve with cross-article RRF fusion"
```

---

### Task 3: Wire into rag_query and rag_query_astream

**Files:**
- Modify: `backend/app/rag/qa_chain.py:207,267`

- [ ] **Step 1: Replace hybrid_retrieve calls in rag_query**

In `qa_chain.py`, line 207, change:

```python
# Before
chunks = hybrid_retrieve(query, top_k=top_k, lang_filter=filter_lang)

# After
chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)
```

- [ ] **Step 2: Replace hybrid_retrieve calls in rag_query_astream**

In `qa_chain.py`, line 267, change:

```python
# Before
chunks = hybrid_retrieve(query, top_k=top_k, lang_filter=filter_lang)

# After
chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)
```

- [ ] **Step 3: Run existing tests to verify no regression**

Run: `cd backend && python -m pytest tests/test_rag_router.py tests/test_rag_router_extended.py -v`
Expected: All existing tests still PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/rag/qa_chain.py
git commit -m "feat: wire multi_query_retrieve into rag_query and rag_query_astream"
```

---

### Task 4: Cross-Article QA Pairs + Benchmark

**Files:**
- Modify: `backend/app/rag/test_data.py`

- [ ] **Step 1: Add cross-article QA pairs**

Append to `TEST_QA_PAIRS` list in `test_data.py` (before the closing `]`):

```python
    # ── Cross-article queries (6 pairs) ──
    {"id": "cross-zh-001", "question": "比较 LangChain 和 LlamaIndex 的 RAG 实现有什么不同？", "answer": "LangChain 使用 LCEL 链式编排，LlamaIndex 使用 Pipeline 三阶段架构", "source_article": "langchain-framework-guide"},
    {"id": "cross-zh-002", "question": "Hermes Agent 和 AI Agent Architecture 有什么共同点？", "answer": "都涉及 ReAct 模式、工具调用、分层架构", "source_article": "hermes-agent-practical-guide"},
    {"id": "cross-zh-003", "question": "向量数据库和 Embedding 模型的关系是什么？", "answer": "Embedding 模型生成向量，向量数据库存储和检索向量", "source_article": "vector-database-guide"},
    {"id": "cross-en-001", "question": "compare the deployment approaches of Railway and GitHub Pages", "answer": "Railway uses Docker multi-stage build, GitHub Pages uses static SPA with router fallback", "source_article": "chatbot-railway-deployment"},
    {"id": "cross-en-002", "question": "what are the similarities between React.memo and useMemo", "answer": "Both optimize performance by avoiding unnecessary re-computation, memo caches render output while useMemo caches computation", "source_article": "react-performance-tips"},
    {"id": "cross-en-003", "question": "differences between BM25 and vector search in RAG systems", "answer": "BM25 uses keyword matching with TF-IDF scoring, vector search uses semantic similarity via embeddings", "source_article": "rag-concepts-deep-dive"},
```

- [ ] **Step 2: Verify test data loads without errors**

Run: `cd backend && python -c "from app.rag.test_data import TEST_QA_PAIRS; print(f'{len(TEST_QA_PAIRS)} QA pairs loaded')"`
Expected: `82 QA pairs loaded` (76 original + 6 new)

- [ ] **Step 3: Commit**

```bash
git add backend/app/rag/test_data.py
git commit -m "test: add 6 cross-article QA pairs (3 zh + 3 en)"
```

---

### Task 5: Run Benchmark + Update Metrics

**Files:**
- Modify: `data/benchmark_results.json`
- Modify: `目标.md`

- [ ] **Step 1: Run full benchmark**

Run: `cd backend && python -m pytest tests/ -v -k "rag" --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run RAG evaluation script (if exists) or manual check**

Check if benchmark script exists:
```bash
ls backend/app/rag/eval*.py backend/eval*.py 2>/dev/null
```

If eval script exists, run it. Otherwise, verify by running the API and testing cross-article queries manually.

- [ ] **Step 3: Update benchmark_results.json**

Update `Recall@3 (Hybrid)` value based on actual benchmark results. Expected improvement from 97.4% to ~99%.

- [ ] **Step 4: Update 目标.md metrics table**

Update the v17 changelog section with cross-article query enhancement details.

- [ ] **Step 5: Final commit**

```bash
git add data/benchmark_results.json 目标.md
git commit -m "docs: update benchmark metrics after cross-article query enhancement"
```
