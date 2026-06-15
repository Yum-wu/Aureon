# -*- coding: utf-8 -*-

"""Cross-encoder reranker for RAG system.



Local CrossEncoder with GPU/CPU fallback and remote API reranking.

Extracted from vector_store.py.

"""



from typing import List, Dict, Any, Optional



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





def _rerank_via_api(query: str, chunks: List[Dict[str, Any]], top_k: int = 3) -> Optional[List[Dict[str, Any]]]:

    """Rerank chunks via remote API. Returns None if unavailable.



    Provider priority (env: RERANK_PROVIDER):

    1. DashScope qwen3-rerank (same platform as embedding, <5ms from Singapore)

    2. SiliconFlow BAAI/bge-reranker-v2-m3

    3. Cohere rerank-multilingual-v3.0

    4. Jina jina-reranker-v2-base-multilingual

    """

    import os

    import httpx



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

    ds_key = os.environ.get("DASHSCOPE_API_KEY") or getattr(settings, "dashscope_api_key", "")

    sf_key = os.environ.get("SILICONFLOW_API_KEY") or getattr(settings, "siliconflow_api_key", "")

    cohere_key = os.environ.get("COHERE_API_KEY") or getattr(settings, "cohere_api_key", None)

    jina_key = os.environ.get("JINA_API_KEY") or getattr(settings, "jina_api_key", None)



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

