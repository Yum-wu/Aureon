from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from qdrant_client import models as qmodels

from app.rag.qdrant_ops import (
    _estimate_embedding_tokens,
    _iter_embedding_ranges,
    _provider_safe_embedding_text,
    hybrid_search_qdrant,
    save_index_qdrant,
)


def test_estimate_embedding_tokens_weights_cjk_more_than_ascii():
    assert _estimate_embedding_tokens("a" * 4000) == 1000
    assert _estimate_embedding_tokens("法" * 4000) == 4000


def test_iter_embedding_ranges_respects_count_and_token_budget():
    chunks = [
        {"text": "法" * 3000},
        {"text": "务" * 3000},
        {"text": "风" * 3000},
        {"text": "d"},
    ]

    assert _iter_embedding_ranges(chunks, max_items=10, max_estimated_tokens=7000) == [
        (0, 2),
        (2, 4),
    ]


def test_iter_embedding_ranges_batches_long_ascii_chunks_by_estimated_tokens():
    chunks = [{"text": "a" * 6000} for _ in range(6)]

    assert _iter_embedding_ranges(chunks, max_items=10, max_estimated_tokens=7000) == [
        (0, 4),
        (4, 6),
    ]


def test_iter_embedding_ranges_respects_item_limit():
    chunks = [{"text": "x"} for _ in range(12)]

    assert _iter_embedding_ranges(chunks, max_items=10, max_estimated_tokens=7000) == [
        (0, 10),
        (10, 12),
    ]


def test_iter_embedding_ranges_default_splits_oversized_structured_chunks():
    chunks = [{"text": "a" * 24000} for _ in range(25)]

    assert _iter_embedding_ranges(chunks) == [(i, i + 1) for i in range(25)]


def test_provider_safe_embedding_text_truncates_long_payload_only_for_embedding():
    text = "a" * 1200

    result = _provider_safe_embedding_text(text)

    assert len(result) == 900
    assert text.startswith(result)


def test_save_index_qdrant_uses_safe_text_for_combined_embedding_only():
    original_text = "x" * 1200
    fake_client = MagicMock()
    fake_client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={"dense": SimpleNamespace(size=3, distance=qmodels.Distance.COSINE)},
                sparse_vectors={"sparse": object()},
            )
        )
    )
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_api_key="test-key",
        dashscope_model="text-embedding-v4",
        vectors_on_disk=False,
        hnsw_m=16,
        hnsw_ef_construct=100,
        quantization_enabled=False,
        hnsw_ef_search=64,
    )

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._get_embedding_dim", return_value=3), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               return_value=(np.array([[0.1, 0.2, 0.3]], dtype=np.float32), [{"sentinel": 1.0}])) as mock_embed, \
         patch("app.rag.embedding._to_sparse_vector",
               return_value=qmodels.SparseVector(indices=[1], values=[1.0])):
        save_index_qdrant([{"text": original_text, "metadata": {"slug": "long-upload"}}])

    embedded_texts = mock_embed.call_args.args[0]
    assert embedded_texts == [original_text[:900]]
    point = fake_client.upsert.call_args.kwargs["points"][0]
    assert point.payload["text"] == original_text


def test_save_index_qdrant_combined_embeds_each_text_individually():
    texts = ["a" * 1200, "b" * 1200, "c" * 1200]
    fake_client = MagicMock()
    fake_client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={"dense": SimpleNamespace(size=3, distance=qmodels.Distance.COSINE)},
                sparse_vectors={"sparse": object()},
            )
        )
    )
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_api_key="test-key",
        dashscope_model="text-embedding-v4",
        vectors_on_disk=False,
        hnsw_m=16,
        hnsw_ef_construct=100,
        quantization_enabled=False,
        hnsw_ef_search=64,
    )
    dense_vectors = [
        np.array([[0.1, 0.2, 0.3]], dtype=np.float32),
        np.array([[0.4, 0.5, 0.6]], dtype=np.float32),
        np.array([[0.7, 0.8, 0.9]], dtype=np.float32),
    ]

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._get_embedding_dim", return_value=3), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               side_effect=[(dense, [{"sentinel": 1.0}]) for dense in dense_vectors]) as mock_embed, \
         patch("app.rag.embedding._to_sparse_vector",
               return_value=qmodels.SparseVector(indices=[1], values=[1.0])):
        save_index_qdrant([{"text": text, "metadata": {"slug": f"long-{i}"}} for i, text in enumerate(texts)])

    assert [call.args[0] for call in mock_embed.call_args_list] == [[text[:900]] for text in texts]
    assert len(fake_client.upsert.call_args.kwargs["points"]) == 3


def test_save_index_qdrant_fallback_embeds_each_text_individually():
    texts = ["a" * 1200, "b" * 1200, "c" * 1200]
    fake_client = MagicMock()
    fake_client.get_collection.return_value = SimpleNamespace(
        config=SimpleNamespace(
            params=SimpleNamespace(
                vectors={"dense": SimpleNamespace(size=3, distance=qmodels.Distance.COSINE)},
                sparse_vectors={"sparse": object()},
            )
        )
    )
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_api_key="test-key",
        dashscope_model="text-embedding-v4",
        vectors_on_disk=False,
        hnsw_m=16,
        hnsw_ef_construct=100,
        quantization_enabled=False,
        hnsw_ef_search=64,
    )
    dense_vectors = [
        np.array([[0.1, 0.2, 0.3]], dtype=np.float32),
        np.array([[0.4, 0.5, 0.6]], dtype=np.float32),
        np.array([[0.7, 0.8, 0.9]], dtype=np.float32),
    ]

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._get_embedding_dim", return_value=3), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               side_effect=RuntimeError("combined rejected batch")), \
         patch("app.rag.embedding.embed_texts_llm",
               side_effect=dense_vectors) as mock_embed, \
         patch("app.rag.sparse_embed.embed_sparse",
               return_value=[{"sentinel": 1.0}, {"sentinel": 1.0}, {"sentinel": 1.0}]), \
         patch("app.rag.embedding._to_sparse_vector",
               return_value=qmodels.SparseVector(indices=[1], values=[1.0])):
        save_index_qdrant([{"text": text, "metadata": {"slug": f"long-{i}"}} for i, text in enumerate(texts)])

    assert [call.args[0] for call in mock_embed.call_args_list] == [[text[:900]] for text in texts]
    assert len(fake_client.upsert.call_args.kwargs["points"]) == 3


def test_hybrid_search_qdrant_keeps_keyword_candidates_when_sparse_enabled():
    keyword_doc = {
        "text": "AUREON_TENANT_SENTINEL_MD_80F329A upload content",
        "metadata": {
            "source": "aureon-tenant-fix-md-80f329a.md",
            "slug": "aureon-tenant-fix-md-80f329a",
        },
        "score": 1.0,
    }
    vector_point = SimpleNamespace(
        id="vector-1",
        score=0.9,
        payload={
            "text": "unrelated pricing content",
            "metadata": {"source": "pricing.md", "slug": "pricing"},
        },
    )
    fake_client = MagicMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[vector_point])

    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_model="text-embedding-v4",
        hnsw_ef_search=64,
        rerank_enabled=False,
    )

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               return_value=([np.array([0.1, 0.2, 0.3], dtype=np.float32)], [{"sentinel": 1.0}])), \
         patch("app.rag.embedding._to_sparse_vector",
               return_value=qmodels.SparseVector(indices=[1], values=[1.0])), \
         patch("app.rag.bm25.retrieve_keyword", return_value=[keyword_doc]):
        results = hybrid_search_qdrant(
            "AUREON_TENANT_SENTINEL_MD_80F329A",
            top_k=2,
            query_complexity="simple",
        )

    assert [r["metadata"]["source"] for r in results] == [
        "aureon-tenant-fix-md-80f329a.md",
        "pricing.md",
    ]


def test_hybrid_search_qdrant_preserves_strong_keyword_hits_after_rerank():
    keyword_doc = {
        "text": "AUREON_TENANT_SENTINEL_MD_80F329A upload content",
        "metadata": {
            "source": "aureon-tenant-fix-md-80f329a.md",
            "slug": "aureon-tenant-fix-md-80f329a",
        },
        "score": 0.95,
    }
    vector_point = SimpleNamespace(
        id="vector-1",
        score=0.9,
        payload={
            "text": "unrelated pricing content",
            "metadata": {"source": "pricing.md", "slug": "pricing"},
        },
    )
    fake_client = MagicMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[vector_point])
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_model="text-embedding-v4",
        hnsw_ef_search=64,
        rerank_enabled=True,
    )

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               return_value=([np.array([0.1, 0.2, 0.3], dtype=np.float32)], [{"sentinel": 1.0}])), \
         patch("app.rag.embedding._to_sparse_vector",
               return_value=qmodels.SparseVector(indices=[1], values=[1.0])), \
         patch("app.rag.bm25.retrieve_keyword", return_value=[keyword_doc]), \
         patch("app.rag.reranker.rerank", return_value=[{
             "text": "unrelated pricing content",
             "metadata": {"source": "pricing.md", "slug": "pricing"},
             "score": 0.9,
             "rerank_score": 0.99,
         }]):
        results = hybrid_search_qdrant(
            "AUREON_TENANT_SENTINEL_MD_80F329A",
            top_k=1,
            query_complexity="simple",
        )

    assert results[0]["metadata"]["source"] == "aureon-tenant-fix-md-80f329a.md"


def test_hybrid_search_qdrant_preserves_exact_payload_hits_after_rerank():
    exact_point = SimpleNamespace(
        id="exact-1",
        payload={
            "text": "Uploaded file contains AUREON_TENANT_SENTINEL_PDF_80F329A.",
            "metadata": {
                "source": "aureon-tenant-fix-pdf-80f329a.pdf",
                "slug": "aureon-tenant-fix-pdf-80f329a",
                "tenant_id": "default",
            },
        },
    )
    vector_point = SimpleNamespace(
        id="vector-1",
        score=0.9,
        payload={
            "text": "unrelated pricing content",
            "metadata": {"source": "pricing.md", "slug": "pricing"},
        },
    )
    fake_client = MagicMock()
    fake_client.query_points.return_value = SimpleNamespace(points=[vector_point])
    fake_client.scroll.return_value = ([exact_point], None)
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_model="text-embedding-v4",
        hnsw_ef_search=64,
        rerank_enabled=True,
    )

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               return_value=([np.array([0.1, 0.2, 0.3], dtype=np.float32)], [{"sentinel": 1.0}])), \
         patch("app.rag.embedding._to_sparse_vector",
               return_value=qmodels.SparseVector(indices=[1], values=[1.0])), \
         patch("app.rag.bm25.retrieve_keyword", return_value=[]), \
         patch("app.rag.reranker.rerank", return_value=[{
             "text": "unrelated pricing content",
             "metadata": {"source": "pricing.md", "slug": "pricing"},
             "score": 0.9,
             "rerank_score": 0.99,
         }]):
        results = hybrid_search_qdrant(
            "AUREON_TENANT_SENTINEL_PDF_80F329A",
            top_k=1,
            query_complexity="simple",
        )

    assert results[0]["metadata"]["source"] == "aureon-tenant-fix-pdf-80f329a.pdf"


def test_hybrid_search_qdrant_exact_payload_searches_parent_text():
    exact_point = SimpleNamespace(
        id="exact-1",
        payload={
            "text": "Contextual prefix without the sentinel.",
            "metadata": {
                "parent_text": "Workbook row contains AUREON TENANT SENTINEL XLSX 80F329A.",
                "source": "aureon-tenant-fix-xlsx-80f329a.xlsx",
                "slug": "aureon-tenant-fix-xlsx-80f329a",
                "tenant_id": "default",
            },
        },
    )
    fake_client = MagicMock()
    fake_client.scroll.return_value = ([exact_point], None)
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_model="text-embedding-v4",
        hnsw_ef_search=64,
        rerank_enabled=True,
    )

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               side_effect=RuntimeError("embedding rejected query")), \
         patch("app.rag.bm25.retrieve_keyword", return_value=[]):
        results = hybrid_search_qdrant(
            "AUREON_TENANT_SENTINEL_XLSX_80F329A",
            top_k=1,
            query_complexity="simple",
        )

    assert results[0]["metadata"]["source"] == "aureon-tenant-fix-xlsx-80f329a.xlsx"


def test_hybrid_search_qdrant_uses_exact_payload_when_embedding_fails():
    exact_point = SimpleNamespace(
        id="exact-1",
        payload={
            "text": "AUREON_TENANT_SENTINEL_TXT_80F329A upload content",
            "metadata": {
                "source": "aureon-tenant-fix-txt-80f329a.txt",
                "slug": "aureon-tenant-fix-txt-80f329a",
            },
        },
    )
    fake_client = MagicMock()
    fake_client.scroll.return_value = ([exact_point], None)
    settings = SimpleNamespace(
        sparse_enabled=True,
        dashscope_model="text-embedding-v4",
        hnsw_ef_search=64,
        rerank_enabled=True,
    )

    with patch("app.rag.qdrant_ops.settings", settings), \
         patch("app.rag.qdrant_ops._get_qdrant", return_value=fake_client), \
         patch("app.rag.embedding._embed_dense_sparse_dashscope",
               side_effect=RuntimeError("embedding rejected query")), \
         patch("app.rag.bm25.retrieve_keyword", return_value=[]) as mock_keyword:
        results = hybrid_search_qdrant(
            "AUREON_TENANT_SENTINEL_TXT_80F329A",
            top_k=1,
            query_complexity="simple",
        )

    assert results[0]["metadata"]["source"] == "aureon-tenant-fix-txt-80f329a.txt"
    mock_keyword.assert_not_called()
