# -*- coding: utf-8 -*-

"""Cross-encoder reranker for RAG system.



Local CrossEncoder with GPU/CPU fallback and remote API reranking.

Extracted from vector_store.py.

"""



from typing import List, Dict, Any, Optional

import asyncio

import httpx
import structlog

from app.config import settings



logger = structlog.get_logger()



# ���� Cross-Encoder Reranker (lazy-loaded singleton) ����

_reranker = None

_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"





def _get_reranker():

    """Lazy-load cross-encoder reranker. Returns None if unavailable.



    Always skips loading when:

    - RERANK_ENABLED=false (env var)

    - GPU_ENABLED=false (env var) �� prevents OOM on Railway

    - Less than 500MB RAM available

    """

    global _reranker

    if _reranker is None:

        from app.config import settings as _cfg

        if not _cfg.rerank.rerank_enabled:

            logger.info("Reranker disabled (rerank_enabled=false), skipping CrossEncoder load")

            _reranker = False

            return None



        # Memory guard: skip loading if <500MB free to prevent OOM on constrained containers

        try:

            import psutil

            avail_mb = psutil.virtual_memory().available / (1024 * 1024)

            if avail_mb < 500:

                logger.warning("Skipping reranker load: only %.0fMB RAM available (need ~2200MB)", avail_mb)

                _reranker = False

                return None

        except ImportError:

            pass  # psutil not installed, proceed without memory check

        try:

            from sentence_transformers import CrossEncoder

            _reranker = CrossEncoder(_RERANKER_MODEL)

            logger.info("Cross-encoder reranker loaded: %s", _RERANKER_MODEL)

        except Exception as e:

            logger.warning("Reranker unavailable: %s", e)

            _reranker = False

    return _reranker if _reranker is not False else None





def _rerank_via_api(query: str, chunks: List[Dict[str, Any]], top_k: int = 3,
                    client: Optional[object] = None) -> Optional[List[Dict[str, Any]]]:
    """Rerank chunks via remote API. Returns None if unavailable.

    Provider priority (env: RERANK_PROVIDER):
    1. DashScope qwen3-rerank (same platform as embedding, <5ms from Singapore)
    2. SiliconFlow BAAI/bge-reranker-v2-m3
    3. Cohere rerank-multilingual-v3.0
    4. Jina jina-reranker-v2-base-multilingual

    Args:
        client: Optional httpx.AsyncClient for connection pooling.
                Currently unused in sync path — reserved for async migration.
    """

    texts = [c["text"] for c in chunks]

    from app.config import settings as _cfg

    preferred = _cfg.rerank.rerank_provider



    # ���� Helper: generic rerank POST ����

    def _call_rerank(url: str, api_key: str, model: str, provider_name: str,

                     extra_body: dict | None = None) -> Optional[List[Dict[str, Any]]]:

        body: dict = {

            "model": model,

            "query": query,

            "documents": texts,

            "top_n": top_k,

        }

        if extra_body:

            body.update(extra_body)

        try:

            resp = httpx.post(

                url,

                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},

                json=body,

                timeout=15.0,

            )

            resp.raise_for_status()

            data = resp.json()

            scored = []

            for item in data.get("results", []):

                idx = item["index"]

                score = item["relevance_score"]

                chunk = chunks[idx].copy()

                chunk["rerank_score"] = float(score)

                scored.append(chunk)

            scored.sort(key=lambda x: x["rerank_score"], reverse=True)

            logger.info("API rerank (%s): %d chunks -> %d results", provider_name, len(chunks), len(scored))

            return scored[:top_k]

        except Exception as e:

            logger.warning("%s API rerank failed: %s", provider_name, e)

            return None



    # ���� Build provider list (preferred first, then fallbacks) ����

    ds_key = settings.dashscope_api_key

    sf_key = settings.siliconflow_api_key

    cohere_key = getattr(settings, "cohere_api_key", None)

    jina_key = getattr(settings, "jina_api_key", None)



    providers = []

    if preferred == "dashscope" and ds_key:

        providers.append(("dashscope", ds_key, settings.dashscope_rerank_model, settings.dashscope_rerank_url))

    if sf_key:

        providers.append(("siliconflow", sf_key, "BAAI/bge-reranker-v2-m3", settings.siliconflow_base_url))

    if cohere_key:

        providers.append(("cohere", cohere_key, settings.cohere_rerank_model, "https://api.cohere.ai/v2"))

    if jina_key:

        providers.append(("jina", jina_key, "jina-reranker-v2-base-multilingual", "https://api.jina.ai/v1"))

    # Add dashscope as fallback if it wasn't the preferred

    if preferred != "dashscope" and ds_key:

        providers.append(("dashscope", ds_key, settings.dashscope_rerank_model, settings.dashscope_rerank_url))



    for name, key, model, base_url in providers:

        # DashScope qwen3-rerank uses /reranks (plural), others use /rerank

        suffix = "reranks" if name == "dashscope" else "rerank"

        url = f"{base_url.rstrip('/')}/{suffix}"

        result = _call_rerank(url, key, model, name)

        if result is not None:

            return result



    return None






# ── Batch parallel reranking ──────────────────────────────────────
def _get_rerank_provider_info() -> Optional[tuple]:
    """Get first available rerank provider (url, api_key, model, name)."""
    from app.config import settings as _cfg
    preferred = _cfg.rerank.rerank_provider

    ds_key = settings.dashscope_api_key
    sf_key = settings.siliconflow_api_key
    cohere_key = getattr(settings, "cohere_api_key", None)
    jina_key = getattr(settings, "jina_api_key", None)

    providers = []
    if preferred == "dashscope" and ds_key:
        providers.append(("dashscope", ds_key, settings.dashscope_rerank_model, settings.dashscope_rerank_url))
    if sf_key:
        providers.append(("siliconflow", sf_key, "BAAI/bge-reranker-v2-m3", settings.siliconflow_base_url))
    if cohere_key:
        providers.append(("cohere", cohere_key, settings.cohere_rerank_model, "https://api.cohere.ai/v2"))
    if jina_key:
        providers.append(("jina", jina_key, "jina-reranker-v2-base-multilingual", "https://api.jina.ai/v1"))
    if preferred != "dashscope" and ds_key:
        providers.append(("dashscope", ds_key, settings.dashscope_rerank_model, settings.dashscope_rerank_url))

    for name, key, model, base_url in providers:
        suffix = "reranks" if name == "dashscope" else "rerank"
        url = f"{base_url.rstrip('/')}/{suffix}"
        return (url, key, model, name)

    return None


async def _rerank_batch_async(
    url: str, api_key: str, model: str, provider_name: str,
    query: str, chunks: List[Dict[str, Any]], top_k: int,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Single async rerank request (used by batch parallel).

    Args:
        client: Shared httpx.AsyncClient with connection pooling.
                If None, creates a temporary client (backward compatible).
    """
    texts = [c["text"] for c in chunks]
    body: dict = {
        "model": model,
        "query": query,
        "documents": texts,
        "top_n": min(top_k, len(chunks)),
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if client is not None:
        resp = await client.post(url, headers=headers, json=body, timeout=20.0)
    else:
        async with httpx.AsyncClient() as tmp_client:
            resp = await tmp_client.post(url, headers=headers, json=body, timeout=20.0)

    resp.raise_for_status()
    data = resp.json()

    scored = []
    for item in data.get("results", []):
        idx = item["index"]
        score = item["relevance_score"]
        chunk = chunks[idx].copy()
        chunk["rerank_score"] = float(score)
        scored.append(chunk)

    return scored


async def _rerank_via_api_batched(
    query: str, chunks: List[Dict[str, Any]], top_k: int = 3,
    batch_size: int = 18, max_concurrent: int = 2,
    client: Optional[httpx.AsyncClient] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Batch parallel reranking: split docs into batches, concurrent API calls."""
    import asyncio

    provider_info = _get_rerank_provider_info()
    if provider_info is None:
        return None

    url, api_key, model, provider_name = provider_info

    if len(chunks) <= batch_size:
        return await _rerank_batch_async(url, api_key, model, provider_name, query=query, chunks=chunks, top_k=top_k, client=client)

    batches = [chunks[i:i + batch_size] for i in range(0, len(chunks), batch_size)]
    logger.info("Batch parallel rerank: %d chunks -> %d batches", len(chunks), len(batches))

    sem = asyncio.Semaphore(max_concurrent)

    async def _limited(batch_chunks):
        async with sem:
            return await _rerank_batch_async(url, api_key, model, provider_name, query=query, chunks=batch_chunks, top_k=top_k, client=client)

    results = await asyncio.gather(*[_limited(b) for b in batches], return_exceptions=True)

    all_scored = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.warning("Batch %d failed: %s", i, result)
            continue
        if result:
            all_scored.extend(result)

    if not all_scored:
        return None

    all_scored.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
    logger.info("Batch parallel rerank merged: %d total -> top %d", len(all_scored), top_k)
    return all_scored[:top_k]


async def rerank_batched_async(query: str, chunks: List[Dict[str, Any]], top_k: int = 3,
                               batch_size: int = 18,
                               client: Optional[httpx.AsyncClient] = None) -> List[Dict[str, Any]]:
    """异步批量 rerank，供 async 路径调用。"""
    if not chunks or len(chunks) <= 1:
        return chunks
    try:
        result = await _rerank_via_api_batched(query, chunks, top_k=top_k, batch_size=batch_size, client=client)
        if result:
            return result
    except Exception as e:
        logger.warning("Batch parallel rerank failed, falling back to serial: %s", e)
    return rerank(query, chunks, top_k=top_k)


def rerank_batched(query: str, chunks: List[Dict[str, Any]], top_k: int = 3,
                   batch_size: int = 18) -> List[Dict[str, Any]]:
    """同步批量 rerank（仅在纯同步上下文中使用）。

    如果从已运行的事件循环中调用，会降级到串行 rerank。
    异步路径请使用 rerank_batched_async。
    """
    if not chunks or len(chunks) <= 1:
        return chunks
    # 检测是否已在事件循环中
    try:
        asyncio.get_running_loop()
        logger.warning("rerank_batched called from running event loop, fallback to serial rerank")
        return rerank(query, chunks, top_k=top_k)
    except RuntimeError:
        pass  # 无事件循环，asyncio.run 安全
    try:
        result = asyncio.run(_rerank_via_api_batched(query, chunks, top_k=top_k, batch_size=batch_size))
        if result:
            return result
    except Exception as e:
        logger.warning("Batch parallel rerank failed, falling back to serial: %s", e)
    return rerank(query, chunks, top_k=top_k)


def rerank(query: str, chunks: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:

    """Rerank chunks using cross-encoder or remote API. Returns top_k results.



    Backend selection (env: RERANK_BACKEND):

    - "api"   �� Cohere / Jina remote API (no local model loading, safe for Railway)

    - "local" �� CrossEncoder (GPU or CPU, requires ~500MB+ RAM)

    """

    # HARD STOP: always skip reranking when explicitly disabled

    from app.config import settings

    if not settings.rerank_enabled:

        logger.debug("rerank_enabled=false, returning top %d by score", top_k)

        return chunks[:top_k]



    if not chunks or len(chunks) <= 1:

        return chunks



    # ���� API reranker (zero local memory, ideal for Railway / serverless) ����

    rerank_backend = settings.rerank_backend

    if rerank_backend == "api":

        api_result = _rerank_via_api(query, chunks, top_k=top_k)

        if api_result is not None:

            return api_result

        # API unavailable, fall through to local reranker

        logger.warning("API reranker unavailable, falling back to local CrossEncoder")




    model = _get_reranker()

    if model is None:

        return chunks[:top_k]



    pairs = [(query, c["text"]) for c in chunks]

    scores = model.predict(pairs)



    # Attach scores and sort

    for chunk, score in zip(chunks, scores):

        chunk["rerank_score"] = float(score)



    reranked = sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)



    # No score threshold or cliff detection �� let CRAG handle relevance filtering.

    # The reranker's job is RANKING only: better results first.

    return reranked[:top_k]

