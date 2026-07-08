# -*- coding: utf-8 -*-
"""Embedding functions for RAG system.

Multi-provider API embedding with Redis caching and fallback chain.
Extracted from vector_store.py.
"""

import os
import hashlib
import threading
import time
from collections import OrderedDict

import httpx
import numpy as np
from typing import List, Optional

import structlog

logger = structlog.get_logger()


VECTOR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "vectors")
_SILICONFLOW_SAFE_CHARS = 900
_SILICONFLOW_SAFE_ESTIMATED_TOKENS = 512


# ── Embedding cache (LRU eviction, keyed by text hash) ──
_embed_cache: OrderedDict[str, np.ndarray] = OrderedDict()
_EMBED_CACHE_MAX = 5000
_embed_cache_lock = threading.Lock()  # Thread-safe access to _embed_cache

# ── Shared sync httpx.Client (connection pool reuse) ──
_http_client: httpx.Client | None = None
_http_client_lock = threading.Lock()


def _get_http_client() -> httpx.Client:
    """Lazy-init thread-safe httpx.Client singleton with connection pooling.

    Replaces per-call `requests.post` (which opens a new TCP connection each
    time) with a shared client that keeps connections alive in a pool.
    """
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            if _http_client is None:
                _http_client = httpx.Client(
                    timeout=httpx.Timeout(connect=10.0, read=90.0, write=30.0, pool=10.0),
                    limits=httpx.Limits(max_connections=20, max_keepalive_connections=5, keepalive_expiry=30.0),
                )
    return _http_client


def _get_embedding_dim() -> int:
    """Return the active embedding dimension from settings or env var.

    Priority: EMBEDDING_DIMENSION env -> settings.embedding_dim -> default (1024).
    """
    try:
        from app.config import settings
        return settings.embedding_dim
    except Exception:
        logger.debug("embedding_dim_settings_unavailable", fallback=1024)
        return 1024


def _to_sparse_vector(sv):
    """将 sparse 向量转换为 Qdrant SparseVector 格式。

    支持输入：
    - None / {} / [] → 空 SparseVector
    - {int: float} 字典（SiliconFlow 返回格式）→ SparseVector
    - SparseVector 对象（DashScope combined API 返回）→ 直接返回
    """
    from qdrant_client import models as qmodels
    if sv is None or sv == {} or sv == []:
        return qmodels.SparseVector(indices=[], values=[])
    if isinstance(sv, qmodels.SparseVector):
        return sv
    if isinstance(sv, dict):
        indices = sorted(sv.keys())
        values = [float(sv[k]) for k in indices]
        return qmodels.SparseVector(indices=indices, values=values)
    return qmodels.SparseVector(indices=[], values=[])


_redis_fail_count = 0


def _redis_sync_get(key: str) -> bytes | None:
    """同步 Redis GET，使用共享连接池单例。"""
    global _redis_fail_count
    try:
        from app.cache.redis_client import get_sync_redis
        r = get_sync_redis()
        if r is None:
            return None
        return r.get(key)
    except Exception as e:
        _redis_fail_count += 1
        if _redis_fail_count <= 3 or _redis_fail_count % 100 == 0:
            logger.warning("Redis GET failed (%d times): %s", _redis_fail_count, e)
        return None


def _redis_sync_setex(key: str, ttl: int, value: bytes) -> None:
    """同步 Redis SETEX，使用共享连接池单例。"""
    global _redis_fail_count
    try:
        from app.cache.redis_client import get_sync_redis
        r = get_sync_redis()
        if r is None:
            return
        r.setex(key, ttl, value)
    except Exception as e:
        _redis_fail_count += 1
        if _redis_fail_count <= 3 or _redis_fail_count % 100 == 0:
            logger.warning("Redis SETEX failed (%d times): %s", _redis_fail_count, e)


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def _estimate_embedding_tokens(text: str) -> int:
    cjk_chars = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    other_chars = max(0, len(text) - cjk_chars)
    return cjk_chars + (max(1, other_chars // 4) if other_chars else 0)


def _limit_by_estimated_tokens(text: str, max_estimated_tokens: int) -> str:
    if _estimate_embedding_tokens(text) <= max_estimated_tokens:
        return text

    end = len(text)
    while end > 1 and _estimate_embedding_tokens(text[:end]) > max_estimated_tokens:
        span_tokens = _estimate_embedding_tokens(text[:end])
        end = max(1, end * max_estimated_tokens // span_tokens)
    return text[:end]


def _provider_safe_api_text(provider: str, text: str) -> str:
    if provider == "siliconflow":
        return _limit_by_estimated_tokens(
            text[:_SILICONFLOW_SAFE_CHARS],
            _SILICONFLOW_SAFE_ESTIMATED_TOKENS,
        )
    return text


def _dashscope_compatible_embeddings_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if "compatible-" in base:
        return f"{base}/embeddings"
    if "://" not in base:
        return f"https://{base}/compatible-mode/v1/embeddings"
    scheme, rest = base.split("://", 1)
    host = rest.split("/", 1)[0]
    return f"{scheme}://{host}/compatible-mode/v1/embeddings"


def _embed_api(texts: List[str], provider: str, batch_size: int = 10,
               client: Optional[object] = None) -> np.ndarray:
    """Call a single embedding API provider. Returns (N, dim) array.

    Raises on failure — caller decides fallback strategy.

    Args:
        provider: "dashscope" | "siliconflow" | "zhipu"
        client: Optional httpx.AsyncClient for connection pooling.
                Currently unused in sync path — reserved for async migration.
                When callers become async, pass app.state.http_client to
                reuse TCP connections instead of creating new ones per request.
    """
    from app.config import settings

    if provider == "dashscope":
        url = _dashscope_compatible_embeddings_url(settings.dashscope_base_url)
        api_key = settings.dashscope_api_key
        model = settings.dashscope_model
        dim = settings.dashscope_dimensions
    elif provider == "siliconflow":
        url = f"{settings.siliconflow_base_url.rstrip('/')}/embeddings"
        api_key = settings.siliconflow_api_key
        model = settings.siliconflow_model
        dim = None  # model-determined
    elif provider == "zhipu":
        url = f"{settings.embedding_base_url.rstrip('/')}/embeddings"
        api_key = settings.embedding_api_key or settings.llm_api_key
        model = settings.embedding_model or "embedding-2"
        dim = None
    else:
        raise ValueError(f"Unknown provider: {provider}")

    if not api_key:
        raise RuntimeError(f"{provider}: API key not configured")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    all_embeddings = []

    for start in range(0, len(texts), batch_size):
        batch = [_provider_safe_api_text(provider, text) for text in texts[start:start + batch_size]]
        payload = {"model": model, "input": batch}
        if provider == "siliconflow":
            payload["encoding_format"] = "float"
        if dim and dim != 1024:
            payload["dimensions"] = dim
            payload["encoding_format"] = "float"  # DashScope needs this for non-default dimensions

        # Retry with backoff for transient SSL/connection errors
        last_err = None
        client = _get_http_client()
        for attempt in range(3):
            try:
                resp = client.post(url, headers=headers, json=payload, timeout=90.0)
                if not resp.is_success:
                    logger.error("Embedding API %s error %d: %s", provider, resp.status_code, resp.text[:300])
                resp.raise_for_status()
                break
            except (httpx.ConnectError, httpx.TimeoutException,
                    httpx.NetworkError) as e:
                last_err = e
                wait = 2 ** attempt * 5
                logger.warning("Embedding API %s attempt %d failed: %s, retrying in %ds",
                               provider, attempt + 1, e, wait)
                time.sleep(wait)
        else:
            raise last_err

        data = resp.json()
        batch_embs = [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]
        all_embeddings.extend(batch_embs)

    result = np.array(all_embeddings, dtype=np.float32)

    # Validate: reject zero vectors (broken API response)
    norms = np.linalg.norm(result, axis=1)
    zero_ratio = np.sum(norms < 1e-6) / len(norms)
    if zero_ratio > 0.05:
        raise RuntimeError(f"{provider}: {zero_ratio:.0%} zero vectors — API returning garbage")

    logger.info("Embedding via %s: %d texts, dim=%d", provider, len(texts), result.shape[1])
    return result


def _embed_dense_sparse_dashscope(texts: List[str], batch_size: int = 10,
                                   max_workers: int = 5,
                                   client: Optional[object] = None) -> tuple[np.ndarray, list]:
    """DashScope text-embedding-v4 output_type=dense&sparse 一次调用同时获取 dense + sparse.

    Args:
        client: Optional httpx.AsyncClient for connection pooling.
                Currently unused in sync path — reserved for async migration.

    Returns:
        (dense_embeddings, sparse_vectors)，dense 为 (N, dim) ndarray，
        sparse 为 List[Dict[int, float]]。
    """
    from app.config import settings

    api_key = settings.dashscope_api_key
    model = settings.dashscope_model
    dim = settings.dashscope_dimensions

    if not api_key:
        raise RuntimeError("dashscope: API key not configured")

    def _call_batch(batch: List[str]) -> tuple[list, list]:
        """单批 API 调用，返回 (dense_list, sparse_list)。"""
        # DashScope v4 支持 output_type 参数，通过 DashScope 原生 API。
        # 根据 dashscope_base_url 推导原生 API URL
        # 新加坡节点: ws-xxx.ap-southeast-1.maas.aliyuncs.com
        # 国际版: dashscope-intl.aliyuncs.com
        # 国内版: dashscope.aliyuncs.com
        base = settings.dashscope_base_url.rstrip("/")
        if "ap-southeast-1" in base:
            # 新加坡节点 — 从 base_url 提取主机
            host = base.split("://")[1].split("/")[0]
            dashscope_url = f"https://{host}/api/v1/services/embeddings/text-embedding/text-embedding"
        elif "intl" in base:
            dashscope_url = "https://dashscope-intl.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        else:
            dashscope_url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        ds_payload = {
            "model": model,
            "input": {"texts": batch},
            "parameters": {
                "dimension": dim,
                "output_type": "dense&sparse",
            },
        }
        ds_headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        last_err = None
        client = _get_http_client()
        for attempt in range(3):
            try:
                resp = client.post(dashscope_url, headers=ds_headers, json=ds_payload, timeout=90.0)
                if not resp.is_success:
                    logger.warning("DashScope dense&sparse API error %d: %s", resp.status_code, resp.text[:300])
                resp.raise_for_status()
                break
            except (httpx.ConnectError, httpx.TimeoutException,
                    httpx.NetworkError) as e:
                last_err = e
                wait = 2 ** attempt * 5
                logger.warning("DashScope dense&sparse attempt %d failed: %s, retry in %ds", attempt + 1, e, wait)
                time.sleep(wait)
        else:
            raise last_err

        data = resp.json()
        output = data.get("output", {})
        embeddings_data = output.get("embeddings", [])

        # 按 text_index 排序
        embeddings_data.sort(key=lambda x: x.get("text_index", 0))

        batch_dense = []
        batch_sparse = []
        for item in embeddings_data:
            batch_dense.append(item.get("embedding", []))
            sparse_raw = item.get("sparse_embedding", [])
            # sparse_embedding 格式: [{"index": int, "value": float, "token": str}, ...]
            # 转换为 Qdrant SparseVector(indices, values) 格式
            from qdrant_client import models as qmodels
            if sparse_raw:
                indices = []
                values = []
                for entry in sparse_raw:
                    idx = entry.get("index")
                    val = entry.get("value", 0.0)
                    if idx is not None and val != 0:
                        indices.append(idx)
                        values.append(float(val))
                batch_sparse.append(qmodels.SparseVector(indices=indices, values=values) if indices else None)
            else:
                batch_sparse.append(None)

        return batch_dense, batch_sparse

    # 并发调用多批
    from concurrent.futures import ThreadPoolExecutor, as_completed

    all_dense = [None] * len(texts)
    all_sparse = [None] * len(texts)
    batches = []
    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        batches.append((start, batch))

    if len(batches) <= 1 or max_workers <= 1:
        # 单批不需要并发
        for start, batch in batches:
            bd, bs = _call_batch(batch)
            for j, (d, s) in enumerate(zip(bd, bs)):
                all_dense[start + j] = d
                all_sparse[start + j] = s
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {}
            for start, batch in batches:
                f = pool.submit(_call_batch, batch)
                future_map[f] = start
            for f in as_completed(future_map):
                start = future_map[f]
                try:
                    bd, bs = f.result()
                except Exception as e:
                    logger.error("DashScope dense&sparse batch at offset %d failed: %s", start, e)
                    raise
                for j, (d, s) in enumerate(zip(bd, bs)):
                    all_dense[start + j] = d
                    all_sparse[start + j] = s

    # 检查是否有 None 条目（batch 失败残留）
    none_count = sum(1 for d in all_dense if d is None)
    if none_count:
        raise RuntimeError(f"dashscope dense&sparse: {none_count}/{len(all_dense)} embeddings are None")

    dense_result = np.array(all_dense, dtype=np.float32)

    # 验证
    norms = np.linalg.norm(dense_result, axis=1)
    zero_ratio = np.sum(norms < 1e-6) / len(norms)
    if zero_ratio > 0.05:
        raise RuntimeError(f"dashscope dense&sparse: {zero_ratio:.0%} zero vectors")

    sparse_count = sum(1 for s in all_sparse if s)
    logger.info("Embedding via dashscope dense&sparse: %d texts, dim=%d, sparse=%d",
                len(texts), dense_result.shape[1], sparse_count)
    return dense_result, all_sparse


def embed_texts_as_list(texts: List[str], client: Optional[object] = None) -> List[np.ndarray]:
    """Embed texts and return as list of vectors (for SemanticTextSplitter).

    Wrapper around embed_texts_llm that returns a list of individual vectors
    instead of a 2D numpy array.
    """
    if not texts:
        return []
    result = embed_texts_llm(texts, client=client)
    return [result[i] for i in range(len(texts))]


def embed_texts_llm(texts: List[str], batch_size: int = 10,
                    client: Optional[object] = None) -> np.ndarray:
    """Multi-provider embedding with fallback chain.

    Priority: DashScope → SiliconFlow → Zhipu.

    Args:
        client: Optional httpx.AsyncClient for connection pooling.
                Passed through to provider functions for future async migration.

    Raises if ALL providers fail. Never returns zero vectors.
    """
    from app.config import settings

    # 1. Check in-memory cache first (fastest)
    uncached: List[tuple[int, str]] = []
    result = [None] * len(texts)
    with _embed_cache_lock:
        for i, t in enumerate(texts):
            key = _cache_key(t)
            if key in _embed_cache:
                result[i] = _embed_cache[key]
                _embed_cache.move_to_end(key)  # LRU: 标记为最近使用
            else:
                uncached.append((i, t))
    if not uncached:
        return np.array(result, dtype=np.float32)

    # 2. Check Redis cache for remaining texts
    try:
        if uncached:
            still_uncached = []
            for idx, t in uncached:
                key = _cache_key(t)
                cached = _redis_sync_get(f"embed:{key}")
                if cached:
                    emb = np.frombuffer(cached, dtype=np.float32)
                    result[idx] = emb
                    with _embed_cache_lock:
                        _embed_cache[key] = emb
                else:
                    still_uncached.append((idx, t))
            uncached = still_uncached
            if not uncached:
                return np.array(result, dtype=np.float32)
    except Exception as e:
        logger.debug("redis_embed_cache_read_failed", error=str(e))

    uncached_texts = [t for _, t in uncached]

    # 3. API fallback chain
    providers = []
    if settings.dashscope_api_key:
        providers.append("dashscope")
    if settings.siliconflow_api_key:
        providers.append("siliconflow")
    if settings.embedding_api_key or settings.llm_api_key:
        providers.append("zhipu")

    if not providers:
        raise RuntimeError(
            "No embedding provider available. "
            "Set DASHSCOPE_API_KEY or EMBEDDING_API_KEY in .env"
        )

    embeddings = None
    last_error = None
    provider_errors = []
    for p in providers:
        try:
            embeddings = _embed_api(uncached_texts, p, batch_size, client=client)
            break
        except Exception as e:
            logger.warning("Embedding provider %s failed: %s", p, e)
            last_error = e
            provider_errors.append(f"{p}: {type(e).__name__}: {str(e)[:200]}")

    if embeddings is None:
        error_summary = "; ".join(provider_errors)
        raise RuntimeError(f"All embedding providers failed. {error_summary}. Last error: {last_error}")

    # 4. Fill results + update cache
    with _embed_cache_lock:
        for (idx, text), emb in zip(uncached, embeddings):
            result[idx] = emb
            key = _cache_key(text)
            _embed_cache[key] = emb

    # Persist to Redis outside lock (I/O operation)
    for (idx, text), emb in zip(uncached, embeddings):
        key = _cache_key(text)
        try:
            _redis_sync_setex(f"embed:{key}", 86400 * 7, emb.astype(np.float32).tobytes())
        except Exception as e:
            logger.debug("redis_embed_cache_write_failed", error=str(e))

    # Evict if over limit (LRU: 删除最久未使用的条目)
    with _embed_cache_lock:
        while len(_embed_cache) > _EMBED_CACHE_MAX:
            _embed_cache.popitem(last=False)

    return np.array(result, dtype=np.float32)
