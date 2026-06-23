# -*- coding: utf-8 -*-
"""超时级联 — 分层超时配置，防止请求堆积。

层级关系（从外到内逐层递减）：
    API(60s) > Agent(45s) > LLM(30s) > RAG(10s) > Qdrant(5s)
    Embedding(10s) / Reranker(10s) / Redis(2s)

外层超时必须大于内层超时之和，确保内层有机会正常返回或快速失败，
避免外层等待时内层请求持续堆积。
"""

import asyncio
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import structlog

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# 超时层级配置（秒）— 从外到内逐层递减
TIMEOUT_HIERARCHY: dict[str, float] = {
    "api": 60.0,        # API 请求总超时
    "agent": 45.0,      # Agent 执行超时
    "llm": 30.0,        # LLM 调用超时
    "rag": 10.0,        # RAG 检索超时
    "qdrant": 5.0,      # Qdrant 查询超时
    "embedding": 10.0,  # Embedding API 超时
    "reranker": 10.0,   # Reranker API 超时
    "redis": 2.0,       # Redis 操作超时
}


class TimeoutError(asyncio.TimeoutError):
    """自定义超时异常，携带层级信息。

    注意：此类名与内置 TimeoutError 冲突，在 __init__.py 中以
    LayerTimeoutError 别名导出，避免污染命名空间。

    Attributes:
        layer: 触发超时的层级名称
        timeout: 触发的超时秒数
    """

    def __init__(self, layer: str, timeout: float):
        self.layer = layer
        self.timeout = timeout
        super().__init__(f"Timeout after {timeout}s in layer '{layer}'")


def with_timeout(layer: str, timeout: float | None = None) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """装饰器：为异步函数添加超时控制。

    Args:
        layer: 超时层级名称（如 'llm', 'rag'）
        timeout: 自定义超时秒数，None 则使用 TIMEOUT_HIERARCHY 中的默认值

    Returns:
        装饰器函数

    Raises:
        TimeoutError: 当函数执行超过指定时间时
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            t = timeout if timeout is not None else TIMEOUT_HIERARCHY.get(layer, 30.0)
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=t)
            except asyncio.TimeoutError:
                logger.warning(
                    "timeout_exceeded",
                    layer=layer,
                    timeout=t,
                    func=func.__name__,
                )
                raise TimeoutError(layer, t) from None

        return wrapper

    return decorator


async def call_with_timeout(layer: str, coro: Awaitable[T], timeout: float | None = None) -> T:
    """为协程添加超时控制（非装饰器方式）。

    适用于无法使用装饰器的场景，如直接调用第三方库协程。

    Args:
        layer: 超时层级名称
        coro: 要执行的协程（已 awaitable）
        timeout: 自定义超时秒数，None 则使用 TIMEOUT_HIERARCHY 中的默认值

    Returns:
        协程执行结果

    Raises:
        TimeoutError: 当协程执行超过指定时间时
    """
    t = timeout if timeout is not None else TIMEOUT_HIERARCHY.get(layer, 30.0)
    try:
        return await asyncio.wait_for(coro, timeout=t)
    except asyncio.TimeoutError:
        logger.warning("timeout_exceeded", layer=layer, timeout=t)
        raise TimeoutError(layer, t) from None
