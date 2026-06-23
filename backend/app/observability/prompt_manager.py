"""LangFuse Prompt Management — preload prompts at startup, zero runtime dependency.

Architecture:
  startup: init_prompt_manager() -> fetch all prompts from LangFuse -> store in memory dict
  runtime: get_prompt("name", fallback="...") -> read from memory -> zero latency
  fallback: LangFuse unavailable -> use code-hardcoded defaults
"""

import structlog

logger = structlog.get_logger(__name__)

# 内存提示词缓存
_prompts: dict[str, str] = {}
_initialized: bool = False

# 注册表：所有需要从 LangFuse 同步的提示词
# Key: LangFuse 提示词名称, Value: (默认值, 描述)
PROMPT_REGISTRY: dict[str, tuple[str, str]] = {}


def register_prompt(name: str, default: str, description: str = "") -> None:
    """注册一个提示词用于 LangFuse 同步。在模块导入时同步调用。"""
    PROMPT_REGISTRY[name] = (default, description)


async def init_prompt_manager() -> None:
    """从 LangFuse 预加载所有已注册提示词。在 lifespan startup 阶段调用。"""
    global _initialized
    from app.config import settings

    if not settings.observability.langfuse_enabled:
        logger.info(
            "LangFuse disabled, using default prompts (%d registered)",
            len(PROMPT_REGISTRY),
        )
        _load_defaults()
        _initialized = True
        return

    if (
        not settings.observability.langfuse_public_key
        or not settings.observability.langfuse_secret_key
    ):
        logger.warning("LangFuse keys not configured, using default prompts")
        _load_defaults()
        _initialized = True
        return

    try:
        # Reuse the singleton Langfuse client from langfuse_integration
        # (init_langfuse() runs before init_prompt_manager() in lifespan)
        from app.observability.langfuse_integration import _client as langfuse_client

        if langfuse_client is None:
            logger.warning("Langfuse client not available, using default prompts")
            _load_defaults()
            _initialized = True
            return

        loaded = 0
        for name, (default, _) in PROMPT_REGISTRY.items():
            try:
                prompt = langfuse_client.get_prompt(name)
                if prompt:
                    _prompts[name] = prompt.compile()
                    loaded += 1
                    logger.debug("Loaded prompt from LangFuse: %s", name)
            except Exception:
                _prompts[name] = default
                logger.debug(
                    "Prompt not found in LangFuse, using default: %s", name
                )

        # 填充未从 LangFuse 加载的已注册提示词
        for name, (default, _) in PROMPT_REGISTRY.items():
            if name not in _prompts:
                _prompts[name] = default

        logger.info(
            "Prompt manager initialized: %d/%d from LangFuse",
            loaded,
            len(PROMPT_REGISTRY),
        )
    except Exception as e:
        logger.warning(
            "LangFuse prompt fetch failed: %s, using defaults", e
        )
        _load_defaults()

    _initialized = True


def _load_defaults() -> None:
    """将所有已注册的默认值加载到缓存中。"""
    for name, (default, _) in PROMPT_REGISTRY.items():
        _prompts[name] = default


def get_prompt(name: str, fallback: str = "") -> str:
    """按名称从内存缓存获取提示词。

    未找到时返回 fallback。零延迟，无外部调用。
    """
    if name in _prompts:
        return _prompts[name]
    if name in PROMPT_REGISTRY:
        return PROMPT_REGISTRY[name][0]
    return fallback


def get_all_prompts() -> dict[str, str]:
    """返回所有缓存中的提示词（用于调试/管理）。"""
    return dict(_prompts)


async def refresh_prompts() -> int:
    """手动从 LangFuse 刷新提示词。返回加载的提示词数量。"""
    global _initialized
    _initialized = False
    await init_prompt_manager()
    return len([v for v in _prompts.values() if v])
