"""OpenTelemetry tracing integration for Aureon.

Provides distributed tracing via OpenTelemetry with FastAPI auto-instrumentation.
Falls back to ``ConsoleSpanExporter`` when no OTLP endpoint is configured
(development environment).

Usage::

    from app.observability.tracing import init_tracing, get_tracer, create_span

    # In startup:
    init_tracing(app)

    # In request handlers / pipeline code:
    tracer = get_tracer()
    with create_span("retrieval") as span:
        span.set_attribute("chunk_count", len(chunks))
        ...
"""

import os
from contextlib import contextmanager

import structlog

logger = structlog.get_logger()

_tracer = None
_tracer_provider = None


def init_tracing(app, service_name: str = "aureon-api") -> None:
    """Initialize OpenTelemetry TracerProvider and instrument FastAPI.

    If ``OTEL_EXPORTER_OTLP_ENDPOINT`` is set, exports to that endpoint
    via OTLP/gRPC.  Otherwise, uses ``ConsoleSpanExporter`` for dev.

    Args:
        app: The FastAPI application instance.
        service_name: Service name for traces (default: ``aureon-api``).
    """
    global _tracer_provider, _tracer

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except ImportError as e:
        logger.warning("opentelemetry-sdk not installed, tracing disabled: %s", e)
        return

    resource = Resource.create({SERVICE_NAME: service_name})

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
    trace.set_tracer_provider(provider)
    _tracer_provider = provider
    _tracer = trace.get_tracer(service_name)

    # Instrument FastAPI
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        FastAPIInstrumentor.instrument_app(app)
        logger.info("FastAPI instrumentation enabled for OpenTelemetry")
    except Exception as e:
        logger.warning("FastAPI OTel instrumentation failed (non-fatal): %s", e)

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
        return trace.get_tracer("aureon-api")
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
                    except Exception:
                        pass
            yield span
    except Exception:
        # If anything goes wrong, yield a no-op span
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
