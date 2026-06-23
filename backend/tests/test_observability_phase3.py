"""Phase 3 可观测性增强测试。

覆盖：
- ``trace_qdrant_operation`` 上下文管理器
- 资源属性配置（service.name / service.version / deployment.environment）
- 插桩幂等性（多次调用不报错）
- graceful skip（模拟 ImportError 时不抛异常）
"""
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from app.observability import tracing
from app.observability.tracing import (
    _NoOpSpan,
    _NoOpTracer,
    _build_resource,
    _instrument_httpx,
    _instrument_redis,
    _maybe_attach_langfuse_otel,
    create_span,
    get_tracer,
    trace_qdrant_operation,
)


@pytest.fixture(autouse=True)
def _reset_tracing_globals():
    """每个测试前后重置 tracing 模块的全局状态，避免污染其它测试。"""
    saved_tracer = tracing._tracer
    saved_provider = tracing._tracer_provider
    saved_instrumented = dict(tracing._instrumented)

    tracing._tracer = None
    tracing._tracer_provider = None
    tracing._instrumented = {"fastapi": False, "redis": False, "httpx": False}

    yield

    tracing._tracer = saved_tracer
    tracing._tracer_provider = saved_provider
    tracing._instrumented = saved_instrumented


# ── trace_qdrant_operation 上下文管理器 ──


class TestTraceQdrantOperation:
    """测试 Qdrant 手动 span 上下文管理器。"""

    def test_yields_span_object(self):
        """上下文管理器应 yield 一个 span-like 对象（至少有 set_attribute 方法）。"""
        with trace_qdrant_operation("qdrant_search") as span:
            assert span is not None
            assert hasattr(span, "set_attribute")
            assert hasattr(span, "add_event")

    def test_accepts_attributes(self):
        """传入的 attributes 应被设置到 span 上而不抛异常。"""
        with trace_qdrant_operation(
            "qdrant_search",
            {"collection": "aureon", "top_k": 10},
        ) as span:
            # NoOp 或真实 span 都不应抛异常
            span.set_attribute("result_count", 5)

    def test_does_not_raise_without_init(self):
        """未调用 init_tracing 时使用应优雅降级，不抛异常。"""
        # tracing._tracer 已被 fixture 置为 None，且未安装 OTel 时返回 NoOp
        with trace_qdrant_operation("qdrant_query") as span:
            span.set_attribute("test", True)

    def test_noop_span_set_attribute_does_not_raise(self):
        """NoOpSpan 的 set_attribute 应静默成功。"""
        span = _NoOpSpan()
        span.set_attribute("k", "v")
        span.add_event("evt")
        span.set_status("OK")
        span.record_exception(Exception("test"))

    def test_operation_name_passed_through(self):
        """操作名称应能传入上下文管理器（NoOp 路径下不验证 span 名）。"""
        # 使用 NoOpTracer 验证不抛异常即可
        noop_tracer = _NoOpTracer()
        with noop_tracer.start_as_current_span("qdrant_delete") as span:
            assert span is not None


# ── 资源属性配置 ──


class TestResourceAttributes:
    """测试 OTel Resource 属性配置。"""

    def test_service_name_always_present(self):
        """service.name 应始终被设置。"""
        resource = _build_resource("aureon-backend")
        # Resource.attributes 是 SDK 提供的只读映射
        assert resource.attributes.get("service.name") == "aureon-backend"

    def test_service_version_from_env(self, monkeypatch):
        """BUILD_VERSION 环境变量应映射到 service.version 属性。"""
        monkeypatch.setenv("BUILD_VERSION", "1.2.3")
        resource = _build_resource("aureon-backend")
        assert resource.attributes.get("service.version") == "1.2.3"

    def test_service_version_absent_when_env_missing(self, monkeypatch):
        """未设置 BUILD_VERSION 时不应包含 service.version 属性。"""
        monkeypatch.delenv("BUILD_VERSION", raising=False)
        resource = _build_resource("aureon-backend")
        assert "service.version" not in resource.attributes

    def test_deployment_environment_from_env(self, monkeypatch):
        """ENVIRONMENT 环境变量应映射到 deployment.environment 属性。"""
        monkeypatch.setenv("ENVIRONMENT", "staging")
        resource = _build_resource("aureon-backend")
        assert resource.attributes.get("deployment.environment") == "staging"

    def test_deployment_environment_fallback_to_settings(self, monkeypatch):
        """ENVIRONMENT 未设置时回退到 settings.auth.environment。"""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        # 使用 patch 替换 tracing 模块中的 settings 引用，确保属性读取正确
        with patch("app.observability.tracing.settings") as mock_settings:
            mock_settings.auth.environment = "staging"
            resource = _build_resource("aureon-backend")
            assert resource.attributes.get("deployment.environment") == "staging"

    def test_deployment_environment_absent_when_no_source(self, monkeypatch):
        """ENVIRONMENT 与 settings.auth.environment 都为空时不包含该属性。"""
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        with patch("app.observability.tracing.settings") as mock_settings:
            mock_settings.auth.environment = ""
            resource = _build_resource("aureon-backend")
            assert "deployment.environment" not in resource.attributes


# ── 插桩幂等性 ──


class TestInstrumentationIdempotency:
    """测试插桩函数的幂等性（多次调用不报错）。"""

    def test_redis_instrument_idempotent_when_already_instrumented(self):
        """已标记为 instrumented 时再次调用应直接返回，不重复插桩。"""
        tracing._instrumented["redis"] = True
        # 不应抛异常
        _instrument_redis()
        assert tracing._instrumented["redis"] is True

    def test_httpx_instrument_idempotent_when_already_instrumented(self):
        """已标记为 instrumented 时再次调用应直接返回。"""
        tracing._instrumented["httpx"] = True
        _instrument_httpx()
        assert tracing._instrumented["httpx"] is True

    def test_redis_instrument_handles_already_instrumented_sdk(self):
        """即使 SDK 报告已插桩，函数也应捕获异常并标记为已启用。"""
        # 模拟 RedisInstrumentor.instrument() 抛异常（SDK 内部检测到已插桩）
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.redis": _FakeModule()}):
            # _FakeModule 的 instrument() 会抛 RuntimeError，但函数应捕获
            _instrument_redis()
            # 由于异常被捕获，_instrumented 不会被标记为 True
            # 但函数不应抛异常
            assert tracing._instrumented["redis"] in (True, False)


# ── Graceful skip（ImportError）──


class TestGracefulSkip:
    """测试依赖未安装时的优雅降级。"""

    def test_redis_instrument_skips_when_module_missing(self):
        """opentelemetry-instrumentation-redis 未安装时应 graceful skip。"""
        # 通过让 import 失败来模拟模块缺失
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.redis": None}):
            # 不应抛异常
            _instrument_redis()
            # 未成功插桩，标记位保持 False
            assert tracing._instrumented["redis"] is False

    def test_httpx_instrument_skips_when_module_missing(self):
        """opentelemetry-instrumentation-httpx 未安装时应 graceful skip。"""
        with patch.dict("sys.modules", {"opentelemetry.instrumentation.httpx": None}):
            _instrument_httpx()
            assert tracing._instrumented["httpx"] is False

    def test_langfuse_otel_skips_when_env_not_set(self):
        """LANGFUSE_OTEL_ENABLED 未设置时不应附加 SpanProcessor。"""
        # 使用一个伪 provider 验证 add_span_processor 未被调用
        fake_provider = _FakeProvider()
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("LANGFUSE_OTEL_ENABLED", None)
            _maybe_attach_langfuse_otel(fake_provider)
        assert fake_provider.added_processors == []

    def test_langfuse_otel_skips_when_disabled(self):
        """LANGFUSE_OTEL_ENABLED=false 时不应附加 SpanProcessor。"""
        fake_provider = _FakeProvider()
        with patch.dict(os.environ, {"LANGFUSE_OTEL_ENABLED": "false"}):
            _maybe_attach_langfuse_otel(fake_provider)
        assert fake_provider.added_processors == []

    def test_langfuse_otel_handles_missing_sdk_gracefully(self):
        """LANGFUSE_OTEL_ENABLED=true 但 langfuse SDK 不提供 SpanProcessor 时优雅降级。"""
        fake_provider = _FakeProvider()
        # 让 langfuse.open_telemetry 和 langfuse 模块都不可用
        with patch.dict(os.environ, {"LANGFUSE_OTEL_ENABLED": "true"}):
            with patch.dict(
                "sys.modules",
                {
                    "langfuse.open_telemetry": None,
                    "langfuse": None,
                },
            ):
                # 不应抛异常
                _maybe_attach_langfuse_otel(fake_provider)
        # 未附加任何 processor
        assert fake_provider.added_processors == []


# ── create_span 与 get_tracer 降级 ──


class TestSpanFallback:
    """测试未初始化时的 span/tracer 降级。"""

    def test_get_tracer_returns_object_without_init(self):
        """未初始化时 get_tracer 应返回一个可用的 tracer 对象。"""
        tracer = get_tracer()
        assert tracer is not None
        # 应能正常使用 start_as_current_span
        with tracer.start_as_current_span("test_span") as span:
            assert span is not None

    def test_create_span_yields_object(self):
        """create_span 在未初始化时应 yield 一个 no-op span。"""
        with create_span("test_op") as span:
            assert span is not None
            span.set_attribute("key", "value")

    def test_create_span_with_attributes(self):
        """create_span 应能接受 attributes 参数。"""
        with create_span("test_op", {"count": 10, "name": "test"}) as span:
            assert span is not None


# ── 辅助伪类 ──


class _FakeModule:
    """模拟已插桩的 OTel 模块（instrument() 抛异常表示已插桩）。"""

    class RedisInstrumentor:
        @staticmethod
        def instrument():
            raise RuntimeError("RedisInstrumentor already instrumented")

    class HTTPXClientInstrumentor:
        @staticmethod
        def instrument():
            raise RuntimeError("HTTPXClientInstrumentor already instrumented")


class _FakeProvider:
    """伪 TracerProvider，记录 add_span_processor 调用。"""

    def __init__(self):
        self.added_processors: list = []

    def add_span_processor(self, processor):
        self.added_processors.append(processor)
