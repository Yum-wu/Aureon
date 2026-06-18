"""
LLM wrapper with retry logic, fallback support, and connection pooling.

Primary LLM uses `settings.llm_*` (DashScope Qwen).
Fallback LLM uses `settings.fallback_*` (Zhipu AI).
"""

import os
import asyncio
import threading
from collections import OrderedDict

from langchain_openai import ChatOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from openai import APIError, APITimeoutError, RateLimitError
import structlog

from app.config import settings

logger = structlog.get_logger()

# ── LLM instance pool (reuse connections across requests, LRU eviction) ──

_LLM_POOL_MAXSIZE = 10
_llm_pool: OrderedDict[str, ChatOpenAI] = OrderedDict()
_llm_pool_lock = threading.Lock()


def _pool_put(key: str, llm: ChatOpenAI) -> None:
    """Insert into pool with LRU eviction. Must be called with _llm_pool_lock held."""
    if key in _llm_pool:
        _llm_pool.move_to_end(key)
    else:
        if len(_llm_pool) >= _LLM_POOL_MAXSIZE:
            _llm_pool.popitem(last=False)  # evict least recently used
        _llm_pool[key] = llm

# Default parameters per LangChain best practices
_DEFAULT_MAX_TOKENS = 2048
_DEFAULT_TIMEOUT = 30  # seconds — Railway proxy 默认 30s，留余量
_DEFAULT_MAX_RETRIES = 2
_DEFAULT_TEMPERATURE = 0.3  # RAG: low temperature for accuracy


def create_llm(model: str = None, **kwargs):
    """Factory: create ChatOpenAI instance with connection pooling.

    Reuses instances when same model+streaming combo is requested.
    Follows LangChain best practices: max_tokens, timeout, max_retries.
    """
    model_name = model or settings.llm_model
    streaming = kwargs.get("streaming", True)
    enable_thinking = kwargs.get("extra_body", {}).get("enable_thinking", False)
    pool_key = f"{model_name}:{streaming}:thinking={enable_thinking}"

    # Return cached instance if available
    with _llm_pool_lock:
        if pool_key in _llm_pool:
            _llm_pool.move_to_end(pool_key)  # LRU promotion
            return _llm_pool[pool_key]

    if model:
        from app.config import MODEL_REGISTRY
        if model in MODEL_REGISTRY:
            cfg = MODEL_REGISTRY[model]
            api_key = cfg["api_key"] or os.environ.get(f"{cfg['provider'].upper()}_API_KEY", "")
            if not api_key:
                raise ValueError(f"No API key for {model}. Set {cfg['provider'].upper()}_API_KEY env var.")
            llm = ChatOpenAI(
                model=cfg["model"],
                api_key=api_key,
                base_url=cfg["base_url"],
                temperature=kwargs.get("temperature", _DEFAULT_TEMPERATURE),
                streaming=streaming,
                max_tokens=cfg.get("max_tokens", _DEFAULT_MAX_TOKENS),
                timeout=_DEFAULT_TIMEOUT,
                max_retries=_DEFAULT_MAX_RETRIES,
            )
            with _llm_pool_lock:
                _pool_put(pool_key, llm)
            return llm

    # Default: DashScope Qwen
    extra_body = kwargs.get("extra_body", {})
    # 关闭思考模式以加速生成（RAG 场景不需要深度推理）
    if "enable_thinking" not in extra_body:
        extra_body["enable_thinking"] = False
    llm = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        temperature=kwargs.get("temperature", _DEFAULT_TEMPERATURE),
        streaming=streaming,
        max_tokens=kwargs.get("max_tokens", _DEFAULT_MAX_TOKENS),
        timeout=_DEFAULT_TIMEOUT,
        max_retries=_DEFAULT_MAX_RETRIES,
        extra_body=extra_body,
    )
    with _llm_pool_lock:
        _pool_put(pool_key, llm)
    return llm


def create_fallback_llm(**kwargs):
    """Factory: create fallback ChatOpenAI instance (Zhipu). Returns None if not configured."""
    if not settings.fallback_api_key:
        return None
    return ChatOpenAI(
        model=settings.fallback_model,
        api_key=settings.fallback_api_key,
        base_url=settings.fallback_base_url,
        temperature=kwargs.get("temperature", 0.7),
        streaming=kwargs.get("streaming", True),
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((APIError, APITimeoutError, RateLimitError)),
    before_sleep=lambda retry_state: logger.warning(
        "LLM API call failed, retrying (%d/%d) after %.1fs ...",
        retry_state.attempt_number,
        retry_state.retry_object.stop.max_attempt_number,
        retry_state.next_action.sleep if retry_state.next_action else 0,
    ),
)
def llm_invoke_with_retry(llm, messages):
    """Invoke LLM with automatic retry on transient errors."""
    response = llm.invoke(messages)
    return response


def llm_invoke_with_fallback(messages, primary=None, fallback=None, **kwargs):
    """Invoke LLM with automatic fallback on failure.

    Tries primary (Qwen) first. On error, falls back to Zhipu.
    Creates LLMs automatically if not provided.
    """
    if primary is None:
        primary = create_llm(streaming=False, **kwargs)
    if fallback is None:
        fallback = create_fallback_llm(streaming=False)

    try:
        return llm_invoke_with_retry(primary, messages)
    except Exception as e:
        logger.warning("Primary LLM (%s) failed: %s", settings.llm_model, e)
        if fallback is not None:
            logger.info("Falling back to %s", settings.fallback_model)
            return llm_invoke_with_retry(fallback, messages)
        raise


async def create_llm_async(model: str = None, **kwargs):
    """Async wrapper for create_llm — safe to call from async routes.

    Wraps the synchronous ChatOpenAI constructor in asyncio.to_thread()
    to avoid blocking the event loop (FastAPI best practice).
    """
    return await asyncio.to_thread(create_llm, model, **kwargs)
