import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.cost.budget_engine import BudgetEngine, get_budget_engine
from app.cost.models import BudgetConfigNew


class TestBudgetEngine:
    def test_get_budget_engine_singleton(self):
        engine1 = get_budget_engine()
        engine2 = get_budget_engine()
        assert engine1 is engine2

    def test_redis_unavailable_returns_none(self):
        engine = BudgetEngine()
        assert engine._get_redis() is None

    @pytest.mark.asyncio
    async def test_check_budget_no_config(self):
        engine = BudgetEngine()
        async def mock_get(key):
            return None
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        result = await engine.check_budget("tenant_1")
        assert result is None

    @pytest.mark.asyncio
    async def test_check_budget_below_warning(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            warning_threshold=0.8,
            critical_threshold=0.95,
            hard_limit=False,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get
        engine._fire_alert = AsyncMock()

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=50.0)):
            result = await engine.check_budget("tenant_1")
            assert result is None

    @pytest.mark.asyncio
    async def test_check_budget_warning_alert(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            warning_threshold=0.8,
            critical_threshold=0.95,
            hard_limit=False,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get
        engine._fire_alert = AsyncMock()

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=85.0)):
            result = await engine.check_budget("tenant_1")
            assert result is not None
            assert result.threshold_type == "warning"
            assert result.percentage == 85.0

    @pytest.mark.asyncio
    async def test_check_budget_critical_alert(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            warning_threshold=0.8,
            critical_threshold=0.95,
            hard_limit=False,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get
        engine._fire_alert = AsyncMock()

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=96.0)):
            result = await engine.check_budget("tenant_1")
            assert result is not None
            assert result.threshold_type == "critical"

    @pytest.mark.asyncio
    async def test_check_budget_hard_limit_alert(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            warning_threshold=0.8,
            critical_threshold=0.95,
            hard_limit=True,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get
        engine._fire_alert = AsyncMock()

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=100.0)):
            result = await engine.check_budget("tenant_1")
            assert result is not None
            assert result.threshold_type == "hard_limit"

    @pytest.mark.asyncio
    async def test_check_budget_zero_usage(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            warning_threshold=0.8,
            critical_threshold=0.95,
            hard_limit=False,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get
        engine._fire_alert = AsyncMock()

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=0.0)):
            result = await engine.check_budget("tenant_1")
            assert result is None

    @pytest.mark.asyncio
    async def test_check_budget_fires_alert(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            warning_threshold=0.8,
            critical_threshold=0.95,
            hard_limit=False,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get
        engine._fire_alert = AsyncMock()

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=85.0)):
            result = await engine.check_budget("tenant_1")
            engine._fire_alert.assert_awaited_once_with(result)

    @pytest.mark.asyncio
    async def test_set_budget_config_without_workspace(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
        )
        engine = BudgetEngine()
        mock_redis = AsyncMock()
        engine._redis = mock_redis

        await engine.set_budget_config(config)
        mock_redis.set.assert_awaited_once()
        key = mock_redis.set.call_args[0][0]
        assert "tenant_1" in key
        assert "ws:" not in key

    @pytest.mark.asyncio
    async def test_set_budget_config_with_workspace(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            workspace_id="ws_1",
            monthly_limit_usd=100.0,
        )
        engine = BudgetEngine()
        mock_redis = AsyncMock()
        engine._redis = mock_redis

        await engine.set_budget_config(config)
        mock_redis.set.assert_awaited_once()
        key = mock_redis.set.call_args[0][0]
        assert "ws:ws_1" in key

    @pytest.mark.asyncio
    async def test_set_budget_config_no_redis(self):
        config = BudgetConfigNew(tenant_id="t1", monthly_limit_usd=100)
        engine = BudgetEngine()
        await engine.set_budget_config(config)

    @pytest.mark.asyncio
    async def test_should_block_query_no_config(self):
        engine = BudgetEngine()
        async def mock_get(key):
            return None
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        result = await engine.should_block_query("tenant_1")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_block_query_not_hard_limit(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            hard_limit=False,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        result = await engine.should_block_query("tenant_1")
        assert result is False

    @pytest.mark.asyncio
    async def test_should_block_query_under_limit(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            hard_limit=True,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=50.0)):
            result = await engine.should_block_query("tenant_1")
            assert result is False

    @pytest.mark.asyncio
    async def test_should_block_query_over_limit(self):
        config = BudgetConfigNew(
            tenant_id="tenant_1",
            monthly_limit_usd=100.0,
            hard_limit=True,
        )
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        with patch.object(engine, "_get_monthly_usage", AsyncMock(return_value=100.0)):
            result = await engine.should_block_query("tenant_1")
            assert result is True

    @pytest.mark.asyncio
    async def test_get_monthly_usage_no_redis(self):
        engine = BudgetEngine()
        result = await engine._get_monthly_usage("tenant_1")
        assert result == 0.0

    @pytest.mark.asyncio
    async def test_get_monthly_usage_with_data(self):
        class _FakePipe:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *a):
                pass
            async def hgetall(self, key):
                return {"total_cost": "50.0"}
            async def execute(self):
                return [{"total_cost": "50.0"}]

        engine = BudgetEngine()
        engine._redis = MagicMock()
        engine._redis.pipeline = lambda transaction=False: _FakePipe()

        result = await engine._get_monthly_usage("tenant_1")
        assert result == 50.0

    @pytest.mark.asyncio
    async def test_get_budget_config_no_redis(self):
        engine = BudgetEngine()
        result = await engine.get_budget_config("tenant_1")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_budget_config_tenant_level(self):
        config = BudgetConfigNew(tenant_id="t1", monthly_limit_usd=100)
        engine = BudgetEngine()
        config_bytes = config.model_dump_json().encode()
        async def mock_get(key):
            return config_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        result = await engine.get_budget_config("t1")
        assert result is not None
        assert result.monthly_limit_usd == 100.0

    @pytest.mark.asyncio
    async def test_get_budget_config_workspace_preferred(self):
        tenant_config = BudgetConfigNew(tenant_id="t1", monthly_limit_usd=100)
        ws_config = BudgetConfigNew(tenant_id="t1", workspace_id="ws_1", monthly_limit_usd=200)

        engine = BudgetEngine()
        ws_bytes = ws_config.model_dump_json().encode()
        tenant_bytes = tenant_config.model_dump_json().encode()
        async def mock_get(key):
            if "ws:ws_1" in key:
                return ws_bytes
            return tenant_bytes
        engine._redis = MagicMock()
        engine._redis.get = mock_get

        result = await engine.get_budget_config("t1", "ws_1")
        assert result is not None
        assert result.monthly_limit_usd == 200.0

    def test_budget_alert_fields(self):
        from app.cost.models import BudgetAlert
        from datetime import datetime, timezone

        alert = BudgetAlert(
            id="test-id",
            tenant_id="t1",
            threshold_type="warning",
            current_usage=50.0,
            budget_limit=100.0,
            percentage=50.0,
            created_at=datetime.now(timezone.utc),
        )
        assert alert.id == "test-id"
        assert alert.threshold_type == "warning"
        assert alert.current_usage == 50.0

    def test_budget_config_defaults(self):
        config = BudgetConfigNew(tenant_id="t1", monthly_limit_usd=100)
        assert config.warning_threshold == 0.8
        assert config.critical_threshold == 0.95
        assert config.hard_limit is False
