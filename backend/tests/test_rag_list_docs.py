from types import SimpleNamespace
from unittest.mock import MagicMock, patch


def test_list_rag_docs_dedupes_chunks_by_slug_and_source():
    from app.tools.rag_list_docs import list_rag_docs

    client = MagicMock()
    client.scroll.return_value = (
        [
            SimpleNamespace(
                payload={
                    "metadata": {
                        "slug": "pricing",
                        "title": "Pricing",
                        "source": "pricing.pdf",
                        "file_type": "pdf",
                        "uploaded": True,
                    }
                }
            ),
            SimpleNamespace(
                payload={
                    "metadata": {
                        "slug": "pricing",
                        "title": "Pricing",
                        "source": "pricing.pdf",
                        "file_type": "pdf",
                        "uploaded": True,
                    }
                }
            ),
            SimpleNamespace(
                payload={
                    "metadata": {
                        "slug": "pipeline",
                        "title": "Pipeline",
                        "source": "pipeline.xlsx",
                        "file_type": "xlsx",
                        "uploaded": True,
                    }
                }
            ),
        ],
        None,
    )

    with patch("app.tools.rag_list_docs._get_qdrant", return_value=client), \
         patch("app.tools.rag_list_docs._get_qdrant_collection_name", return_value="aureon"):
        docs = list_rag_docs(tenant_id="tenant-a")

    assert docs == [
        {
            "slug": "pricing",
            "title": "Pricing",
            "source": "pricing.pdf",
            "file_type": "pdf",
            "uploaded": True,
        },
        {
            "slug": "pipeline",
            "title": "Pipeline",
            "source": "pipeline.xlsx",
            "file_type": "xlsx",
            "uploaded": True,
        },
    ]
    assert client.scroll.call_args.kwargs["with_payload"] is True
    assert client.scroll.call_args.kwargs["with_vectors"] is False


def test_list_rag_docs_handles_missing_metadata():
    from app.tools.rag_list_docs import list_rag_docs

    client = MagicMock()
    client.scroll.return_value = (
        [
            SimpleNamespace(payload={"text": "chunk only"}),
            SimpleNamespace(payload={"metadata": {"source": "notes.txt"}}),
        ],
        None,
    )

    with patch("app.tools.rag_list_docs._get_qdrant", return_value=client), \
         patch("app.tools.rag_list_docs._get_qdrant_collection_name", return_value="aureon"):
        docs = list_rag_docs()

    assert docs == [
        {
            "slug": "notes",
            "title": "notes",
            "source": "notes.txt",
            "file_type": "txt",
            "uploaded": False,
        }
    ]


def test_list_rag_docs_passes_tenant_filter_to_qdrant():
    from app.tools.rag_list_docs import list_rag_docs

    client = MagicMock()
    client.scroll.return_value = ([], None)

    with patch("app.tools.rag_list_docs._get_qdrant", return_value=client), \
         patch("app.tools.rag_list_docs._get_qdrant_collection_name", return_value="aureon"):
        list_rag_docs(tenant_id="tenant-a")

    scroll_filter = client.scroll.call_args.kwargs["scroll_filter"]
    condition = scroll_filter.must[0]
    assert condition.key == "metadata.tenant_id"
    assert condition.match.value == "tenant-a"
