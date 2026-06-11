"""Tests that vector_store works without ChromaDB (Phase 2)."""


class TestNoChromaDependency:
    """Vector store should function with Qdrant as sole backend."""

    def test_import_succeeds_without_chroma(self):
        """Importing vector_store should not require chromadb."""
        import importlib
        import sys
        # Ensure chromadb is not in sys.modules
        saved = sys.modules.pop("chromadb", None)
        saved_import = sys.modules.pop("chromadb.api", None)
        import app.rag.vector_store as vs
        assert vs is not None
        # Clean up and restore
        if saved:
            sys.modules["chromadb"] = saved
        if saved_import:
            sys.modules["chromadb.api"] = saved_import

    def test_no_chroma_client_global(self):
        """No _chroma_client global should exist after import."""
        import app.rag.vector_store as vs
        assert not hasattr(vs, "_chroma_client") or vs._chroma_client is None

    def test_no_chroma_collection_global(self):
        """No _chroma_collection global should exist after import."""
        import app.rag.vector_store as vs
        assert not hasattr(vs, "_chroma_collection") or vs._chroma_collection is None

    def test_retrieve_uses_qdrant(self):
        """retrieve should not reference chroma."""
        import app.rag.vector_store as vs
        assert hasattr(vs, "retrieve")
        import inspect
        source = inspect.getsource(vs.retrieve)
        assert "chroma" not in source.lower()

    def test_no_chroma_client_functions(self):
        """Chroma-specific helper functions should be removed."""
        import app.rag.vector_store as vs
        chroma_names = [
            "_get_chroma", "_get_collection", "_reset_chroma",
            "_add_to_index_chroma", "_delete_from_index_chroma",
            "_get_collection_stats_chroma", "_get_indexed_sources_chroma",
            "_load_docs_from_chroma", "_migrate_from_chroma",
        ]
        for name in chroma_names:
            assert not hasattr(vs, name), f"{name} should be removed"
