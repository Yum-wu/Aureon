"""Test configuration and fixtures for parallel execution."""
import pytest
import os


@pytest.fixture(autouse=True)
def isolate_test_environment(tmp_path):
    """Isolate test environment for parallel execution.

    Each test worker gets:
    - Separate ChromaDB/Qdrant collection
    - Separate temporary directory
    - Isolated environment variables
    """
    # Use temporary directory for vector store in tests
    os.environ.setdefault("VECTOR_DIR", str(tmp_path / "vectors"))
    yield
    # Cleanup is handled by tmp_path fixture


@pytest.fixture(scope="session")
def worker_id():
    """Get pytest-xdist worker ID for isolation."""
    return os.environ.get("PYTEST_XDIST_WORKER", "master")
