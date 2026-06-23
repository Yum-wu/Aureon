# -*- coding: utf-8 -*-
"""Bulkhead 隔舱模式 — 每个外部依赖独立 Semaphore 池，防止级联故障。

为每个外部依赖（Redis/Qdrant/LLM/Embedding）维护独立的并发池与等待队列：
- 并发数超限的任务进入排队等待
- 队列满时快速失败，抛出 BulkheadFullError，避免请求无限堆积
- 通过装饰器或 execute() 方法保护异步函数
"""

import asyncio
import functools
from collections.abc import Awaitable, Callable
from typing import ParamSpec, TypeVar

import structlog

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


class BulkheadFullError(Exception):
    """舱壁已满（队列已满），拒绝新请求。"""

    pass


class Bulkhead:
    """舱壁隔离器 — 限制并发调用数，超出时排队或快速失败。

    Args:
        name: 舱壁名称（用于日志与统计）
        max_concurrent: 最大并发执行数
        max_queue: 最大排队等待数（不含正在执行的任务）
    """

    def __init__(self, name: str, max_concurrent: int = 10, max_queue: int = 20):
        self.name = name
        self._max_concurrent = max_concurrent
        self._max_queue = max_queue
        # 并发执行信号量
        self._semaphore = asyncio.Semaphore(max_concurrent)
        # 队列信号量：限制排队等待的任务数
        self._queue_sem = asyncio.Semaphore(max_queue)
        # 状态计数（用于统计，非控制流）
        self._active = 0
        self._queued = 0

    async def execute(self, func: Callable[P, Awaitable[T]], *args: P.args, **kwargs: P.kwargs) -> T:
        """执行被舱壁保护的异步函数。

        - 队列已满时立即抛出 BulkheadFullError
        - 并发数超限时排队等待
        - 被取消时正确释放已占用的资源

        Args:
            func: 要执行的异步函数
            *args: 位置参数
            **kwargs: 关键字参数

        Returns:
            函数执行结果

        Raises:
            BulkheadFullError: 队列已满
            Exception: 被保护函数抛出的任何异常
        """
        # 阶段1：尝试获取队列位置（非阻塞检查 + acquire）
        if self._queue_sem.locked():
            logger.warning(
                "bulkhead_queue_full",
                bulkhead=self.name,
                active=self._active,
                queued=self._queued,
            )
            raise BulkheadFullError(f"Bulkhead '{self.name}' queue is full")

        await self._queue_sem.acquire()
        self._queued += 1
        acquired_queue = True
        acquired_concurrent = False

        try:
            # 阶段2：等待并发槽位
            await self._semaphore.acquire()
            acquired_concurrent = True
            self._active += 1
            # 已获得并发槽位，释放队列位置
            self._queued -= 1
            self._queue_sem.release()
            acquired_queue = False

            # 阶段3：执行被保护函数
            return await func(*args, **kwargs)
        finally:
            # 清理资源：确保任意退出路径都释放对应信号量
            if acquired_concurrent:
                self._active -= 1
                self._semaphore.release()
            if acquired_queue:
                # 在获取并发槽位前退出（取消/异常），释放队列位置
                self._queued -= 1
                self._queue_sem.release()

    @property
    def stats(self) -> dict:
        """返回当前舱壁状态统计。"""
        return {
            "name": self.name,
            "max_concurrent": self._max_concurrent,
            "max_queue": self._max_queue,
            "active": self._active,
            "queued": self._queued,
        }


def bulkhead(bulkhead_instance: Bulkhead) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """装饰器：用指定 Bulkhead 实例保护异步函数。

    Args:
        bulkhead_instance: 已配置的 Bulkhead 实例

    Returns:
        装饰器函数
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            return await bulkhead_instance.execute(func, *args, **kwargs)

        # 暴露 bulkhead 实例便于检查
        wrapper._bulkhead = bulkhead_instance  # type: ignore[attr-defined]
        return wrapper

    return decorator


# 预配置舱壁实例（按外部依赖隔离）
redis_bulkhead = Bulkhead(name="redis", max_concurrent=20, max_queue=50)
qdrant_bulkhead = Bulkhead(name="qdrant", max_concurrent=10, max_queue=30)
llm_bulkhead = Bulkhead(name="llm", max_concurrent=5, max_queue=15)
embedding_bulkhead = Bulkhead(name="embedding", max_concurrent=8, max_queue=20)

# 全局注册表
_bulkheads: dict[str, Bulkhead] = {
    "redis": redis_bulkhead,
    "qdrant": qdrant_bulkhead,
    "llm": llm_bulkhead,
    "embedding": embedding_bulkhead,
}


def get_bulkhead(name: str) -> Bulkhead:
    """获取指定名称的舱壁实例。

    Args:
        name: 舱壁名称（redis/qdrant/llm/embedding）

    Returns:
        对应的 Bulkhead 实例

    Raises:
        KeyError: 名称不存在
    """
    return _bulkheads[name]


def get_all_bulkhead_stats() -> list[dict]:
    """获取所有舱壁的状态统计。"""
    return [b.stats for b in _bulkheads.values()]


def reset_all_bulkheads() -> None:
    """重置所有舱壁的计数器（仅用于测试）。

    注意：不会重置 Semaphore 内部状态，仅重置统计计数。
    测试间应避免跨用例共享状态。
    """
    for b in _bulkheads.values():
        b._active = 0
        b._queued = 0
    logger.info("all_bulkheads_reset")
