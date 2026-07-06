"""Tests for multi-query retrieval with cross-article support."""

from unittest.mock import patch
from app.rag.qa_chain import multi_query_retrieve


def _make_chunk(slug: str, text: str = "test content", score: float = 0.5):
    return {
        "text": text,
        "metadata": {"slug": slug, "title": f"Article {slug}", "source": slug},
        "score": score,
    }


class TestMultiQueryRetrieve:
    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_simple_query_bypasses_expansion(self, mock_hybrid):
        mock_hybrid.return_value = [_make_chunk("react-tips")]
        result = multi_query_retrieve("React.memo 的作用是什么？", top_k=3)
        assert len(result) == 1
        assert mock_hybrid.call_count == 1

    @patch("app.rag.retriever.is_cross_article_query", return_value=True)
    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", True)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_cross_article_query_expands(self, mock_hybrid, mock_is_cross):
        mock_hybrid.side_effect = [
            [_make_chunk("langchain", score=0.8)],
            [_make_chunk("llamaindex", score=0.7)],
            [_make_chunk("langchain", score=0.6)],
        ]
        multi_query_retrieve("比较 LangChain 和 LlamaIndex 的 RAG 实现", top_k=3)
        assert mock_hybrid.call_count >= 2

    @patch("app.rag.retriever.is_cross_article_query", return_value=True)
    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", True)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_cross_article_rrf_fusion(self, mock_hybrid, mock_is_cross):
        mock_hybrid.side_effect = [
            [_make_chunk("a", score=0.9), _make_chunk("b", score=0.6)],
            [_make_chunk("b", score=0.8), _make_chunk("c", score=0.5)],
            [_make_chunk("a", score=0.7)],
        ]
        result = multi_query_retrieve("比较 A 和 B 的区别", top_k=3)
        slugs = [c["metadata"]["slug"] for c in result]
        assert "b" in slugs

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_empty_results(self, mock_hybrid):
        mock_hybrid.return_value = []
        result = multi_query_retrieve("比较不存在的内容", top_k=3)
        assert result == []

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_respects_top_k(self, mock_hybrid):
        all_chunks = [_make_chunk(f"doc-{i}", score=0.9 - i * 0.1) for i in range(5)]

        def _hybrid_with_topk(query, top_k=3, lang_filter=None, query_complexity="simple", tenant_id=None):
            return all_chunks[:top_k]

        mock_hybrid.side_effect = _hybrid_with_topk
        result = multi_query_retrieve("比较所有文章的共同点", top_k=2)
        assert len(result) <= 2

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_disabled_via_env(self, mock_hybrid):
        mock_hybrid.return_value = [_make_chunk("react-tips")]
        multi_query_retrieve("比较 LangChain 和 LlamaIndex", top_k=3)
        assert mock_hybrid.call_count == 1
