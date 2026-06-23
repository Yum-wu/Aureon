"""OpenTelemetry tracing integration for Aureon.

Provides distributed tracing via OpenTelemetry with FastAPI auto-instrumentation.
Falls back to ``ConsoleSpanExporter`` when no OTLP endpoint is configured
(development environment).

增强内容（Phase 3 / OB3）：
- Redis 自动插桩（``opentelemetry-instrumentation-redis``）
- httpx 自动插桩（用于追踪 LLM API 调用）
- Qdrant 手动 span 上下文管理器（无官方 OTel 插桩）
- LangFuse 可选 OTel SpanProcessor 集成（``LANGFUSE_OTEL_ENABLED=true``）
- 资源属性：service.name / service.version / deployment.environment

Usage::

    from app.observability.tracing import init_tracing, get_tracer, create_span

    # In startup:
    init_tracing(app)

    # In request handlers / pipeline code:
    tracer = get_tracer()
    with create_span("retrieval") as span:
        span.set_attribute("chunk_count", len(chunks))
        ...

    # Qdrant 手动插桩：
    from app.observability.tracing import trace_qdrant_operation
    with trace_qdrant_operation("qdrant_search") as span:
        span.set_attribute("collection", "aureon")
        results = client.search(...)
"""

import os
from contextlib import contextmanager
from typing import Any

import structlog

from app.config import settings

logger = structlog.get_logger()

_tracer = None
_tracer_provider = None

# 标记各插桩是否已启用，避免重复 instrument 导致告警
_instrumented: dict[str, bool] = {
    "fastapi": False,
    "redis": False,
    "httpx": False,
}


def setup_langsmith():
    """初始化 LangSmith tracing。"""
    if not settings.observability.langsmith_enabled:
        return
    os.environ["LANGCHAIN_API_KEY"] = settings.observability.langsmith_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.observability.langsmith_project
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    logger.info("LangSmith tracing enabled, project=%s", settings.observability.langsmith_project)


def _build_resource(service_name: str) -> "Any":
    """构建 OTel Resource，附加 service.version / deployment.environment 等属性。

    Args:
        service_name: 服务名称。

    Returns:
        ``opentelemetry.sdk.resources.Resource`` 实例；若 OTel 未安装返回 ``None``。
    """
    from opentelemetry.sdk.resources import Resource

    attributes: dict[str, str] = {
        "service.name": service_name,
    }

    # 服务版本（来自 BUILD_VERSION 环境变量）
    build_version = os.environ.get("BUILD_VERSION", "").strip()
    if build_version:
        attributes["service.version"] = build_version

    # 部署环境（来自 ENVIRONMENT 环境变量，回退到 settings.auth.environment）
    env_value = os.environ.get("ENVIRONMENT", "").strip()
    if not env_value:
        try:
            env_value = (settings.auth.environment or "").strip()
        except Exception:
            env_value = ""
    if env_value:
        attributes["deployment.environment"] = env_value

    return Resource.create(attributes)


def _instrument_redis() -> None:
    """启用 Redis 自动插桩（幂等，未安装则 graceful skip）。"""
    if _instrumented["redis"]:
        return
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
        _instrumented["redis"] = True
        logger.info("Redis OTel instrumentation enabled")
    except ImportError:
        logger.debug(
            "opentelemetry-instrumentation-redis not installed, skipping Redis instrumentation"
        )
    except Exception as e:
        # 已插桩或其它非致命错误：记录但不抛出
        logger.warning("Redis OTel instrumentation failed (non-fatal): %s", e)


def _instrument_httpx() -> None:
    """启用 httpx 自动插桩（用于追踪 LLM API 调用，幂等，未安装则 graceful skip）。"""
    if _instrumented["httpx"]:
        return
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
        _instrumented["httpx"] = True
        logger.info("httpx OTel instrumentation enabled")
    except ImportError:
        logger.debug(
            "opentelemetry-instrumentation-httpx not installed, skipping httpx instrumentation"
        )
    except Exception as e:
        logger.warning("httpx OTel instrumentation failed (non-fatal): %s", e)


def _maybe_attach_langfuse_otel(provider: "Any") -> None:
    """可选：将 LangFuse 作为 OTel SpanProcessor 附加到 TracerProvider。

    通过环境变量 ``LANGFUSE_OTEL_ENABLED=true`` 启用。
    LangFuse SDK 提供 ``LangfuseSpanProcessor``，可将 OTel span 直接导出到 LangFuse。

    Args:
        provider: ``TracerProvider`` 实例。
    """
    if os.environ.get("LANGFUSE_OTEL_ENABLED", "").lower() != "true":
        return

    try:
        # langfuse v4 提供 OTel SpanProcessor（位于 langfuse.open_telemetry）
        from langfuse.open_telemetry import LangfuseSpanProcessor

        provider.add_span_processor(LangfuseSpanProcessor())
        logger.info("LangFuse OTel SpanProcessor attached")
    except ImportError:
        # 老版本或未安装 langfuse SDK 时尝试备用导入路径
        try:
            from langfuse import LangfuseSpanProcessor  # type: ignore

            provider.add_span_processor(LangfuseSpanProcessor())
            logger.info("LangFuse OTel SpanProcessor attached (legacy import)")
        except ImportError:
            logger.warning(
                "LANGFUSE_OTEL_ENABLED=true but LangfuseSpanProcessor not available "
                "in installed langfuse SDK; skipping OTel integration"
            )
        except Exception as e:
            logger.warning("LangFuse OTel SpanProcessor attach failed (non-fatal): %s", e)
    except Exception as e:
        logger.warning("LangFuse OTel SpanProcessor attach failed (non-fatal): %s", e)


def init_tracing(app, service_name: str = "aureon-backend") -> None:
    """Initialize OpenTelemetry TracerProvider and instrument FastAPI.

    If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, exports to that endpoint
    via OTLP/gRPC.  Otherwise, uses ``ConsoleSpanExporter`` for dev.

    Args:
        app: The FastAPI application instance.
        service_name: Service name for traces (default: ``aureon-backend``).
    """
    global _tracer_provider, _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError as e:
        logger.warning("opentelemetry-sdk not installed, tracing disabled: %s", e)
        return

    # 构建带资源属性的 Resource
    try:
        resource = _build_resource(service_name)
    except Exception as e:
        logger.warning("Failed to build OTel resource, using minimal: %s", e)
        from opentelemetry.sdk.resources import Resource

        resource = Resource.create({"service.name": service_name})

    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            logger.info("OpenTelemetry: exporting to OTLP endpoint %s", otlp_endpoint)
        except Exception as e:
            logger.warning("OTLP exporter init failed, falling back to console: %s", e)
            exporter = ConsoleSpanExporter()
    else:
        logger.info("No OTEL_EXPORTER_OTLP_ENDPOINT set - using ConsoleSpanExporter (dev mode)")
        exporter = ConsoleSpanExporter()

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    # 可选：附加 LangFuse OTel SpanProcessor
    _maybe_attach_langfuse_otel(provider)

    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    _tracer = trace.get_tracer(service_name)

    # Instrument FastAPI（幂等）
    if not _instrumented["fastapi"]:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
            _instrumented["fastapi"] = True
            logger.info("FastAPI instrumentation enabled for OpenTelemetry")
        except Exception as e:
            logger.warning("FastAPI OTel instrumentation failed (non-fatal): %s", e)

    # 额外插桩：Redis + httpx
    _instrument_redis()
    _instrument_httpx()

    logger.info("OpenTelemetry tracing initialized (service=%s)", service_name)


def get_tracer():
    """Return the current OpenTelemetry tracer.

    Returns a ``NoOpTracer`` if tracing was not initialized, so callers
    can always use ``get_tracer()`` without checking for ``None``.
    """
    global _tracer
    if _tracer is not None:
        return _tracer

    # Return a no-op tracer so callers never get AttributeError
    try:
        from opentelemetry import trace

        return trace.get_tracer("aureon-backend")
    except ImportError:
        # Fallback: return a minimal dummy object
        return _NoOpTracer()


@contextmanager
def create_span(name: str, attributes: dict | None = None):
    """Context manager that creates an OpenTelemetry span.

    If tracing is not initialized or opentelemetry is not installed,
    yields a no-op span so callers don't need conditional logic.

    Args:
        name: Span name (e.g. ``"retrieval"``, ``"rerank"``).
        attributes: Optional key-value pairs to set on the span.

    Yields:
        A span-like object (real ``Span`` or no-op).

    Example::

        with create_span("retrieval", {"chunk_count": len(chunks)}) as span:
            chunks = await retrieve(...)
            span.add_event("retrieval_done", {"count": len(chunks)})
    """
    tracer = get_tracer()
    try:
        with tracer.start_as_current_span(name) as span:
            if attributes:
                for k, v in attributes.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception as e:
                        logger.debug("span_set_attribute_failed", error=str(e))
            yield span
    except Exception:
        # If anything goes wrong, yield a no-op span
        yield _NoOpSpan()


@contextmanager
def trace_qdrant_operation(operation_name: str, attributes: dict | None = None):
    """为 Qdrant 操作创建手动 OTel span（Qdrant 无官方 OTel 插桩）。

    Args:
        operation_name: 操作名称，建议带 ``qdrant_`` 前缀，例如 ``qdrant_search``。
        attributes: 可选的 span 属性（collection / query_size / top_k 等）。

    Yields:
        当前 span（真实 ``Span`` 或 no-op）。

    Example::

        with trace_qdrant_operation("qdrant_search", {"collection": "aureon"}) as span:
            results = client.search(...)
            span.set_attribute("result_count", len(results))
    """
    tracer = get_tracer()
    try:
        with tracer.start_as_current_span(operation_name) as span:
            # 标记组件类型，便于在 OTel 后端按 db.system 过滤
            try:
                span.set_attribute("db.system", "qdrant")
            except Exception as e:
                logger.debug("span_set_attribute_failed", error=str(e))
            if attributes:
                for k, v in attributes.items():
                    try:
                        span.set_attribute(k, v)
                    except Exception as e:
                        logger.debug("span_set_attribute_failed", error=str(e))
            yield span
    except Exception:
        yield _NoOpSpan()


class _NoOpSpan:
    """Minimal span stand-in when OpenTelemetry is unavailable."""

    def set_attribute(self, key, value): pass
    def add_event(self, name, attributes=None): pass
    def set_status(self, status): pass
    def record_exception(self, exception): pass
    def __enter__(self): return self
    def __exit__(self, *args): pass


class _NoOpTracer:
    """Minimal tracer stand-in when OpenTelemetry is unavailable."""

    @contextmanager
    def start_as_current_span(self, name, **kwargs):
        yield _NoOpSpan()
