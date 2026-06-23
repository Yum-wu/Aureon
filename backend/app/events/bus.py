"""事件总线 — 进程内发布/订阅模式，解耦模块间通信。"""

import asyncio
from collections import defaultdict
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# 事件处理器类型：同步或异步函数
EventHandler = Any  # Callable[..., Any]，使用 Any 兼容同步/异步函数签名


class EventBus:
    """进程内事件总线，支持同步和异步处理器。"""

    def __init__(self) -> None:
        # 事件名 -> 处理器列表
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def on(self, event: str, handler: EventHandler) -> None:
        """注册事件处理器。

        Args:
            event: 事件名称（如 'chat.completed', 'document.indexed'）
            handler: 处理函数，可以是同步或异步
        """
        self._handlers[event].append(handler)
        logger.debug("event_handler_registered", event_name=event, handler=handler.__name__)

    def off(self, event: str, handler: EventHandler) -> None:
        """移除事件处理器。"""
        if event in self._handlers:
            try:
                self._handlers[event].remove(handler)
                logger.debug("event_handler_removed", event_name=event, handler=handler.__name__)
            except ValueError:
                # 处理器不存在，忽略
                pass

    async def emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """触发事件，异步执行所有处理器。

        处理器异常不会中断其他处理器的执行，但会被记录。
        """
        handlers = self._handlers.get(event, [])
        if not handlers:
            return

        logger.debug("event_emitted", event_name=event, handler_count=len(handlers))

        # 并发执行所有处理器，异常隔离
        async def _safe_execute(h: EventHandler) -> None:
            try:
                if asyncio.iscoroutinefunction(h):
                    await h(*args, **kwargs)
                else:
                    h(*args, **kwargs)
            except Exception:
                logger.exception("event_handler_error", event_name=event, handler=h.__name__)

        # 此处使用 gather + return_exceptions=True 是合理的：
        # 需要容错（单个处理器异常不应影响其他处理器），_safe_execute 已捕获并记录异常
        await asyncio.gather(*[_safe_execute(h) for h in handlers], return_exceptions=True)

    def clear(self, event: str | None = None) -> None:
        """清除事件处理器。不传 event 则清除所有。"""
        if event is None:
            self._handlers.clear()
        else:
            self._handlers.pop(event, None)


# 全局事件总线单例
event_bus = EventBus()


class Events:
    """预定义事件名称常量。"""

    CHAT_COMPLETED = "chat.completed"
    CHAT_ERROR = "chat.error"
    DOCUMENT_INDEXED = "document.indexed"
    DOCUMENT_DELETED = "document.deleted"
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    RAG_QUERY = "rag.query"
    CACHE_HIT = "cache.hit"
    CACHE_MISS = "cache.miss"
