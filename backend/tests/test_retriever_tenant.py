from types import SimpleNamespace
from unittest.mock import patch

from app.rag.retriever import hybrid_retrieve


def test_hybrid_retrieve_passes_current_tenant_to_qdrant_hybrid_search():
    settings = SimpleNamespace(sparse_enabled=True)

    with patch("app.rag.retriever.settings", settings), \
         patch("app.multi_tenant.middleware.get_current_tenant_id", return_value="tenant-a"), \
         patch("app.rag.vector_store.hybrid_search_qdrant", return_value=[]) as mock_hybrid:
        hybrid_retrieve("AUREON_TENANT_SENTINEL_PDF_80F329A", top_k=3)

    assert mock_hybrid.call_args.kwargs["tenant_id"] == "tenant-a"
