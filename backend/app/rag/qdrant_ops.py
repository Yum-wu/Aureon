# -*- coding: utf-8 -*-

"""Qdrant vector store operations for RAG system.



Qdrant client management, index saving, hybrid search, and retrieval.

Extracted from vector_store.py.

"""



import time
import threading

import numpy as np

from typing import List, Dict



import structlog

from app.config import settings

from app.multi_tenant.middleware import get_current_tenant_id



logger = structlog.get_logger()


# ── tenant_id 检查缓存（避免每次查询都 scroll） ──
_tenant_id_cache: dict = {"value": None, "updated_at": 0.0}
_TENANT_ID_CACHE_TTL = 300  # 5 分钟



# ���� Qdrant Backend ����

_qdrant_client = None
_qdrant_lock = threading.Lock()

_qdrant_available = False  # Global flag: True if Qdrant is reachable





def _get_qdrant():

    """Get or create Qdrant client singleton.



    Auto-detects mode from URL scheme:

    - https:// �� Qdrant Cloud (REST only, no gRPC)

    - http://localhost �� local Qdrant (gRPC preferred)

    """

    global _qdrant_client

    if _qdrant_client is not None:  # Fast path (no lock)
        return _qdrant_client

    with _qdrant_lock:
        if _qdrant_client is not None:  # Double-check
            return _qdrant_client

        from qdrant_client import QdrantClient

        from app.config import settings

        url = settings.qdrant_url

        kwargs: dict = {"url": url}

        if url.startswith("https://"):

            # Qdrant Cloud: REST only, gRPC not supported

            pass

        else:

            # Local Qdrant: prefer gRPC for lower latency

            kwargs["prefer_grpc"] = True

            kwargs["grpc_port"] = 6334

        if settings.qdrant_api_key:

            kwargs["api_key"] = settings.qdrant_api_key

        _qdrant_client = QdrantClient(**kwargs)

    return _qdrant_client





def _get_qdrant_collection_name() -> str:

    """Get Qdrant collection name from settings."""

    from app.config import settings

    return settings.qdrant_collection or "aureon"





def save_index_qdrant(chunks: List[Dict], collection_name: str = "aureon"):

    """Save chunks to Qdrant vector store.

    分布式锁保护：当配置不匹配需要 delete+rebuild 时，使用 Redis 分布式锁
    防止多实例同时重建索引导致数据丢失。
    """
    lock_acquired = False
    lock_key = f"aureon:index_rebuild:{collection_name}"
    lock_token = None  # UUID token for safe release

    # Lua script: atomic release — only delete if we own the lock
    _RELEASE_LOCK_SCRIPT = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """

    from qdrant_client import models as qmodels

    from qdrant_client.models import PointStruct

    from app.rag.embedding import (

        _get_embedding_dim, _to_sparse_vector, _embed_dense_sparse_dashscope,

        embed_texts_llm,

    )



    client = _get_qdrant()

    dim = _get_embedding_dim()



    # ��鼯���Ƿ��Ѵ���������ƥ��

    collection_exists = False

    config_matches = False

    try:

        info = client.get_collection(collection_name)

        collection_exists = True

        from qdrant_client.models import Distance

        vectors_config = info.config.params.vectors

        sparse_config = info.config.params.sparse_vectors

        if settings.sparse_enabled:

            # ��Ҫͬʱ�� dense �� sparse ��������

            if (isinstance(vectors_config, dict) and "dense" in vectors_config

                    and isinstance(sparse_config, dict) and "sparse" in sparse_config):

                dense_cfg = vectors_config["dense"]

                if (hasattr(dense_cfg, "size") and dense_cfg.size == dim and

                    hasattr(dense_cfg, "distance") and dense_cfg.distance == Distance.COSINE):

                    config_matches = True

        else:

            # ������ sparse ʱ������ӦΪ��һ��������������

            if not isinstance(vectors_config, dict):

                if (hasattr(vectors_config, "size") and vectors_config.size == dim and

                    hasattr(vectors_config, "distance") and vectors_config.distance == Distance.COSINE):

                    config_matches = True

    except Exception as e:

        logger.debug("collection_config_check_failed", error=str(e))



    # 只在配置不匹配时删除重建，配置匹配时直接 upsert 即可
    if collection_exists and config_matches:

        logger.info("Collection '%s' exists with matching config, upserting %d chunks", collection_name, len(chunks))

    else:

        # 分布式锁：防止多实例同时删除+重建集合
        # 只在需要重建时加锁，upsert 不需要锁
        try:
            import uuid as _uuid
            from app.cache.redis_client import get_sync_redis
            r = get_sync_redis()
            if r is not None:
                lock_token = _uuid.uuid4().hex
                lock_acquired = r.set(lock_key, lock_token, nx=True, ex=600)  # 10 min TTL
                if not lock_acquired:
                    logger.info("Another instance is rebuilding index '%s', waiting...", collection_name)
                    # Wait with 1s polling (max 60 attempts = 1 min)
                    import time as _wt
                    for _ in range(60):
                        _wt.sleep(1)
                        lock_acquired = r.set(lock_key, lock_token, nx=True, ex=600)
                        if lock_acquired:
                            break
                    if not lock_acquired:
                        logger.warning("Timed out waiting for index rebuild lock on '%s'", collection_name)
                        return
        except Exception as e:
            logger.warning("Distributed lock unavailable, proceeding without lock: %s", e)
            lock_acquired = True  # Redis 不可用时跳过锁

        try:
            if collection_exists:
                logger.info("Collection '%s' config mismatch, deleting and recreating", collection_name)

            try:
                client.delete_collection(collection_name)
            except Exception as e:
                logger.debug("delete_collection_failed", collection=collection_name, error=str(e))
        except Exception as e:
            logger.error("Failed to rebuild collection '%s': %s", collection_name, e)
            # 释放锁（Lua 原子释放，防止误删他人锁）
            if lock_acquired and lock_token:
                try:
                    from app.cache.redis_client import get_sync_redis
                    r = get_sync_redis()
                    if r is not None:
                        r.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)
                except Exception:
                    try:
                        r.delete(lock_key)
                    except Exception as e:
                        logger.debug("redis_lock_release_failed", error=str(e))
            raise

    # 根据是否启用 sparse 向量选择 vectors_config

    if settings.sparse_enabled:

        vectors_config = {

            "dense": qmodels.VectorParams(

                size=dim,

                distance=qmodels.Distance.COSINE,

                on_disk=settings.vectors_on_disk,

                hnsw_config=qmodels.HnswConfigDiff(

                    m=settings.hnsw_m,

                    ef_construct=settings.hnsw_ef_construct,

                ),

            ),

        }

        sparse_vectors_config = {

            "sparse": qmodels.SparseVectorParams(

                index=qmodels.SparseIndexParams(on_disk=False),

            ),

        }

    else:

        vectors_config = qmodels.VectorParams(

            size=dim,

            distance=qmodels.Distance.COSINE,

            on_disk=settings.vectors_on_disk,

            hnsw_config=qmodels.HnswConfigDiff(

                m=settings.hnsw_m,

                ef_construct=settings.hnsw_ef_construct,

            ),

        )

        sparse_vectors_config = None



    def _call_create(hnsw_ef_search: bool = True):

        kwargs = dict(

            collection_name=collection_name,

            vectors_config=vectors_config,

            quantization_config=qmodels.ScalarQuantization(

                scalar=qmodels.ScalarQuantizationConfig(

                    type=qmodels.ScalarType.INT8,

                    quantile=0.99,

                    always_ram=True,

                ),

            ) if settings.quantization_enabled else None,

        )

        if sparse_vectors_config is not None:

            kwargs["sparse_vectors_config"] = sparse_vectors_config

        if hnsw_ef_search:

            kwargs["hnsw_config"] = qmodels.HnswConfigDiff(

                ef_search=settings.hnsw_ef_search,

            )

        client.create_collection(**kwargs)



    # ֻ����Ҫʱ�������ϣ����ϲ����ڻ����ò�ƥ�䱻ɾ����

    if not (collection_exists and config_matches):

        try:

            _call_create(hnsw_ef_search=True)

        except Exception as e:

            err_str = str(e).lower()

            if "ef_search" in err_str or "extra_forbidden" in err_str:

                # qdrant-client �汾������ ef_search�����˵��� ef_search ����

                logger.warning("HnswConfigDiff.ef_search not supported, retrying without: %s", e)

                _call_create(hnsw_ef_search=False)

            else:

                raise



        # ���� Payload ����

        for field_name in ["metadata.slug", "metadata.language", "metadata.source", "metadata.tenant_id"]:

            try:

                client.create_payload_index(

                    collection_name=collection_name,

                    field_name=field_name,

                    field_schema=qmodels.PayloadSchemaType.KEYWORD,

                )

            except Exception as e:

                logger.debug("payload_index_already_exists", field=field_name, error=str(e))



    # ��Ƕ��� upsert������ʹ�� DashScope dense&sparse �ϲ��ӿڣ�һ�� API ����ͬʱ��ȡ��

    # �������������˵��ֿ��� dense + sparse embed

    embed_batch_size = 10  # ÿ�� embed ���ı�����DashScope v4 Ӳ���� 10 ��/����

    embed_max_workers = 5  # ���� embed ������

    upsert_batch_size = 100  # ÿ�� upsert �� point ��

    pending_points: list = []

    total_upserted = 0



    # �ж��Ƿ����ʹ�� DashScope dense&sparse �ϲ��ӿ�

    use_combined = (

        settings.sparse_enabled

        and settings.dashscope_api_key

        and settings.dashscope_model in ("text-embedding-v3", "text-embedding-v4")

    )



    if use_combined:

        # ·�� A��DashScope dense&sparse �ϲ��ӿ� + ����

        logger.info("Using DashScope dense&sparse combined API (max_workers=%d)", embed_max_workers)

        all_texts = [c["text"] for c in chunks]



        try:

            all_embeddings, all_sparse = _embed_dense_sparse_dashscope(

                all_texts, batch_size=embed_batch_size, max_workers=embed_max_workers

            )

        except Exception as e:

            logger.warning("DashScope dense&sparse failed: %s, falling back to separate embed", e)

            use_combined = False



    if not use_combined:

        # ·�� B���ֿ��� dense + sparse embed��������ʽ��

        from app.rag.sparse_embed import embed_sparse



    for batch_start in range(0, len(chunks), embed_batch_size):

        batch_end = min(batch_start + embed_batch_size, len(chunks))



        if use_combined:

            # ·�� A��ֱ�Ӵ��� embed �Ľ����ȡ

            batch_embeddings = all_embeddings[batch_start:batch_end]

            batch_sparse = all_sparse[batch_start:batch_end]

        else:

            # ·�� B������ embed

            batch_texts = [c["text"] for c in chunks[batch_start:batch_end]]

            logger.info("Embedding batch %d-%d/%d ...", batch_start, batch_end, len(chunks))



            batch_embeddings = embed_texts_llm(batch_texts)



            batch_sparse = embed_sparse(batch_texts) if settings.sparse_enabled else [{}] * len(batch_texts)



        # ���� points

        for j, idx in enumerate(range(batch_start, batch_end)):

            if settings.sparse_enabled:

                sv = _to_sparse_vector(batch_sparse[j])

                vector_data = {"dense": batch_embeddings[j].tolist(), "sparse": sv}

            else:

                vector_data = batch_embeddings[j].tolist()

            point_payload = {"metadata": chunks[idx].get("metadata", {}), "text": chunks[idx]["text"]}

            # �ڵ�һ�� point �� payload �м�¼��������

            if idx == 0:

                point_payload["_index_config"] = {

                    "embedding_dim": dim,

                    "embedding_model": settings.dashscope_model,

                    "sparse_enabled": settings.sparse_enabled,

                    "chunk_size": 512,  # 与 indexer.py child_chunk_size 保持一致

                    "created_at": time.time(),

                }

            pending_points.append(PointStruct(

                id=idx,

                vector=vector_data,

                payload=point_payload,

            ))



        # ���ܵ� upsert_batch_size �����һ��ʱд��

        if len(pending_points) >= upsert_batch_size or batch_end == len(chunks):

            client.upsert(collection_name=collection_name, points=pending_points)

            total_upserted += len(pending_points)

            logger.info("Qdrant: upserted %d/%d chunks into '%s'", total_upserted, len(chunks), collection_name)

            pending_points = []



    logger.info("Qdrant: indexed %d chunks into '%s' (complete)", len(chunks), collection_name)

    # 释放分布式锁（Lua 原子释放，防止误删他人锁）
    if lock_acquired and lock_token:
        try:
            from app.cache.redis_client import get_sync_redis
            r = get_sync_redis()
            if r is not None:
                r.eval(_RELEASE_LOCK_SCRIPT, 1, lock_key, lock_token)
        except Exception:
            try:
                r.delete(lock_key)
            except Exception as e:
                logger.debug("redis_lock_release_failed", error=str(e))





def hybrid_search_qdrant(

    query: str,

    top_k: int = 5,

    collection_name: str = "aureon",

    tenant_id: str = None,

    lang_filter: str = None,

    query_complexity: str = "simple",

) -> List[Dict]:

    """Qdrant ԭ�����������dense + sparse��RRF �ںϡ�



    ʹ�� Qdrant Query API (v1.10+) prefetch + Fusion.RRF��

    �� sparse ������ʱ���˵� hybrid_retrieve��

    """

    if not settings.sparse_enabled:

        from app.rag.qa_chain import hybrid_retrieve

        return hybrid_retrieve(query, top_k=top_k, lang_filter=lang_filter)



    from qdrant_client import models as qmodels

    from app.rag.embedding import (

        _to_sparse_vector, _embed_dense_sparse_dashscope,

        embed_texts_llm,

    )

    from app.rag.bm25 import retrieve_keyword



    client = _get_qdrant()

    if tenant_id is None:

        tenant_id = get_current_tenant_id()



    # 1. ���� query �� dense + sparse ������������ DashScope combined API��

    try:

        if True and settings.dashscope_model in ("text-embedding-v3", "text-embedding-v4"):

            # �� DashScope dense&sparse combined API һ�λ�ȡ

            query_emb, sparse_results = _embed_dense_sparse_dashscope([query], batch_size=1, max_workers=1)

            dense_vector = query_emb[0].tolist()

            sparse_vector = sparse_results[0] if sparse_results else None
            if sparse_vector is not None:
                sparse_vector = _to_sparse_vector(sparse_vector)

        else:

            query_emb = embed_texts_llm([query])

            dense_vector = query_emb[0].tolist()



            from app.rag.sparse_embed import embed_sparse

            sparse_result = embed_sparse([query])

            sparse_vector = _to_sparse_vector(sparse_result[0]) if sparse_result else _to_sparse_vector(None)

    except Exception as e:

        logger.warning("hybrid_search_qdrant embedding failed, falling back to BM25-only: %s", e)

        # TODO(E19): 迁移到 Qdrant 稀疏向量后移除此 BM25 调用
        return retrieve_keyword(query, top_k=top_k, lang_filter=lang_filter, tenant_id=tenant_id)



    # 2. ���� filter

    conditions = []

    if lang_filter:

        conditions.append(qmodels.FieldCondition(

            key="metadata.language",

            match=qmodels.MatchValue(value=lang_filter),

        ))

    if tenant_id and tenant_id != "default":

        conditions.append(qmodels.FieldCondition(

            key="metadata.tenant_id",

            match=qmodels.MatchValue(value=tenant_id),

        ))

    query_filter = qmodels.Filter(must=conditions) if conditions else None



    # 3. Qdrant Query API: prefetch dense + sparse, RRF fusion
    # 候选池 top_k * 5（top_k=12 → fetch_limit=60），平衡 Recall 和 Relevancy
    _candidate_multiplier = 5
    fetch_limit = top_k * _candidate_multiplier

    prefetch = [
        qmodels.Prefetch(
            query=dense_vector,
            using="dense",
            limit=fetch_limit * 10,  # 扩大候选池提升 Recall
            filter=query_filter,
        ),
    ]

    if sparse_vector:
        prefetch.append(qmodels.Prefetch(
            query=sparse_vector,
            using="sparse",
            limit=fetch_limit * 10,  # 扩大候选池提升 Recall
            filter=query_filter,
        ))

    results = client.query_points(
        collection_name=collection_name,
        prefetch=prefetch,
        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),
        limit=fetch_limit,
        search_params=qmodels.SearchParams(
            hnsw_ef=settings.hnsw_ef_search,
            quantization=qmodels.QuantizationSearchParams(rescore=True),

        ),

    )



    # 4. 格式化结果
    # 保存 query embedding 到 chunks（供 compress_context 复用，避免重复 API 调用）
    formatted = []
    _query_emb_array = np.array(query_emb[0], dtype=np.float32) if query_emb is not None else None
    for point in results.points:
        payload = point.payload or {}
        payload_meta = payload.get("metadata", {})
        # Parent-Child chunking: use parent_text for richer context if available
        parent_text = payload_meta.get("parent_text", "")
        display_text = parent_text if parent_text else payload.get("text", "")
        chunk = {
            "id": str(point.id),
            "text": display_text,
            "metadata": payload_meta,
            "score": point.score,
        }
        # 附加 query embedding 供下游复用
        if _query_emb_array is not None:
            chunk["_query_embedding"] = _query_emb_array
        formatted.append(chunk)

    try:
        keyword_results = retrieve_keyword(
            query,
            top_k=fetch_limit,
            lang_filter=lang_filter,
            tenant_id=tenant_id,
        )
    except Exception as e:
        logger.warning("Qdrant hybrid BM25 merge failed, using vector candidates only: %s", e)
        keyword_results = []

    strong_keyword_results = [
        doc for doc in keyword_results
        if doc.get("score", 0) >= 0.8
    ]

    def _candidate_key(doc):
        meta = doc.get("metadata", {})
        return meta.get("slug") or meta.get("source") or doc.get("text", "")[:80]

    def _prepend_strong_keyword_hits(results):
        if not strong_keyword_results:
            return results[:top_k]
        merged_results = []
        seen_keys = set()
        for doc in [*strong_keyword_results, *results]:
            key = _candidate_key(doc)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            merged_results.append(doc)
            if len(merged_results) >= top_k:
                break
        return merged_results

    if keyword_results:
        merged = []
        seen = set()

        for doc in [*keyword_results, *formatted]:
            key = _candidate_key(doc)
            if key in seen:
                continue
            seen.add(key)
            if _query_emb_array is not None and "_query_embedding" not in doc:
                doc = {**doc, "_query_embedding": _query_emb_array}
            merged.append(doc)
        formatted = merged

    # 5. Rerank: 对 Qdrant RRF 候选做 API rerank 精排，提升 Recall 和 Relevancy
    # 参考 Anthropic Contextual Retrieval 论文：rerank 后取 top-20 比 top-10/5 更有效
    logger.info("Qdrant hybrid: %d RRF candidates, top_k=%d, rerank_enabled=%s",
                len(formatted), top_k, settings.rerank_enabled)
    if settings.rerank_enabled and len(formatted) > top_k:
        try:
            from app.rag.reranker import rerank as do_rerank
            # R18: 回到 R10 的 rerank_top = top_k * 5（P0 的 top-20 导致 Contextual Relevancy/Recall 退化）
            rerank_top = min(len(formatted), top_k * 5)
            reranked = do_rerank(query, formatted, top_k=rerank_top)
            if reranked:
                # R19: 动态 rerank 阈值——根据查询复杂度调整
                # 简单查询：0.55（R10 最佳配置）
                # 中等查询：0.40（中等复杂度查询 rerank score 普遍偏低）
                # 复杂查询：0.30（复杂查询 rerank score 更低，0.55 会过滤掉所有结果）
                _RERANK_THRESHOLDS = {"simple": 0.55, "medium": 0.40, "complex": 0.30}
                _RERANK_SCORE_THRESHOLD = _RERANK_THRESHOLDS.get(query_complexity, 0.55)
                filtered = [c for c in reranked if c.get("rerank_score", 0) >= _RERANK_SCORE_THRESHOLD]
                if filtered:
                    logger.info("Qdrant hybrid rerank (%s): %d/%d passed threshold (>=%.2f), returning top %d",
                                query_complexity, len(filtered), len(reranked), _RERANK_SCORE_THRESHOLD, top_k)
                    return _prepend_strong_keyword_hits(filtered)
                else:
                    # 所有 rerank score < 阈值，返回 rerank top-K（避免空结果）
                    logger.warning("Qdrant hybrid rerank (%s): 0/%d passed threshold (>=%.2f), returning rerank top-%d",
                                   query_complexity, len(reranked), _RERANK_SCORE_THRESHOLD, top_k)
                    return _prepend_strong_keyword_hits(reranked)
            else:
                logger.warning("Qdrant hybrid rerank returned None, using RRF results")
        except Exception as e:
            logger.warning("Qdrant hybrid rerank failed, using RRF results: %s", e)
    else:
        if not settings.rerank_enabled:
            logger.info("Qdrant hybrid: rerank disabled, returning top %d RRF results", top_k)
        elif len(formatted) <= top_k:
            logger.info("Qdrant hybrid: only %d candidates (<=top_k=%d), skipping rerank", len(formatted), top_k)

    return formatted[:top_k]




def retrieve_qdrant(query: str, top_k: int = 3, collection_name: str = "aureon", tenant_id: str = None, lang_filter: str = None) -> List[Dict]:

    """Retrieve from Qdrant vector store.



    Supports both old (search) and new (query_points) qdrant_client APIs.

    Supports payload filtering via Qdrant Filter (e.g. lang_filter, tenant_id).

    Supports parent_text: if parent_text exists in metadata, use it as display text.



    Args:

        query: ��ѯ�ı�

        top_k: ���ؽ������

        collection_name: Qdrant collection ����

        tenant_id: �⻧ ID��Ĭ�ϴ������Ļ�ȡ��

        lang_filter: ���Թ��ˣ�"zh" �� "en"����None ��ʾ������

    """

    from app.rag.embedding import (

        embed_texts_llm,

    )



    client = _get_qdrant()



    # Get tenant_id from context if not provided

    if tenant_id is None:

        tenant_id = get_current_tenant_id()



    try:

        query_emb = embed_texts_llm([query])

    except Exception as e:

        logger.error("Embedding failed for query: %s", e)

        raise



    query_vector = query_emb[0].tolist()







    # Check if stored data actually has tenant_id — skip filter if not
    # 缓存结果 5 分钟，避免每次查询都 scroll
    _has_tenant_id = False
    now = time.time()
    if (now - _tenant_id_cache["updated_at"]) < _TENANT_ID_CACHE_TTL and _tenant_id_cache["value"] is not None:
        _has_tenant_id = _tenant_id_cache["value"]
    else:
        try:
            _sample, _ = client.scroll(
                collection_name=collection_name, limit=1,
                with_payload=True, with_vectors=False,
            )
            if _sample:
                _sample_meta = _sample[0].payload.get("metadata", {}) if _sample[0].payload else {}
                _has_tenant_id = "tenant_id" in _sample_meta
            _tenant_id_cache["value"] = _has_tenant_id
            _tenant_id_cache["updated_at"] = now
        except Exception as e:
            logger.debug("tenant_id_cache_check_failed", error=str(e))



    # Build Qdrant filter conditions (tenant + lang_filter)

    from qdrant_client.models import Filter, FieldCondition, MatchValue

    must_conditions = []

    if tenant_id and _has_tenant_id:

        must_conditions.append(

            FieldCondition(

                key="metadata.tenant_id",

                match=MatchValue(value=tenant_id),

            )

        )

    if lang_filter:

        must_conditions.append(

            FieldCondition(

                key="metadata.language",

                match=MatchValue(value=lang_filter),

            )

        )

    query_filter = Filter(must=must_conditions) if must_conditions else None



    # Try new API first (qdrant_client >= 1.12), fall back to old

    from qdrant_client import models as qmodels

    _search_params = qmodels.SearchParams(

        hnsw_ef=settings.hnsw_ef_search,

        quantization=qmodels.QuantizationSearchParams(rescore=True),

    )

    try:

        search_kwargs = dict(

            collection_name=collection_name,

            query=query_vector,

            limit=top_k,

            with_payload=True,

            with_vectors=True,

            search_params=_search_params,

        )

        if query_filter is not None:

            search_kwargs["query_filter"] = query_filter

        response = client.query_points(**search_kwargs)

        results = response.points

    except (AttributeError, TypeError):

        # Old API fallback

        search_kwargs = dict(

            collection_name=collection_name,

            query_vector=query_vector,

            limit=top_k,

            with_vectors=True,

            search_params=_search_params,

        )

        if query_filter is not None:

            search_kwargs["filter"] = query_filter

        results = client.search(**search_kwargs)



    items = []

    for r in results:

        payload_meta = r.payload.get("metadata", {})



        # Parent-Child chunking: use parent_text for richer context if available

        parent_text = payload_meta.get("parent_text", "")

        if parent_text:

            display_text = parent_text

        else:

            display_text = r.payload.get("text", "")



        item = {

            "text": display_text,

            "metadata": {**payload_meta, "cosine_score": r.score},

            "score": r.score,

        }

        # Attach stored embedding for reuse (avoids recomputation in compress_context)

        try:

            if hasattr(r, 'vector') and r.vector is not None:

                emb = np.array(r.vector, dtype=np.float32)

                if np.linalg.norm(emb) > 1e-6:

                    item["_embedding"] = emb

        except Exception as e:

            logger.debug("embedding_attach_failed", error=str(e))

        # ���� query embedding���� compress_context ���ã����Ⲣ����̬��

        item["_query_embedding"] = query_emb[0]

        items.append(item)

    return items

