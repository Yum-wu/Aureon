# -*- coding: utf-8 -*-

"""Embedding functions for RAG system.



Multi-provider API embedding with Redis caching and fallback chain.

Extracted from vector_store.py.

"""



import os

import hashlib

import threading

import time

import numpy as np

from typing import List, Dict, Optional



import structlog



logger = structlog.get_logger()








VECTOR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "vectors")



# ���� Embedding cache (FIFO eviction, keyed by text hash) ����

_embed_cache: Dict[str, np.ndarray] = {}

_EMBED_CACHE_MAX = 5000

_embed_cache_lock = threading.Lock()  # Thread-safe access to _embed_cache



# ���� Query embedding reuse (module-level) ����

# retrieve_qdrant stores the query embedding here so compress_context

# can reuse it without a redundant embedding API call.

# Uses module-level (not thread-local) because asyncio.to_thread runs

# compress_context in a different worker thread than retrieve_qdrant.

_last_query_embedding: Optional[np.ndarray] = None

_last_query_embedding_lock = threading.Lock()



# ���� Local embedding model (lazy-loaded singleton) ����






def _get_embedding_dim() -> int:

    """Return the active embedding dimension from settings or env var.



    Priority: EMBEDDING_DIMENSION env -> settings.embedding_dim -> default (1024).

    """

    try:

        from app.config import settings

        return settings.embedding_dim

    except Exception:

        return 1024





def _to_sparse_vector(sv):

    """�� sparse ����ת��Ϊ Qdrant SparseVector ��ʽ��



    ֧�����룺

    - None / {} / [] �� �� SparseVector

    - {int: float} �ֵ䣨SiliconFlow ���ظ�ʽ���� SparseVector

    - SparseVector ����DashScope combined API ���أ��� ֱ�ӷ���

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





def _redis_sync_get(key: str) -> bytes | None:

    """ͬ������ Redis GET���첽�ͻ�����ͬ���������е��Žӣ���



    embed_texts_llm �ں�̨�߳������У��޷�ֱ�� await �첽 Redis ������

    ʹ��ͬ�� Redis �ͻ��ˣ�decode_responses=False �Ի�ȡ bytes����

    """

    try:

        import redis as redis_sync

        from app.config import settings as _cfg

        sync_redis = redis_sync.Redis.from_url(

            _cfg.redis_url or "redis://localhost:6379/0",

            decode_responses=False,

            socket_connect_timeout=2,

            socket_timeout=2,

        )

        return sync_redis.get(key)

    except Exception:

        return None





def _redis_sync_setex(key: str, ttl: int, value: bytes) -> None:

    """ͬ������ Redis SETEX���첽�ͻ�����ͬ���������е��Žӣ���"""

    try:

        import redis as redis_sync

        from app.config import settings as _cfg

        sync_redis = redis_sync.Redis.from_url(

            _cfg.redis_url or "redis://localhost:6379/0",

            decode_responses=False,

            socket_connect_timeout=2,

            socket_timeout=2,

        )

        sync_redis.setex(key, ttl, value)

    except Exception:

        pass





def _cache_key(text: str) -> str:

    return hashlib.md5(text.encode()).hexdigest()





def get_thread_query_embedding() -> Optional[np.ndarray]:

    """Retrieve the last query embedding stored by retrieve_qdrant.



    Used by compress_context to avoid redundant embedding API calls.

    Uses module-level storage (not thread-local) to work across asyncio.to_thread boundaries.

    """

    with _last_query_embedding_lock:

        return _last_query_embedding





def _set_thread_query_embedding(emb: np.ndarray) -> None:

    """Store query embedding for downstream reuse by compress_context."""

    global _last_query_embedding

    with _last_query_embedding_lock:

        _last_query_embedding = emb








def _embed_api(texts: List[str], provider: str, batch_size: int = 10) -> np.ndarray:

    """Call a single embedding API provider. Returns (N, dim) array.



    Raises on failure �� caller decides fallback strategy.



    Args:

        provider: "dashscope" | "siliconflow" | "zhipu"

    """

    from app.config import settings

    import requests



    if provider == "dashscope":

        url = f"{settings.dashscope_base_url.rstrip('/')}/embeddings"

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

        batch = texts[start:start + batch_size]

        payload = {"model": model, "input": batch}

        if dim and dim != 1024:

            payload["dimensions"] = dim

            payload["encoding_format"] = "float"  # DashScope needs this for non-default dimensions



        # Retry with backoff for transient SSL/connection errors

        last_err = None

        for attempt in range(3):

            try:

                resp = requests.post(url, headers=headers, json=payload, timeout=90)

                if not resp.ok:

                    logger.error("Embedding API %s error %d: %s", provider, resp.status_code, resp.text[:300])

                resp.raise_for_status()

                break

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,

                    requests.exceptions.SSLError) as e:

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

    if zero_ratio > 0.5:

        raise RuntimeError(f"{provider}: {zero_ratio:.0%} zero vectors �� API returning garbage")



    logger.info("Embedding via %s: %d texts, dim=%d", provider, len(texts), result.shape[1])

    return result





def _embed_dense_sparse_dashscope(texts: List[str], batch_size: int = 10,

                                   max_workers: int = 5) -> tuple[np.ndarray, list]:

    """DashScope text-embedding-v4 output_type=dense&sparse һ�ε���ͬʱ��ȡ dense + sparse��



    Returns:

        (dense_embeddings, sparse_vectors) �� dense Ϊ (N, dim) ndarray��

        sparse Ϊ List[Dict[int, float]]��

    """

    from app.config import settings

    import requests



    api_key = settings.dashscope_api_key

    model = settings.dashscope_model

    dim = settings.dashscope_dimensions



    if not api_key:

        raise RuntimeError("dashscope: API key not configured")



    def _call_batch(batch: List[str]) -> tuple[list, list]:

        """���� API ���ã����� (dense_list, sparse_list)��"""

        # DashScope v4 ֧�� output_type ������ͨ�� DashScope ԭ�� API��

        # ���� dashscope_base_url �Ƶ�ԭ�� API URL

        # �¼���: ws-xxx.ap-southeast-1.maas.aliyuncs.com

        # ���ʰ������: dashscope-intl.aliyuncs.com

        # ���ڰ�: dashscope.aliyuncs.com

        base = settings.dashscope_base_url.rstrip("/")

        if "ap-southeast-1" in base:

            # �¼��½ڵ� �� �� base_url ��ȡ����

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

        for attempt in range(3):

            try:

                resp = requests.post(dashscope_url, headers=ds_headers, json=ds_payload, timeout=90)

                if not resp.ok:

                    logger.warning("DashScope dense&sparse API error %d: %s", resp.status_code, resp.text[:300])

                resp.raise_for_status()

                break

            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,

                    requests.exceptions.SSLError) as e:

                last_err = e

                wait = 2 ** attempt * 5

                logger.warning("DashScope dense&sparse attempt %d failed: %s, retry in %ds", attempt + 1, e, wait)

                time.sleep(wait)

        else:

            raise last_err



        data = resp.json()

        output = data.get("output", {})

        embeddings_data = output.get("embeddings", [])



        # �� text_index ����

        embeddings_data.sort(key=lambda x: x.get("text_index", 0))



        batch_dense = []

        batch_sparse = []

        for item in embeddings_data:

            batch_dense.append(item.get("embedding", []))

            sparse_raw = item.get("sparse_embedding", [])

            # sparse_embedding ��ʽ: [{"index": int, "value": float, "token": str}, ...]

            # ת��Ϊ Qdrant SparseVector(indices, values) ��ʽ

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



    # �������ö���

    from concurrent.futures import ThreadPoolExecutor, as_completed



    all_dense = [None] * len(texts)

    all_sparse = [None] * len(texts)

    batches = []

    for start in range(0, len(texts), batch_size):

        batch = texts[start:start + batch_size]

        batches.append((start, batch))



    if len(batches) <= 1 or max_workers <= 1:

        # ��������Ҫ����

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

                bd, bs = f.result()

                for j, (d, s) in enumerate(zip(bd, bs)):

                    all_dense[start + j] = d

                    all_sparse[start + j] = s



    dense_result = np.array(all_dense, dtype=np.float32)



    # ��֤

    norms = np.linalg.norm(dense_result, axis=1)

    zero_ratio = np.sum(norms < 1e-6) / len(norms)

    if zero_ratio > 0.5:

        raise RuntimeError(f"dashscope dense&sparse: {zero_ratio:.0%} zero vectors")



    sparse_count = sum(1 for s in all_sparse if s)

    logger.info("Embedding via dashscope dense&sparse: %d texts, dim=%d, sparse=%d",

                len(texts), dense_result.shape[1], sparse_count)

    return dense_result, all_sparse





def embed_texts_as_list(texts: List[str]) -> List[np.ndarray]:

    """Embed texts and return as list of vectors (for SemanticTextSplitter).



    Wrapper around embed_texts_llm that returns a list of individual vectors

    instead of a 2D numpy array.

    """

    if not texts:

        return []

    result = embed_texts_llm(texts)

    return [result[i] for i in range(len(texts))]





def embed_texts_llm(texts: List[str], batch_size: int = 10) -> np.ndarray:

    """Multi-provider embedding with fallback chain.



    Priority: DashScope �� DashScope (768d) �� SiliconFlow �� Zhipu.

    
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

    except Exception:

        pass  # Redis unavailable, continue with API



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

    for p in providers:

        try:

            embeddings = _embed_api(uncached_texts, p, batch_size)

            break

        except Exception as e:

            logger.warning("Embedding provider %s failed: %s", p, e)

            last_error = e



    if embeddings is None:

        raise RuntimeError(f"All embedding providers failed. Last error: {last_error}")



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

        except Exception:

            pass



    # Evict if over limit

    with _embed_cache_lock:

        if len(_embed_cache) > _EMBED_CACHE_MAX:

            for k in list(_embed_cache.keys())[:len(_embed_cache) - _EMBED_CACHE_MAX]:

                del _embed_cache[k]



    return np.array(result, dtype=np.float32)

