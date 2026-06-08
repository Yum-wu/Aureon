"""Tests for LLM-based multi-query expansion."""
import pytest
import json
from unittest.mock import AsyncMock
from app.rag.multi_query_llm import multi_query_llm_rewrite, decompose_complex_query


class TestMultiQueryLLMRewrite:
    @pytest.mark.asyncio
    async def test_returns_original_plus_variants(self):
        mock_llm = AsyncMock(return_value=json.dumps([
            "BM25 keyword retrieval explained",
            "How BM25 scoring works",
        ]))
        result = await multi_query_llm_rewrite("What is BM25?", mock_llm, n_variants=2)
        assert len(result) == 3
        assert result[0] == "What is BM25?"

    @pytest.mark.asyncio
    async def test_deduplicates_original(self):
        mock_llm = AsyncMock(return_value=json.dumps([
            "What is BM25?",
            "BM25 explained",
        ]))
        result = await multi_query_llm_rewrite("What is BM25?", mock_llm, n_variants=2)
        assert result.count("What is BM25?") == 1

    @pytest.mark.asyncio
    async def test_fallback_on_invalid_json(self):
        mock_llm = AsyncMock(return_value="not json")
        result = await multi_query_llm_rewrite("test query", mock_llm)
        assert result == ["test query"]

    @pytest.mark.asyncio
    async def test_limits_variants(self):
        mock_llm = AsyncMock(return_value=json.dumps(["v1", "v2", "v3", "v4"]))
        result = await multi_query_llm_rewrite("test", mock_llm, n_variants=2)
        assert len(result) <= 3


class TestDecomposeComplexQuery:
    @pytest.mark.asyncio
    async def test_returns_sub_queries(self):
        mock_llm = AsyncMock(return_value=json.dumps([
            "What is LangChain?",
            "What is LlamaIndex?",
            "LangChain vs LlamaIndex performance",
        ]))
        result = await decompose_complex_query(
            "Compare LangChain and LlamaIndex", mock_llm
        )
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_fallback_on_error(self):
        mock_llm = AsyncMock(side_effect=Exception("API error"))
        result = await decompose_complex_query("complex query", mock_llm)
        assert result == ["complex query"]

    @pytest.mark.asyncio
    async def test_limits_sub_queries(self):
        mock_llm = AsyncMock(return_value=json.dumps([f"q{i}" for i in range(10)]))
        result = await decompose_complex_query("test", mock_llm, max_sub_queries=3)
        assert len(result) <= 3
