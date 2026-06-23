"""事件总线 EventBus 单元测试。"""

import pytest

from app.events import EventBus, Events, event_bus
from app.events.bus import event_bus as global_bus


@pytest.fixture
def bus() -> EventBus:
    """每个测试使用独立的事件总线，避免全局单例污染。"""
    return EventBus()


async def test_sync_handler(bus: EventBus) -> None:
    """同步处理器执行。"""
    received: list[str] = []

    def handler(msg: str) -> None:
        received.append(msg)

    bus.on(Events.CHAT_COMPLETED, handler)
    await bus.emit(Events.CHAT_COMPLETED, "hello")

    assert received == ["hello"]


async def test_async_handler(bus: EventBus) -> None:
    """异步处理器执行。"""
    received: list[str] = []

    async def handler(msg: str) -> None:
        received.append(msg)

    bus.on(Events.DOCUMENT_INDEXED, handler)
    await bus.emit(Events.DOCUMENT_INDEXED, "doc-1")

    assert received == ["doc-1"]


async def test_multiple_handlers(bus: EventBus) -> None:
    """多个处理器并发执行。"""
    results: list[int] = []

    def handler_a() -> None:
        results.append(1)

    async def handler_b() -> None:
        results.append(2)

    def handler_c() -> None:
        results.append(3)

    bus.on(Events.RAG_QUERY, handler_a)
    bus.on(Events.RAG_QUERY, handler_b)
    bus.on(Events.RAG_QUERY, handler_c)
    await bus.emit(Events.RAG_QUERY)

    # 三个处理器都被执行
    assert sorted(results) == [1, 2, 3]
    assert len(results) == 3


async def test_handler_error_isolation(bus: EventBus) -> None:
    """处理器异常不影响其他处理器。"""
    executed: list[str] = []

    def good_handler_before() -> None:
        executed.append("before")

    def bad_handler() -> None:
        raise RuntimeError("故意失败")

    def good_handler_after() -> None:
        executed.append("after")

    bus.on(Events.CHAT_ERROR, good_handler_before)
    bus.on(Events.CHAT_ERROR, bad_handler)
    bus.on(Events.CHAT_ERROR, good_handler_after)

    # 不应抛出异常
    await bus.emit(Events.CHAT_ERROR)

    # 前后两个正常处理器都执行了
    assert "before" in executed
    assert "after" in executed


async def test_off_removes_handler(bus: EventBus) -> None:
    """off 方法移除处理器。"""
    received: list[str] = []

    def handler(msg: str) -> None:
        received.append(msg)

    bus.on(Events.CACHE_HIT, handler)
    await bus.emit(Events.CACHE_HIT, "first")
    assert received == ["first"]

    bus.off(Events.CACHE_HIT, handler)
    await bus.emit(Events.CACHE_HIT, "second")
    # 移除后不再触发
    assert received == ["first"]


async def test_off_nonexistent_handler_is_safe(bus: EventBus) -> None:
    """移除不存在的处理器不报错。"""
    def handler() -> None:
        pass

    def other() -> None:
        pass

    bus.on(Events.CACHE_MISS, handler)
    # 移除未注册的处理器不应抛异常
    bus.off(Events.CACHE_MISS, other)
    bus.off("nonexistent.event", handler)


async def test_clear_all(bus: EventBus) -> None:
    """clear 清除所有处理器。"""
    received: list[str] = []

    def handler_a() -> None:
        received.append("a")

    def handler_b() -> None:
        received.append("b")

    bus.on(Events.USER_LOGIN, handler_a)
    bus.on(Events.USER_LOGOUT, handler_b)

    bus.clear()

    await bus.emit(Events.USER_LOGIN)
    await bus.emit(Events.USER_LOGOUT)

    assert received == []


async def test_clear_event(bus: EventBus) -> None:
    """clear 清除特定事件，不影响其他事件。"""
    login_received: list[str] = []
    logout_received: list[str] = []

    def login_handler() -> None:
        login_received.append("login")

    def logout_handler() -> None:
        logout_received.append("logout")

    bus.on(Events.USER_LOGIN, login_handler)
    bus.on(Events.USER_LOGOUT, logout_handler)

    # 只清除 login 事件
    bus.clear(Events.USER_LOGIN)

    await bus.emit(Events.USER_LOGIN)
    await bus.emit(Events.USER_LOGOUT)

    # login 被清除，logout 仍执行
    assert login_received == []
    assert logout_received == ["logout"]


async def test_emit_no_handlers(bus: EventBus) -> None:
    """无处理器时不报错。"""
    # 触发一个没有任何处理器的事件，不应抛异常
    await bus.emit("no.such.event", "arg1", kwarg="value")


async def test_global_event_bus_singleton() -> None:
    """全局事件总线单例可用且与模块导出一致。"""
    assert event_bus is global_bus
    assert isinstance(event_bus, EventBus)


async def test_events_constants() -> None:
    """预定义事件名称常量为字符串。"""
    assert Events.CHAT_COMPLETED == "chat.completed"
    assert Events.DOCUMENT_INDEXED == "document.indexed"
    assert Events.RAG_QUERY == "rag.query"
