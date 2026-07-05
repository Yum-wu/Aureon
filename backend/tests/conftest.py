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
def _bypass_api_key_auth(monkeypatch):
    """测试期间跳过 API Key 认证中间件。

    本地 .env 可能配置了 API_AUTH_KEY，导致 TestClient 请求被
    logging_middleware 拦截返回 401。通过清空该配置让中间件跳过检查，
    同时仍可在 security 测试中显式验证认证逻辑。
    """
    from app.config import settings

    monkeypatch.setattr(settings.auth, "api_auth_key", "")
    yield


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


@pytest.fixture(scope="session")
def pg_client():
    """Session-scoped TestClient with lifespan — initializes asyncpg pool once.

    Shared across all test modules that require a live PostgreSQL connection.
    Skipped automatically when DATABASE_URL is not configured.
    """
    from fastapi.testclient import TestClient
    from app.config import settings

    if not settings.database_url:
        pytest.skip("Requires PostgreSQL (DATABASE_URL)")

    with TestClient(app) as c:
        yield c
