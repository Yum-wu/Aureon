"""Tests for vector store interface contract."""
import pytest
from app.vector_store_interface import VectorStoreInterface


class TestVectorStoreInterface:
    def test_is_abstract(self):
        """VectorStoreInterface should not be instantiable."""
        with pytest.raises(TypeError):
            VectorStoreInterface()

    def test_requires_all_methods(self):
        """Incomplete implementation should fail."""
        class Incomplete(VectorStoreInterface):
            pass
        with pytest.raises(TypeError):
            Incomplete()
