# -*- coding: utf-8 -*-
"""Phase 3/4 可靠性模块单元测试。

覆盖：
- Bulkhead 隔舱模式（bulkhead.py）
- 超时级联（timeouts.py）
- Chaos Engineering（chaos.py）
"""

import asyncio
import random as random_module

import pytest

from app.reliability.bulkhead import (
    Bulkhead,
    BulkheadFullError,
    bulkhead,
    get_bulkhead,
    get_all_bulkhead_stats,
    reset_all_bulkheads,
    redis_bulkhead,
    qdrant_bulkhead,
    llm_bulkhead,
    embedding_bulkhead,
)
from app.reliability.timeouts import (
    TIMEOUT_HIERARCHY,
    TimeoutError as LayerTimeoutError,
    with_timeout,
    call_with_timeout,
)
from app.reliability.chaos import (
    ChaosConfig,
    chaos,
    enable_chaos,
    disable_chaos,
    is_chaos_enabled,
    register_chaos_rule,
)


# ──────────────────────────────────────────────────────────────────────────────
# Bulkhead 测试
# ──────────────────────────────────────────────────────────────────────────────


class TestBulkhead:
    """Bulkhead 隔舱模式测试。"""

    @pytest.mark.asyncio
    async def test_normal_execution(self):
        """测试正常执行（并发数内）。"""
        bh = Bulkhead(name="test_normal", max_concurrent=2, max_queue=2)

        async def echo(x: int) -> int:
            return x

        result = await bh.execute(echo, 42)
        assert result == 42
        # 执行完成后状态归零
        assert bh.stats["active"] == 0
        assert bh.stats["queued"] == 0

    @pytest.mark.asyncio
    async def test_concurrent_limit_queues(self):
        """测试并发限制：超过 max_concurrent 时排队等待。"""
        bh = Bulkhead(name="test_concurrent", max_concurrent=1, max_queue=5)

        started: list[int] = []
        finished: list[int] = []

        async def worker(i: int) -> int:
            started.append(i)
            await asyncio.sleep(0.05)
            finished.append(i)
            return i

        # 并发启动 3 个任务，但只有 1 个能同时执行
        tasks = [asyncio.create_task(bh.execute(worker, i)) for i in range(3)]
        results = await asyncio.gather(*tasks)

        assert results == [0, 1, 2]
        # 所有任务都完成
        assert len(finished) == 3
        # 由于 max_concurrent=1，任务应串行执行（started 顺序与 finished 顺序一致）
        assert started == finished

    @pytest.mark.asyncio
    async def test_queue_full_raises_error(self):
        """测试队列满时抛出 BulkheadFullError。"""
        # max_concurrent=1, max_queue=1：1 个执行 + 1 个排队 = 2 个并发任务上限
        bh = Bulkhead(name="test_full", max_concurrent=1, max_queue=1)

        started = asyncio.Event()

        async def blocker() -> str:
            started.set()
            await asyncio.sleep(0.3)
            return "done"

        async def quick() -> str:
            return "quick"

        # 第 1 个任务占用并发槽位
        task1 = asyncio.create_task(bh.execute(blocker))
        await started.wait()

        # 第 2 个任务进入排队
        task2 = asyncio.create_task(bh.execute(quick))
        await asyncio.sleep(0.01)  # 让 task2 进入排队

        # 第 3 个任务：队列已满，应立即抛出 BulkheadFullError
        with pytest.raises(BulkheadFullError):
            await bh.execute(quick)

        # 清理
        await task1
        await task2

    @pytest.mark.asyncio
    async def test_stats_returns_correct_values(self):
        """测试 stats 属性返回正确的活跃/排队计数。"""
        bh = Bulkhead(name="test_stats", max_concurrent=2, max_queue=3)

        # 初始状态
        stats = bh.stats
        assert stats["name"] == "test_stats"
        assert stats["active"] == 0
        assert stats["queued"] == 0
        assert stats["max_concurrent"] == 2
        assert stats["max_queue"] == 3

        in_progress = asyncio.Event()

        async def long_task() -> str:
            in_progress.set()
            await asyncio.sleep(0.2)
            return "done"

        # 启动 1 个任务占用并发槽位
        task = asyncio.create_task(bh.execute(long_task))
        await in_progress.wait()
        await asyncio.sleep(0.01)

        assert bh.stats["active"] == 1
        assert bh.stats["queued"] == 0

        await task
        assert bh.stats["active"] == 0

    @pytest.mark.asyncio
    async def test_decorator_usage(self):
        """测试装饰器用法。"""
        bh = Bulkhead(name="test_decorator", max_concurrent=2, max_queue=2)

        @bulkhead(bh)
        async def add(a: int, b: int) -> int:
            return a + b

        result = await add(3, 5)
        assert result == 8

        # 装饰器应暴露 _bulkhead 实例
        assert hasattr(add, "_bulkhead")
        assert add._bulkhead is bh  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_exception_propagation(self):
        """测试被保护函数抛出的异常正确传播。"""
        bh = Bulkhead(name="test_exc", max_concurrent=1, max_queue=1)

        async def failing() -> None:
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await bh.execute(failing)

        # 异常后状态应归零
        assert bh.stats["active"] == 0
        assert bh.stats["queued"] == 0

    @pytest.mark.asyncio
    async def test_preconfigured_instances(self):
        """测试预配置舱壁实例。"""
        assert redis_bulkhead.name == "redis"
        assert redis_bulkhead.stats["max_concurrent"] == 20
        assert redis_bulkhead.stats["max_queue"] == 50

        assert qdrant_bulkhead.name == "qdrant"
        assert qdrant_bulkhead.stats["max_concurrent"] == 10

        assert llm_bulkhead.name == "llm"
        assert llm_bulkhead.stats["max_concurrent"] == 5

        assert embedding_bulkhead.name == "embedding"
        assert embedding_bulkhead.stats["max_concurrent"] == 8

    @pytest.mark.asyncio
    async def test_get_bulkhead_returns_instance(self):
        """测试 get_bulkhead 返回正确实例。"""
        assert get_bulkhead("redis") is redis_bulkhead
        assert get_bulkhead("qdrant") is qdrant_bulkhead
        assert get_bulkhead("llm") is llm_bulkhead
        assert get_bulkhead("embedding") is embedding_bulkhead

        with pytest.raises(KeyError):
            get_bulkhead("nonexistent")

    @pytest.mark.asyncio
    async def test_get_all_bulkhead_stats(self):
        """测试获取所有舱壁统计。"""
        stats = get_all_bulkhead_stats()
        assert isinstance(stats, list)
        assert len(stats) == 4
        names = {s["name"] for s in stats}
        assert names == {"redis", "qdrant", "llm", "embedding"}

    @pytest.mark.asyncio
    async def test_reset_all_bulkheads(self):
        """测试重置所有舱壁计数器。"""
        # 先制造一些状态
        bh = Bulkhead(name="temp", max_concurrent=1, max_queue=1)
        bh._active = 5
        bh._queued = 3

        # 重置全局实例（不影响独立创建的实例）
        reset_all_bulkheads()

        # 全局实例计数应归零
        for stats in get_all_bulkhead_stats():
            assert stats["active"] == 0
            assert stats["queued"] == 0


# ──────────────────────────────────────────────────────────────────────────────
# Timeouts 测试
# ──────────────────────────────────────────────────────────────────────────────


class TestTimeouts:
    """超时级联测试。"""

    @pytest.mark.asyncio
    async def test_normal_execution_no_timeout(self):
        """测试正常执行（未超时）。"""
        @with_timeout("llm", timeout=1.0)
        async def quick_func() -> str:
            await asyncio.sleep(0.01)
            return "success"

        result = await quick_func()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_timeout_raises_error(self):
        """测试超时抛出 LayerTimeoutError。"""
        @with_timeout("llm", timeout=0.05)
        async def slow_func() -> str:
            await asyncio.sleep(1.0)
            return "should not reach"

        with pytest.raises(LayerTimeoutError) as exc_info:
            await slow_func()

        # 验证异常携带层级信息
        assert exc_info.value.layer == "llm"
        assert exc_info.value.timeout == 0.05

    @pytest.mark.asyncio
    async def test_custom_timeout_value(self):
        """测试自定义超时值覆盖默认配置。"""
        # 使用极短的自定义超时
        @with_timeout("api", timeout=0.01)
        async def slow_func() -> str:
            await asyncio.sleep(0.5)
            return "should not reach"

        with pytest.raises(LayerTimeoutError) as exc_info:
            await slow_func()

        # 应使用自定义值而非 TIMEOUT_HIERARCHY 中的 60s
        assert exc_info.value.timeout == 0.01

    @pytest.mark.asyncio
    async def test_default_timeout_from_hierarchy(self):
        """测试未指定 timeout 时使用层级默认值。"""
        # redis 层级默认 2.0s，这里用极短的 sleep 避免实际等待
        @with_timeout("redis")
        async def quick_func() -> str:
            return "done"

        result = await quick_func()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_call_with_timeout_function(self):
        """测试 call_with_timeout 函数（非装饰器方式）。"""

        async def coro_func(x: int) -> int:
            await asyncio.sleep(0.01)
            return x * 2

        result = await call_with_timeout("rag", coro_func(21), timeout=1.0)
        assert result == 42

    @pytest.mark.asyncio
    async def test_call_with_timeout_exceeded(self):
        """测试 call_with_timeout 超时。"""

        async def slow_coro() -> str:
            await asyncio.sleep(1.0)
            return "should not reach"

        with pytest.raises(LayerTimeoutError) as exc_info:
            await call_with_timeout("qdrant", slow_coro(), timeout=0.05)

        assert exc_info.value.layer == "qdrant"
        assert exc_info.value.timeout == 0.05

    @pytest.mark.asyncio
    async def test_call_with_timeout_default_from_hierarchy(self):
        """测试 call_with_timeout 使用层级默认超时。"""

        async def quick() -> str:
            return "ok"

        # 不指定 timeout，应使用 redis 的默认 2.0s
        result = await call_with_timeout("redis", quick())
        assert result == "ok"

    def test_timeout_error_attributes(self):
        """测试 LayerTimeoutError 属性。"""
        err = LayerTimeoutError("llm", 30.0)
        assert err.layer == "llm"
        assert err.timeout == 30.0
        assert "llm" in str(err)
        assert "30.0" in str(err)
        # 应继承自 asyncio.TimeoutError
        assert isinstance(err, asyncio.TimeoutError)

    def test_timeout_hierarchy_config(self):
        """测试超时层级配置正确性。"""
        # 外层超时应大于内层
        assert TIMEOUT_HIERARCHY["api"] > TIMEOUT_HIERARCHY["agent"]
        assert TIMEOUT_HIERARCHY["agent"] > TIMEOUT_HIERARCHY["llm"]
        assert TIMEOUT_HIERARCHY["llm"] > TIMEOUT_HIERARCHY["rag"]
        assert TIMEOUT_HIERARCHY["rag"] > TIMEOUT_HIERARCHY["qdrant"]

        # 验证具体值
        assert TIMEOUT_HIERARCHY["api"] == 60.0
        assert TIMEOUT_HIERARCHY["agent"] == 45.0
        assert TIMEOUT_HIERARCHY["llm"] == 30.0
        assert TIMEOUT_HIERARCHY["rag"] == 10.0
        assert TIMEOUT_HIERARCHY["qdrant"] == 5.0
        assert TIMEOUT_HIERARCHY["redis"] == 2.0
        assert TIMEOUT_HIERARCHY["embedding"] == 10.0
        assert TIMEOUT_HIERARCHY["reranker"] == 10.0

    @pytest.mark.asyncio
    async def test_with_timeout_preserves_function_name(self):
        """测试装饰器保留原函数名。"""
        @with_timeout("llm")
        async def my_named_function() -> str:
            return "ok"

        assert my_named_function.__name__ == "my_named_function"


# ──────────────────────────────────────────────────────────────────────────────
# Chaos 测试
# ──────────────────────────────────────────────────────────────────────────────


class TestChaos:
    """Chaos Engineering 测试。"""

    def setup_method(self):
        """每个测试前确保混沌工程处于禁用状态。"""
        disable_chaos()

    def teardown_method(self):
        """每个测试后清理：禁用混沌工程，避免污染其他测试。"""
        disable_chaos()

    @pytest.mark.asyncio
    async def test_disabled_passthrough(self):
        """测试禁用时装饰器直接透传原函数。"""
        assert not is_chaos_enabled()

        @chaos("redis")
        async def echo(x: int) -> int:
            return x

        result = await echo(42)
        assert result == 42

    @pytest.mark.asyncio
    async def test_enabled_with_no_rule_passthrough(self, monkeypatch):
        """测试启用但无匹配规则时直接透传。"""
        enable_chaos()
        assert is_chaos_enabled()

        @chaos("nonexistent_layer_xyz")
        async def echo(x: int) -> int:
            return x

        result = await echo(99)
        assert result == 99

    @pytest.mark.asyncio
    async def test_enabled_injects_delay(self, monkeypatch):
        """测试启用时注入随机延迟。"""
        enable_chaos()

        # 控制 random.uniform 返回固定值（chaos.py 中使用全局 random 模块）
        monkeypatch.setattr(random_module, "uniform", lambda a, b: 0.05)
        # 不触发失败
        monkeypatch.setattr(random_module, "random", lambda: 0.99)

        @chaos("redis")
        async def echo(x: int) -> int:
            return x

        # 应执行成功（延迟 0.05s）
        result = await echo(7)
        assert result == 7

    @pytest.mark.asyncio
    async def test_enabled_injects_failure(self, monkeypatch):
        """测试启用时注入随机失败。"""
        enable_chaos()

        # 不触发延迟
        monkeypatch.setattr(random_module, "uniform", lambda a, b: 0.0)
        # 触发失败（random.random() < failure_rate=0.05）
        monkeypatch.setattr(random_module, "random", lambda: 0.01)
        # 选择第一个异常（ConnectionError）
        monkeypatch.setattr(random_module, "choice", lambda seq: seq[0])

        @chaos("redis")
        async def echo(x: int) -> int:
            return x

        with pytest.raises(ConnectionError, match="Chaos failure"):
            await echo(1)

    @pytest.mark.asyncio
    async def test_enabled_no_failure_when_rate_zero(self, monkeypatch):
        """测试 failure_rate=0 时不注入失败。"""
        enable_chaos()

        custom_config = ChaosConfig(
            name="safe_layer",
            failure_rate=0.0,
            max_delay=0.0,
        )

        @chaos("custom_safe", config=custom_config)
        async def echo(x: int) -> int:
            return x

        # 多次调用都不应失败
        for i in range(10):
            result = await echo(i)
            assert result == i

    def test_enable_disable_chaos(self):
        """测试 enable/disable 函数。"""
        # 初始状态
        disable_chaos()
        assert is_chaos_enabled() is False

        # 启用
        enable_chaos()
        assert is_chaos_enabled() is True

        # 禁用
        disable_chaos()
        assert is_chaos_enabled() is False

    @pytest.mark.asyncio
    async def test_custom_config(self, monkeypatch):
        """测试自定义 ChaosConfig。"""
        enable_chaos()

        custom_config = ChaosConfig(
            name="custom",
            failure_rate=1.0,  # 100% 失败
            max_delay=0.0,
            exceptions=(RuntimeError,),
        )

        @chaos("custom_layer", config=custom_config)
        async def echo(x: int) -> int:
            return x

        with pytest.raises(RuntimeError, match="Chaos failure"):
            await echo(1)

    @pytest.mark.asyncio
    async def test_register_chaos_rule(self, monkeypatch):
        """测试注册新的混沌规则。"""
        enable_chaos()

        # 注册一个 100% 失败的规则
        register_chaos_rule(
            "test_custom_rule",
            ChaosConfig(
                name="test_custom_rule",
                failure_rate=1.0,
                max_delay=0.0,
                exceptions=(ValueError,),
            ),
        )

        @chaos("test_custom_rule")
        async def echo(x: int) -> int:
            return x

        with pytest.raises(ValueError, match="Chaos failure"):
            await echo(1)

    def test_chaos_config_clamps_failure_rate(self):
        """测试 ChaosConfig 限制 failure_rate 在 [0, 1] 范围。"""
        cfg_high = ChaosConfig(name="high", failure_rate=2.0)
        assert cfg_high.failure_rate == 1.0

        cfg_low = ChaosConfig(name="low", failure_rate=-0.5)
        assert cfg_low.failure_rate == 0.0

        cfg_normal = ChaosConfig(name="normal", failure_rate=0.3)
        assert cfg_normal.failure_rate == 0.3

    def test_chaos_config_clamps_max_delay(self):
        """测试 ChaosConfig 限制 max_delay 非负。"""
        cfg = ChaosConfig(name="neg", max_delay=-1.0)
        assert cfg.max_delay == 0.0

    @pytest.mark.asyncio
    async def test_preconfigured_rules_exist(self):
        """测试预配置混沌规则存在。"""
        from app.reliability.chaos import _CHAOS_RULES

        assert "redis" in _CHAOS_RULES
        assert "qdrant" in _CHAOS_RULES
        assert "llm" in _CHAOS_RULES
        assert "embedding" in _CHAOS_RULES

        # 验证失败率在合理范围
        for name, cfg in _CHAOS_RULES.items():
            assert 0.0 <= cfg.failure_rate <= 1.0
            assert cfg.max_delay >= 0.0
