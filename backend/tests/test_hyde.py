# -*- coding: utf-8 -*-
"""
Test HyDE (Hypothetical Document Embedding) implementation.
"""
import pytest
from unittest.mock import MagicMock, patch


def test_generate_hypothetical_answer():
    """Test hypothetical answer generation."""
    from app.rag.query_rewriter import generate_hypothetical_answer

    # Mock LLM call function
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "RAG is a technique that combines retrieval and generation."
    mock_llm.return_value = mock_response

    result = generate_hypothetical_answer(
        "What is RAG?",
        mock_llm,
        lang="en"
    )

    assert result == "RAG is a technique that combines retrieval and generation."
    mock_llm.assert_called_once()


def test_generate_hypothetical_answer_error():
    """Test hypothetical answer generation with LLM error."""
    from app.rag.query_rewriter import generate_hypothetical_answer

    mock_llm = MagicMock()
    mock_llm.side_effect = Exception("LLM API error")

    result = generate_hypothetical_answer(
        "What is RAG?",
        mock_llm,
        lang="en"
    )

    assert result == ""


def test_hyde_retrieve():
    """Test HyDE retrieval with mocked dependencies."""
    from app.rag.query_rewriter import hyde_retrieve

    # Mock LLM call function
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "RAG is a technique combining retrieval and generation"
    mock_llm.return_value = mock_response

    # Mock hybrid_retrieve（HyDE 现在使用混合检索而非纯向量检索）
    mock_chunks = [
        {"text": "RAG Introduction", "metadata": {"title": "RAG Guide"}, "score": 0.8},
        {"text": "Vector Search", "metadata": {"title": "Vector Search"}, "score": 0.7},
    ]

    with patch("app.rag.qa_chain.hybrid_retrieve", return_value=mock_chunks) as mock_hybrid:
        result = hyde_retrieve(
            "What is RAG?",
            mock_llm,
            top_k=3,
            lang="en"
        )

        assert len(result) == 2
        assert result[0]["text"] == "RAG Introduction"
        # Verify hybrid_retrieve was called with hypothetical answer, not original query
        mock_hybrid.assert_called_once()
        call_args = mock_hybrid.call_args
        assert call_args[0][0] == "RAG is a technique combining retrieval and generation"


def test_hyde_retrieve_fallback():
    """Test HyDE retrieval fallback when hypothetical answer returns no results."""
    from app.rag.query_rewriter import hyde_retrieve

    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "Hypothetical answer"
    mock_llm.return_value = mock_response

    # First call returns empty, second call returns results
    mock_chunks = [{"text": "Result", "metadata": {}, "score": 0.5}]

    with patch("app.rag.qa_chain.hybrid_retrieve", side_effect=[[], mock_chunks]) as mock_hybrid:
        result = hyde_retrieve(
            "Test query",
            mock_llm,
            top_k=3,
            lang="en"
        )

        assert len(result) == 1
        # Should be called twice: once with hypothetical, once with original query
        assert mock_hybrid.call_count == 2


def test_hyde_retrieve_empty_hypothetical():
    """Test HyDE retrieval when hypothetical answer is empty."""
    from app.rag.query_rewriter import hyde_retrieve

    mock_llm = MagicMock()
    mock_llm.side_effect = Exception("LLM error")

    mock_chunks = [{"text": "Result", "metadata": {}, "score": 0.5}]

    with patch("app.rag.qa_chain.hybrid_retrieve", return_value=mock_chunks) as mock_hybrid:
        result = hyde_retrieve(
            "Test query",
            mock_llm,
            top_k=3,
            lang="en"
        )

        assert len(result) == 1
        # Should fallback to direct query retrieval
        mock_hybrid.assert_called_once_with("Test query", top_k=3, lang_filter=None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
