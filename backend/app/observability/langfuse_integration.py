"""Langfuse tracing integration for Aureon.

Uses the Langfuse v4 SDK ``CallbackHandler`` to automatically trace all
LangChain / LangGraph runs (LLM calls, tool calls, chain steps, RAG
queries, etc.) with proper span hierarchy, token usage, and metadata.

Usage::

    from app.observability.langfuse_integration import (
        get_langfuse_handler, init_langfuse, shutdown_langfuse,
    )

    # In app lifespan startup:
    await init_langfuse()

    # Pass to LangGraph agent:
    handler = get_langfuse_handler()
    async for event in graph.astream_events(
        inputs, version="v2",
        config={"callbacks": [handler]},
    ):
        ...

    # In app lifespan shutdown:
    await shutdown_langfuse()
"""

import structlog
from app.config import settings

logger = structlog.get_logger()

_handler = None
_client = None


def get_langfuse_handler():
    """Return the global Langfuse ``CallbackHandler`` singleton.

    Returns ``None`` if Langfuse is disabled or not yet initialized.
    """
    return _handler


async def init_langfuse() -> None:
    """Initialize the Langfuse client and callback handler.

    Reads credentials from ``settings.observability`` (which are sourced
    from environment variables).  Does nothing if
    ``observability.langfuse_enabled`` is ``False``.

    In langfuse v4, the client is a singleton created via ``Langfuse()``,
    and the ``CallbackHandler`` is imported from ``langfuse.langchain``.
    """
    from app.config import settings as s

    obs = s.observability
    if not obs.langfuse_enabled:
        logger.info("Langfuse tracing disabled (langfuse_enabled=False)")
        return

    if not obs.langfuse_public_key or not obs.langfuse_secret_key:
        logger.warning(
            "Langfuse enabled but LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY missing"
        )
        return

    global _handler, _client

    try:
        from langfuse import Langfuse
        from langfuse.langchain import CallbackHandler

        # v4: 先创建 Langfuse 客户端（单例），凭据通过构造函数传入
        _client = Langfuse(
            secret_key=obs.langfuse_secret_key,
            public_key=obs.langfuse_public_key,
            host=obs.langfuse_host,
            release=obs.langfuse_release or None,
        )

        # v4: CallbackHandler 不再接受凭据参数，使用客户端单例
        _handler = CallbackHandler()

        # 启动时检查 Langfuse 连接状态
        try:
            _client.auth_check()
            logger.info(
                "Langfuse tracing initialized",
                host=obs.langfuse_host,
                release=obs.langfuse_release or "dev",
            )
        except Exception as e:
            logger.warning(
                "Langfuse connection check failed (tracing will still attempt to send): %s",
                e,
            )

    except Exception as e:
        logger.warning("Failed to initialize Langfuse handler: %s", e)
        _handler = None
        _client = None


async def shutdown_langfuse() -> None:
    """Gracefully flush remaining traces and shutdown Langfuse."""
    global _handler, _client
    if _client is None:
        return
    try:
        _client.shutdown()
        logger.info("Langfuse handler shut down")
    except Exception as e:
        logger.warning("Langfuse shutdown failed: %s", e)
    _handler = None
    _client = None


def get_trace_url(trace_id: str | None = None) -> str | None:
    """Return the URL to view a trace in the Langfuse dashboard.

    Args:
        trace_id: The Langfuse trace ID.  If ``None``, returns the base URL.

    Returns:
        Full URL to the trace (or base dashboard URL).
    """
    host = settings.observability.langfuse_host
    if not host:
        return None
    if trace_id:
        return f"{host}/trace/{trace_id}"
    return host
