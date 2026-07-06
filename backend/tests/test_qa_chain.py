"""Tests for app.rag.qa_chain — generate_answer, rag_query, rag_query_astream."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.rag.qa_chain import (
    generate_answer,
    rag_query,
    rag_query_astream,
    rag_query_with_cache,
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
    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve", return_value=[])
    def test_no_chunks_returns_no_result_zh(self, mock_hybrid):
        llm_fn = MagicMock()
        result = rag_query("test", llm_fn, lang="zh")
        assert "暂无" in result.answer
        assert result.sources == []
        llm_fn.assert_not_called()

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve", return_value=[])
    def test_no_chunks_returns_no_result_en(self, mock_hybrid):
        llm_fn = MagicMock()
        result = rag_query("test", llm_fn, lang="en")
        assert "No relevant content" in result.answer

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.classifier.classify_query_answerable_sync", return_value=True)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_with_chunks(self, mock_hybrid, mock_classify):
        mock_hybrid.return_value = [
            {"text": "RAG is retrieval augmented generation", "metadata": {"title": "RAG Guide", "slug": "rag"}, "score": 0.9}
        ]
        llm_fn = MagicMock(return_value="RAG is a technique...")
        result = rag_query("What is RAG?", llm_fn, lang="en")
        assert result.answer == "RAG is a technique..."
        assert len(result.sources) == 1
        assert result.sources[0].title == "RAG Guide"

    @patch("app.rag.query_classifier.route_retrieval", return_value="complex")
    @patch("app.rag.generator.hyde_retrieve")
    @patch("app.rag.generator.hybrid_retrieve")
    def test_exact_lookup_skips_hyde(self, mock_hybrid, mock_hyde, mock_route):
        mock_hybrid.return_value = [
            {
                "text": "AUREON_TENANT_SENTINEL_DOCX_80F329A upload content",
                "metadata": {"title": "Upload DOCX", "slug": "upload-docx"},
                "score": 1.0,
            }
        ]
        llm_fn = MagicMock(return_value="found")

        result = rag_query("AUREON_TENANT_SENTINEL_DOCX_80F329A", llm_fn, lang="en")

        assert result.sources[0].title == "Upload DOCX"
        mock_hyde.assert_not_called()
        assert mock_hybrid.call_args.kwargs["query_complexity"] == "simple"

    @patch("app.rag.query_classifier.route_retrieval", return_value="complex")
    @patch("app.rag.generator.hybrid_retrieve")
    def test_exact_lookup_promotes_matching_chunk(self, mock_hybrid, mock_route):
        mock_hybrid.return_value = [
            {
                "text": "generic upload content",
                "metadata": {"title": "Other Upload", "slug": "other-upload"},
                "score": 1.0,
            },
            {
                "text": "AUREON_TENANT_SENTINEL_XLSX_80F329A upload content",
                "metadata": {"title": "Upload XLSX", "slug": "upload-xlsx"},
                "score": 0.1,
            },
        ]
        llm_fn = MagicMock(return_value="found")

        result = rag_query("AUREON_TENANT_SENTINEL_XLSX_80F329A", llm_fn, top_k=1, lang="en")

        assert result.sources[0].title == "Upload XLSX"
        assert mock_hybrid.call_args.kwargs["top_k"] == 10

    @patch("app.rag.query_classifier.route_retrieval", return_value="complex")
    @patch("app.rag.generator._retrieve_exact_lookup_chunks")
    @patch("app.rag.generator.hybrid_retrieve")
    def test_exact_lookup_merges_payload_hits(self, mock_hybrid, mock_exact, mock_route):
        mock_hybrid.return_value = [
            {
                "text": "generic upload content",
                "metadata": {"title": "Upload CSV", "slug": "upload-csv"},
                "score": 1.0,
            },
        ]
        mock_exact.return_value = [
            {
                "text": "AUREON_TENANT_SENTINEL_DOCX_80F329A upload content",
                "metadata": {"title": "Upload DOCX", "slug": "upload-docx"},
                "score": 1.0,
            },
        ]
        llm_fn = MagicMock(return_value="found")

        result = rag_query("AUREON_TENANT_SENTINEL_DOCX_80F329A", llm_fn, top_k=1, lang="en")

        assert result.sources[0].title == "Upload DOCX"
        mock_exact.assert_called_once_with("AUREON_TENANT_SENTINEL_DOCX_80F329A", 10, None)

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.classifier.classify_query_answerable_sync", return_value=True)
    @patch("app.rag.retriever.hybrid_retrieve")
    def test_long_chunk_truncated(self, mock_hybrid, mock_classify):
        long_text = "x" * 300
        mock_hybrid.return_value = [
            {"text": long_text, "metadata": {"title": "T", "slug": "s"}, "score": 0.8}
        ]
        llm_fn = MagicMock(return_value="ok")
        result = rag_query("q", llm_fn)
        assert result.sources[0].chunk.endswith("...")

    @patch("app.rag.retriever.MULTI_QUERY_ENABLED", False)
    @patch("app.rag.retriever.hybrid_retrieve", return_value=[])
    def test_auto_detect_language(self, mock_hybrid):
        llm_fn = MagicMock()
        rag_query("你好世界", llm_fn)
        # lang=None triggers auto-detect → should be zh


# ── rag_query_astream ──


class TestRagQueryAstream:
    @pytest.mark.asyncio
    @patch("app.rag.query_classifier.route_retrieval", return_value="medium")
    @patch("app.rag.generator.hybrid_retrieve", return_value=[])
    async def test_no_chunks(self, mock_hybrid, mock_route):
        events = []
        async for event in rag_query_astream("test", AsyncMock(), lang="en"):
            events.append(event)

        types = [e["type"] for e in events]
        assert "sources" in types
        assert "text" in types
        assert "No relevant content" in next(e["content"] for e in events if e["type"] == "text")

    @pytest.mark.asyncio
    @patch("app.rag.query_classifier.route_retrieval", return_value="medium")
    @patch("app.rag.classifier.classify_query_answerable", new_callable=AsyncMock, return_value=True)
    @patch("app.rag.generator.hybrid_retrieve")
    async def test_with_chunks(self, mock_hybrid_retrieve, mock_classify, mock_route):
        mock_hybrid_retrieve.return_value = [
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
    @patch("app.rag.query_classifier.route_retrieval", return_value="medium")
    @patch("app.rag.generator.hybrid_retrieve", return_value=[])
    async def test_zh_no_results(self, mock_hybrid, mock_route):
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
    @patch("app.rag.ingestion.pipeline.build_chunks", return_value=[])
    def test_nonempty_file_with_zero_chunks_returns_error(self, mock_build, mock_load, mock_add):
        mock_load.return_value = {
            "content": "This is test content for indexing.",
            "metadata": {"title": "Test", "source": "test.md"}
        }
        result = run_incremental_index("/fake/test.md")
        assert result["status"] == "error"
        assert result["documents_indexed"] == 0
        assert result["chunks_created"] == 0
        mock_add.assert_not_called()


# ── run_index_pipeline ──


class TestRunIndexPipeline:
    @pytest.mark.integration
    @patch("app.rag.indexer.save_index")
    @patch("app.rag.loader.load_markdown_files", return_value=[])
    async def test_no_docs_returns_error(self, mock_load, mock_save):
        result = await run_index_pipeline("/empty/dir")
        assert result["status"] == "error"
        assert "没有找到" in result["message"]

    @pytest.mark.integration
    @patch("app.rag.indexer.save_index")
    @patch("app.rag.loader.load_markdown_files")
    async def test_valid_pipeline(self, mock_load, mock_save):
        mock_load.return_value = [
            {"content": "Some content to index.", "metadata": {"title": "Test", "source": "test.md"}}
        ]
        result = await run_index_pipeline("/articles")
        assert result["status"] == "ok"
        assert result["documents_indexed"] == 1
        assert result["chunks_created"] >= 1
        mock_save.assert_called_once()


# ── rag_query_with_cache ──


class TestRagQueryWithCache:
    @pytest.mark.asyncio
    async def test_miss_then_cache_stores_sources(self):
        with patch("app.cache.redis_client.get_redis", return_value=None), \
             patch("app.cache.redis_client.set_cached", new_callable=AsyncMock) as mock_set_cached, \
             patch("app.cache.redis_client.get_cached", new_callable=AsyncMock, return_value=None), \
             patch("app.rag.retriever.MULTI_QUERY_ENABLED", False), \
             patch("app.rag.classifier.classify_query_answerable_sync", return_value=True), \
             patch("app.rag.retriever.hybrid_retrieve") as mock_hybrid:
            mock_hybrid.return_value = [
                {"text": "RAG content", "metadata": {"title": "Guide", "slug": "g"}, "score": 0.9}
            ]
            llm_fn = MagicMock(return_value="RAG answer")
            result = await rag_query_with_cache("What is RAG?", llm_fn, lang="en")
            assert result.answer == "RAG answer"
            assert len(result.sources) == 1
            assert result.sources[0].title == "Guide"
            import json
            cached_value = mock_set_cached.call_args[0][1]
            parsed = json.loads(cached_value)
            assert parsed["answer"] == "RAG answer"
            assert len(parsed["sources"]) == 1
            assert parsed["sources"][0]["title"] == "Guide"

    @pytest.mark.asyncio
    async def test_hit_restores_sources(self):
        import json
        cached_json = json.dumps({
            "answer": "Cached answer",
            "sources": [{"title": "Doc A", "slug": "a", "chunk": "text...", "score": 0.95}]
        })
        with patch("app.cache.redis_client.get_redis", return_value=None), \
             patch("app.cache.redis_client.set_cached", new_callable=AsyncMock), \
             patch("app.cache.redis_client.get_cached", new_callable=AsyncMock) as mock_get_cached, \
             patch("app.rag.retriever.MULTI_QUERY_ENABLED", False), \
             patch("app.rag.retriever.hybrid_retrieve"):
            mock_get_cached.return_value = cached_json
            llm_fn = MagicMock()
            result = await rag_query_with_cache("test query", llm_fn, lang="en")
            assert result.answer == "Cached answer"
            assert len(result.sources) == 1
            assert result.sources[0].title == "Doc A"
            assert result.sources[0].score == 0.95
            llm_fn.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.cache.redis_client.get_redis", return_value=None)
    @patch("app.cache.redis_client.set_cached", new_callable=AsyncMock)
    @patch("app.cache.redis_client.get_cached", new_callable=AsyncMock)
    @patch("app.rag.qa_chain.retrieve")
    @patch("app.rag.vector_store.hybrid_search_qdrant")
    async def test_hit_plain_string_fallback(self, mock_hybrid_search, mock_retrieve, mock_get_cached, mock_set_cached, mock_redis):
        """Old plain-string cache entries should be skipped and re-queried."""
        mock_get_cached.return_value = "Plain cached answer"
        mock_retrieve.return_value = []
        mock_hybrid_search.return_value = []
        llm_fn = MagicMock()
        result = await rag_query_with_cache("test query", llm_fn, lang="en")
        # Should NOT return the plain string — should fall through to fresh query
        assert result.answer != "Plain cached answer"
        # Fresh query was made (hybrid_search_qdrant or retrieve called)
        assert mock_hybrid_search.called or mock_retrieve.called
