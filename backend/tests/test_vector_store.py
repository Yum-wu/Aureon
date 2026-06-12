"""Tests for app.rag.vector_store — utility functions, BM25, format, diversity."""

from unittest.mock import patch

from app.rag.vector_store import (
    _cache_key,
    _tokenize,
    _bm25_score,
    _simple_diversity,
    format_context,
    get_bm25_stats,
    retrieve_keyword,
)


# ── _cache_key ──


class TestCacheKey:
    def test_deterministic(self):
        assert _cache_key("hello") == _cache_key("hello")

    def test_different_inputs(self):
        assert _cache_key("a") != _cache_key("b")


# ── _tokenize ──


class TestTokenize:
    def test_english_words(self):
        tokens = _tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_numbers(self):
        tokens = _tokenize("test 123")
        assert "123" in tokens

    def test_chinese_chars_and_bigrams(self):
        tokens = _tokenize("人工智能")
        # jieba segments into words; "人工" and "智能" are standard splits
        assert any("人工" in t for t in tokens)
        assert any("智能" in t for t in tokens)

    def test_mixed_content(self):
        tokens = _tokenize("RAG 系统 v2")
        assert "rag" in tokens
        # jieba keeps "系统" as one word; single chars filtered out
        assert "系统" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []


# ── _bm25_score ──


class TestBM25Score:
    def test_matching_terms(self):
        import app.rag.vector_store as vs
        vs._kw_idf = {"hello": 2.0, "world": 1.5}
        vs._kw_avgdl = 10.0
        score = _bm25_score(["hello", "world"], ["hello", "world", "foo"], vs._kw_avgdl)
        assert score > 0

    def test_no_matching_terms(self):
        import app.rag.vector_store as vs
        vs._kw_idf = {"foo": 1.0}
        vs._kw_avgdl = 10.0
        score = _bm25_score(["hello"], ["world"], vs._kw_avgdl)
        assert score == 0.0

    def test_empty_query(self):
        import app.rag.vector_store as vs
        vs._kw_idf = {"hello": 1.0}
        vs._kw_avgdl = 5.0
        score = _bm25_score([], ["hello"], vs._kw_avgdl)
        assert score == 0.0


# ── _simple_diversity ──


class TestSimpleDiversity:
    def test_prefers_unique_sources(self):
        items = [
            {"text": "a", "metadata": {"source": "doc1.md"}, "score": 0.9},
            {"text": "b", "metadata": {"source": "doc1.md"}, "score": 0.85},
            {"text": "c", "metadata": {"source": "doc2.md"}, "score": 0.8},
        ]
        result = _simple_diversity(items, top_k=2)
        sources = [r["metadata"]["source"] for r in result]
        assert "doc1.md" in sources
        assert "doc2.md" in sources

    def test_top_k_limits_output(self):
        items = [
            {"text": f"t{i}", "metadata": {"source": f"d{i}.md"}, "score": 1.0 - i * 0.1}
            for i in range(10)
        ]
        result = _simple_diversity(items, top_k=3)
        assert len(result) == 3

    def test_fills_when_not_enough_unique(self):
        items = [
            {"text": "a", "metadata": {"source": "doc.md"}, "score": 0.9},
            {"text": "b", "metadata": {"source": "doc.md"}, "score": 0.8},
        ]
        result = _simple_diversity(items, top_k=2)
        assert len(result) == 2


# ── format_context ──


class TestFormatContext:
    def test_single_chunk(self):
        chunks = [{"text": "content", "metadata": {"title": "Doc A"}}]
        result = format_context(chunks)
        assert "Doc A" in result
        assert "content" in result

    def test_multiple_chunks(self):
        chunks = [
            {"text": "first", "metadata": {"title": "A"}},
            {"text": "second", "metadata": {"source": "B.md"}},
        ]
        result = format_context(chunks)
        assert "Source 1" in result
        assert "Source 2" in result
        assert "first" in result
        assert "second" in result

    def test_empty_chunks(self):
        assert format_context([]) == ""

    def test_uses_source_when_no_title(self):
        chunks = [{"text": "t", "metadata": {"source": "file.md"}}]
        result = format_context(chunks)
        assert "file.md" in result

    def test_unknown_when_no_metadata(self):
        chunks = [{"text": "t", "metadata": {}}]
        result = format_context(chunks)
        assert "Unknown" in result


# ── get_bm25_stats ──


class TestGetBM25Stats:
    def test_with_data(self):
        import app.rag.vector_store as vs
        vs._kw_docs = [{"text": "a"}, {"text": "b"}]
        vs._kw_idf = {"a": 1.0, "b": 2.0, "c": 0.5}
        vs._kw_avgdl = 5.5

        stats = get_bm25_stats()
        assert stats["docs"] == 2
        assert stats["terms"] == 3
        assert stats["avgdl"] == 5.5

    def test_empty_index(self):
        import app.rag.vector_store as vs
        vs._kw_docs = []
        vs._kw_idf = {}
        vs._kw_avgdl = 0.0

        stats = get_bm25_stats()
        assert stats["docs"] == 0
        assert stats["terms"] == 0
        assert stats["avgdl"] == 0


# ── retrieve_keyword ──


class TestRetrieveKeyword:
    def test_empty_index_returns_empty(self):
        import app.rag.vector_store as vs
        vs._kw_docs = []
        vs._kw_idf = {}
        vs._kw_avgdl = 0.0

        with patch("app.rag.vector_store._build_kw_index"):
            result = retrieve_keyword("test query")
        assert result == []

    def test_returns_matching_docs(self):
        import app.rag.vector_store as vs
        vs._kw_docs = [
            {"text": "RAG retrieval augmented generation", "metadata": {"title": "RAG Guide"}},
            {"text": "deploy to GitHub Pages", "metadata": {"title": "Deploy"}},
        ]
        vs._kw_idf = {"rag": 2.0, "retrieval": 1.5, "deploy": 1.0, "github": 1.0}
        vs._kw_avgdl = 5.0

        with patch("app.rag.vector_store._build_kw_index"):
            result = retrieve_keyword("RAG retrieval", top_k=2)
        assert len(result) > 0
        assert result[0]["text"] == "RAG retrieval augmented generation"
        assert "score" in result[0]

    def test_no_match_returns_empty(self):
        import app.rag.vector_store as vs
        vs._kw_docs = [
            {"text": "completely unrelated content", "metadata": {"title": "Other"}},
        ]
        vs._kw_idf = {"unrelated": 1.0, "content": 1.0}
        vs._kw_avgdl = 3.0

        with patch("app.rag.vector_store._build_kw_index"):
            result = retrieve_keyword("RAG")
        assert result == []
