"""Tests for post-generation self-reflection (Self-RAG style)."""
import pytest
from unittest.mock import AsyncMock
from app.rag.post_generation_reflection import (
    reflect_on_answer,
    wrap_answer_with_reflection,
)


class TestReflectOnAnswer:
    @pytest.mark.asyncio
    async def test_supported_returns_supported(self):
        mock_llm = AsyncMock(return_value="SUPPORTED")
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "supported"

    @pytest.mark.asyncio
    async def test_not_supported_returns_not_supported(self):
        mock_llm = AsyncMock(return_value="NOT_SUPPORTED")
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "not_supported"

    @pytest.mark.asyncio
    async def test_partial_returns_partial(self):
        mock_llm = AsyncMock(return_value="PARTIAL")
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "partial"

    @pytest.mark.asyncio
    async def test_error_defaults_to_supported(self):
        mock_llm = AsyncMock(side_effect=Exception("API error"))
        result = await reflect_on_answer("query", "context", "answer", mock_llm)
        assert result == "supported"


class TestWrapAnswerWithReflection:
    def test_supported_returns_original(self):
        result = wrap_answer_with_reflection("answer", "supported", "en")
        assert result == "answer"

    def test_not_supported_adds_warning_en(self):
        result = wrap_answer_with_reflection("answer", "not_supported", "en")
        assert "not fully supported" in result.lower()

    def test_partial_adds_note_zh(self):
        result = wrap_answer_with_reflection("答案", "partial", "zh")
        assert "不完整" in result
