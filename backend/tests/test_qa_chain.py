"""Tests for app.rag.qa_chain — generate_answer, rag_query, rag_query_astream."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace

from app.rag.qa_chain import (
    generate_answer,
    rag_query,
    rag_query_astream,
    run_incremental_index,
    run_index_pipeline,
)


# ── generate_answer ──


class TestGenerateAnswer:
    def test_basic_call(self):
        llm_fn = MagicMock(return_value="The answer is 42.")
        result = generate_answer("What is RAG?", "context here", llm_fn, lang="en")
        assert result == "The answer is 42."
        llm_fn.assert_called_once()
        messages = llm_fn.call_args[0][0]
        assert messages[1]["role"] == "user"
        assert messages[1]["content"] == "What is RAG?"

    def test_chinese_prompt(self):
        llm_fn = MagicMock(return_value="答案")
        result = generate_answer("什么是RAG?", "context", llm_fn, lang="zh")
        assert result == "答案"
        messages = llm_fn.call_args[0][0]
        assert "知识库" in messages[0]["content"]

    def test_custom_system_prompt(self):
        llm_fn = MagicMock(return_value="custom")
        result = generate_answer("q", "ctx", llm_fn, system_prompt="Custom: {context} {lang_instruction}")
        assert result == "custom"
        messages = llm_fn.call_args[0][0]
        assert "Custom:" in messages[0]["content"]


# ── rag_query ──


class TestRagQuery:
    @patch("app.rag.qa_chain.retrieve", return_value=[])
    def test_no_chunks_returns_no_result_zh(self, mock_retrieve):
        llm_fn = MagicMock()
        result = rag_query("test", llm_fn, lang="zh")
        assert "暂无" in result.answer
        assert result.sources == []
        llm_fn.assert_not_called()

    @patch("app.rag.qa_chain.retrieve", return_value=[])
    def test_no_chunks_returns_no_result_en(self, mock_retrieve):
        llm_fn = MagicMock()
        result = rag_query("test", llm_fn, lang="en")
        assert "No relevant content" in result.answer

    @patch("app.rag.qa_chain.retrieve")
    def test_with_chunks(self, mock_retrieve):
        mock_retrieve.return_value = [
            {"text": "RAG is retrieval augmented generation", "metadata": {"title": "RAG Guide", "slug": "rag"}, "score": 0.9}
        ]
        llm_fn = MagicMock(return_value="RAG is a technique...")
        result = rag_query("What is RAG?", llm_fn, lang="en")
        assert result.answer == "RAG is a technique..."
        assert len(result.sources) == 1
        assert result.sources[0].title == "RAG Guide"

    @patch("app.rag.qa_chain.retrieve")
    def test_long_chunk_truncated(self, mock_retrieve):
        long_text = "x" * 300
        mock_retrieve.return_value = [
            {"text": long_text, "metadata": {"title": "T", "slug": "s"}, "score": 0.8}
        ]
        llm_fn = MagicMock(return_value="ok")
        result = rag_query("q", llm_fn)
        assert result.sources[0].chunk.endswith("...")

    @patch("app.rag.qa_chain.retrieve", return_value=[])
    def test_auto_detect_language(self, mock_retrieve):
        llm_fn = MagicMock()
        rag_query("你好世界", llm_fn)
        # lang=None triggers auto-detect → should be zh


# ── rag_query_astream ──


class TestRagQueryAstream:
    @pytest.mark.asyncio
    @patch("app.rag.qa_chain.retrieve_keyword", return_value=[])
    async def test_no_chunks(self, mock_retrieve):
        events = []
        async for event in rag_query_astream("test", AsyncMock(), lang="en"):
            events.append(event)

        types = [e["type"] for e in events]
        assert "sources" in types
        assert "text" in types
        assert "No relevant content" in next(e["content"] for e in events if e["type"] == "text")

    @pytest.mark.asyncio
    @patch("app.rag.qa_chain.retrieve_keyword")
    async def test_with_chunks(self, mock_retrieve):
        mock_retrieve.return_value = [
            {"text": "RAG content", "metadata": {"title": "Guide", "slug": "g"}, "score": 0.9}
        ]

        chunk = MagicMock()
        chunk.content = "Answer"

        async def fake_astream(messages):
            yield chunk

        mock_llm = MagicMock()
        mock_llm.model = "test-model"
        mock_llm.astream = fake_astream

        events = []
        async for event in rag_query_astream("What is RAG?", mock_llm, lang="en"):
            events.append(event)

        types = [e["type"] for e in events]
        assert "sources" in types
        assert "citation" in types
        assert "text" in types

    @pytest.mark.asyncio
    @patch("app.rag.qa_chain.retrieve_keyword")
    async def test_zh_no_results(self, mock_retrieve):
        mock_retrieve.return_value = []
        events = []
        async for event in rag_query_astream("test", AsyncMock(), lang="zh"):
            events.append(event)
        text = next(e["content"] for e in events if e["type"] == "text")
        assert "暂无" in text


# ── run_incremental_index ──


class TestRunIncrementalIndex:
    @patch("app.rag.vector_store.add_to_index")
    @patch("app.rag.loader.load_single_document")
    def test_empty_file_returns_error(self, mock_load, mock_add):
        mock_load.return_value = {"content": "", "metadata": {}}
        result = run_incremental_index("/fake/empty.md")
        assert result["status"] == "error"
        assert result["chunks_created"] == 0

    @patch("app.rag.vector_store.add_to_index")
    @patch("app.rag.loader.load_single_document")
    def test_valid_file(self, mock_load, mock_add):
        mock_load.return_value = {
            "content": "This is test content for indexing.",
            "metadata": {"title": "Test", "source": "test.md"}
        }
        result = run_incremental_index("/fake/test.md")
        assert result["status"] == "ok"
        assert result["documents_indexed"] == 1
        assert result["chunks_created"] >= 1
        mock_add.assert_called_once()


# ── run_index_pipeline ──


class TestRunIndexPipeline:
    @patch("app.rag.qa_chain.save_index")
    @patch("app.rag.qa_chain.embed_texts_llm", return_value=[[0.1, 0.2]])
    @patch("app.rag.loader.load_markdown_files", return_value=[])
    def test_no_docs_returns_error(self, mock_load, mock_embed, mock_save):
        result = run_index_pipeline("/empty/dir")
        assert result["status"] == "error"
        assert "没有找到" in result["message"]

    @patch("app.rag.qa_chain.save_index")
    @patch("app.rag.qa_chain.embed_texts_llm")
    @patch("app.rag.loader.load_markdown_files")
    def test_valid_pipeline(self, mock_load, mock_embed, mock_save):
        import numpy as np
        mock_load.return_value = [
            {"content": "Some content to index.", "metadata": {"title": "Test", "source": "test.md"}}
        ]
        mock_embed.return_value = np.array([[0.1, 0.2]], dtype=np.float32)
        result = run_index_pipeline("/articles")
        assert result["status"] == "ok"
        assert result["documents_indexed"] == 1
        assert result["chunks_created"] >= 1
        # save_index is called via `from app.rag.vector_store import save_index` inside run_index_pipeline
        # so we need to check it was called through the vector_store module
        mock_save.assert_called_once()
