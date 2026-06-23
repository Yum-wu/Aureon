# -*- coding: utf-8 -*-
"""Chaos Engineering — 测试环境注入随机延迟和失败，验证系统弹性。

仅在测试环境启用（通过环境变量 CHAOS_ENGINEERING_ENABLED=true 或运行时
调用 enable_chaos()）。生产环境默认禁用，装饰器直接透传原函数。

支持两类故障注入：
- 随机延迟：模拟网络抖动或服务慢响应
- 随机失败：按概率抛出指定异常（如 ConnectionError/TimeoutError）
"""

import asyncio
import os
import random
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

import structlog

logger = structlog.get_logger(__name__)

P = ParamSpec("P")
T = TypeVar("T")


# 是否启用混沌工程（仅测试环境）
# 模块加载时读取环境变量，运行时可通过 enable/disable_chaos() 切换
_CHAOS_ENABLED: bool = os.environ.get("CHAOS_ENGINEERING_ENABLED", "false").lower() == "true"


class ChaosConfig:
    """混沌工程配置。

    Args:
        name: 配置名称（用于日志）
        failure_rate: 失败概率，0.0 ~ 1.0
        max_delay: 最大随机延迟（秒），0 表示不注入延迟
        exceptions: 失败时随机选择的异常类型
    """

    def __init__(
        self,
        name: str,
        failure_rate: float = 0.0,
        max_delay: float = 0.0,
        exceptions: tuple[type[BaseException], ...] = (Exception,),
    ):
        self.name = name
        self.failure_rate = max(0.0, min(1.0, failure_rate))
        self.max_delay = max(0.0, max_delay)
        self.exceptions = exceptions


# 预配置混沌规则
# 注意：使用 asyncio.TimeoutError（Python 3.12 中为 builtins.TimeoutError 别名）
_CHAOS_RULES: dict[str, ChaosConfig] = {
    "redis": ChaosConfig(
        "redis",
        failure_rate=0.05,
        max_delay=0.1,
        exceptions=(ConnectionError, asyncio.TimeoutError),
    ),
    "qdrant": ChaosConfig(
        "qdrant",
        failure_rate=0.03,
        max_delay=0.2,
        exceptions=(ConnectionError, asyncio.TimeoutError),
    ),
    "llm": ChaosConfig(
        "llm",
        failure_rate=0.02,
        max_delay=0.5,
        exceptions=(ConnectionError, asyncio.TimeoutError),
    ),
    "embedding": ChaosConfig(
        "embedding",
        failure_rate=0.03,
        max_delay=0.3,
        exceptions=(ConnectionError, asyncio.TimeoutError),
    ),
}


def chaos(layer: str, config: ChaosConfig | None = None) -> Callable[[Callable[P, Awaitable[T]]], Callable[P, Awaitable[T]]]:
    """装饰器：为异步函数注入混沌故障（仅测试环境生效）。

    生产环境（_CHAOS_ENABLED=False）直接透传原函数，零开销。

    Args:
        layer: 混沌层级名称（如 'redis', 'llm'）
        config: 自定义混沌配置，None 则使用 _CHAOS_RULES 中的预配置

    Returns:
        装饰器函数
    """

    def decorator(func: Callable[P, Awaitable[T]]) -> Callable[P, Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            # 生产环境直接透传
            if not _CHAOS_ENABLED:
                return await func(*args, **kwargs)

            cfg = config or _CHAOS_RULES.get(layer)
            if cfg is None:
                return await func(*args, **kwargs)

            # 注入随机延迟
            if cfg.max_delay > 0:
                delay = random.uniform(0, cfg.max_delay)
                logger.debug(
                    "chaos_delay_injected",
                    layer=layer,
                    delay=delay,
                    func=func.__name__,
                )
                await asyncio.sleep(delay)

            # 注入随机失败
            if cfg.failure_rate > 0 and random.random() < cfg.failure_rate:
                exc_class = random.choice(cfg.exceptions)
                logger.debug(
                    "chaos_failure_injected",
                    layer=layer,
                    exception=exc_class.__name__,
                    func=func.__name__,
                )
                raise exc_class(f"Chaos failure in layer '{layer}'")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def enable_chaos() -> None:
    """启用混沌工程（运行时）。

    主要用于测试中动态启用，无需重启进程。
    """
    global _CHAOS_ENABLED
    _CHAOS_ENABLED = True
    logger.warning("chaos_engineering_enabled")


def disable_chaos() -> None:
    """禁用混沌工程（运行时）。

    测试结束时应调用以避免污染其他测试。
    """
    global _CHAOS_ENABLED
    _CHAOS_ENABLED = False
    logger.info("chaos_engineering_disabled")


def is_chaos_enabled() -> bool:
    """返回混沌工程当前是否启用。"""
    return _CHAOS_ENABLED


def register_chaos_rule(name: str, config: ChaosConfig) -> None:
    """注册或更新混沌规则。

    Args:
        name: 规则名称
        config: 混沌配置
    """
    _CHAOS_RULES[name] = config
    logger.info("chaos_rule_registered", name=name, failure_rate=config.failure_rate)
