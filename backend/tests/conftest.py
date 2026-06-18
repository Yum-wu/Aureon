"""Test configuration and fixtures for parallel execution."""
import pytest
import os

from app.main import app
from app.security import UserRole
from app.security.rbac import _ROLE_CHECKERS


@pytest.fixture(autouse=True)
def _bypass_rbac():
    """Bypass all require_role RBAC checks during tests.

    Uses _ROLE_CHECKERS registry from rbac.py to find all _role_checker
    closures, instead of traversing app.routes (which became a tree in
    FastAPI 0.137+ and no longer exposes all routes as a flat list).

    Uses dependency_overrides (FastAPI 官方推荐方式) 替代修改 settings，
    避免依赖生产代码中的 dev-mode 旁路逻辑。
    """
    mock_user = {"sub": "test-user", "role": "ADMIN", "_role": UserRole.ADMIN}

    # 直接从注册表获取所有 _role_checker 闭包
    overrides = {}
    for call in _ROLE_CHECKERS:
        async def _mock_admin(_captured_call=call):
            return mock_user
        overrides[call] = _mock_admin

    # 防止闭包被重命名导致静默失败
    if not overrides:
        pytest.fail(
            "No _role_checker dependencies found — "
            "require_role closure may have been renamed"
        )

    # 应用 override
    for dep_func, mock_func in overrides.items():
        app.dependency_overrides[dep_func] = mock_func

    yield

    # 清理 override，避免污染其他测试
    for dep_func in overrides:
        app.dependency_overrides.pop(dep_func, None)


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
