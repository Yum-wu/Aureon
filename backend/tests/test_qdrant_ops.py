from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
from qdrant_client import models as qmodels

from app.rag.qdrant_ops import _iter_embedding_ranges, hybrid_search_qdrant


def test_iter_embedding_ranges_respects_count_and_char_budget():
    chunks = [
        {"text": "a" * 3000},
        {"text": "b" * 3000},
        {"text": "c" * 3000},
        {"text": "d"},
    ]

    assert _iter_embedding_ranges(chunks, max_items=10, max_chars=8000) == [
        (0, 2),
        (2, 4),
    ]


def test_iter_embedding_ranges_respects_item_limit():
    chunks = [{"text": "x"} for _ in range(12)]

    assert _iter_embedding_ranges(chunks, max_items=10, max_chars=8000) == [
        (0, 10),
        (10, 12),
    ]


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
