# -*- coding: utf-8 -*-

"""Qdrant vector store operations for RAG system.



Qdrant client management, index saving, hybrid search, and retrieval.

Extracted from vector_store.py.

"""



import time

import numpy as np

from typing import List, Dict



import structlog

from app.config import settings

from app.multi_tenant.middleware import get_current_tenant_id



logger = structlog.get_logger()



# ���� Qdrant Backend ����

_qdrant_client = None

_qdrant_available = False  # Global flag: True if Qdrant is reachable





def _get_qdrant():

    """Get or create Qdrant client singleton.



    Auto-detects mode from URL scheme:

    - https:// �� Qdrant Cloud (REST only, no gRPC)

    - http://localhost �� local Qdrant (gRPC preferred)

    """

    global _qdrant_client

    if _qdrant_client is None:

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



    ��������Ѵ���������ƥ�䣬ֱ�� upsert ���ǣ����� delete_collection ����

    �ؽ��ж�ʱ���ݶ�ʧ����ֻ�����ò�ƥ��ʱ��ɾ���ؽ���

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

    except Exception:

        pass



    # ֻ�����ò�ƥ��ʱɾ���ؽ�������ƥ��ʱֱ�� upsert ����

    if collection_exists and config_matches:

        logger.info("Collection '%s' exists with matching config, upserting %d chunks", collection_name, len(chunks))

    else:

        if collection_exists:

            logger.info("Collection '%s' config mismatch, deleting and recreating", collection_name)

        try:

            client.delete_collection(collection_name)

        except Exception:

            pass



    # �����Ƿ����� sparse ����ѡ�� vectors_config

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

            except Exception:

                pass  # ���������Ѵ���



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

        and True

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



            if True:  # API-only

                batch_embeddings = embed_texts_llm(batch_texts)

            else:

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





def hybrid_search_qdrant(

    query: str,

    top_k: int = 5,

    collection_name: str = "aureon",

    tenant_id: str = None,

    lang_filter: str = None,

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

            sparse_vector = sparse_results[0] if sparse_results else _to_sparse_vector(None)

            if not isinstance(sparse_vector, type(None)):

                sparse_vector = _to_sparse_vector(sparse_vector)

        else:

            query_emb = embed_texts_llm([query])

            dense_vector = query_emb[0].tolist()



            from app.rag.sparse_embed import embed_sparse

            sparse_result = embed_sparse([query])

            sparse_vector = _to_sparse_vector(sparse_result[0]) if sparse_result else _to_sparse_vector(None)

    except Exception as e:

        logger.warning("hybrid_search_qdrant embedding failed, falling back to BM25-only: %s", e)

        return retrieve_keyword(query, top_k=top_k, lang_filter=lang_filter)



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

    prefetch = [

        qmodels.Prefetch(

            query=dense_vector,

            using="dense",

            limit=top_k * 3,

            filter=query_filter,

        ),

    ]

    if sparse_vector:

        prefetch.append(qmodels.Prefetch(

            query=sparse_vector,

            using="sparse",

            limit=top_k * 3,

            filter=query_filter,

        ))



    results = client.query_points(

        collection_name=collection_name,

        prefetch=prefetch,

        query=qmodels.FusionQuery(fusion=qmodels.Fusion.RRF),

        limit=top_k,

        search_params=qmodels.SearchParams(

            hnsw_ef=settings.hnsw_ef_search,

            quantization=qmodels.QuantizationSearchParams(rescore=True),

        ),

    )



    # 4. ��ʽ�����

    formatted = []

    for point in results.points:

        payload = point.payload or {}

        formatted.append({

            "id": str(point.id),

            "text": payload.get("text", ""),

            "metadata": payload.get("metadata", {}),

            "score": point.score,

        })

    return formatted





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

        embed_texts_llm, _set_thread_query_embedding,

    )



    client = _get_qdrant()



    # Get tenant_id from context if not provided

    if tenant_id is None:

        tenant_id = get_current_tenant_id()



    try:

        query_emb = embed_texts_llm([query])

    except Exception as e:

        logger.warning("Adaptive embedding failed: %s, falling back to API", e)

        query_emb = embed_texts_llm([query])



    query_vector = query_emb[0].tolist()



    # deprecated: ȫ�ֱ������ݣ����ڲ�����̬������ʹ�� _query_embedding �ֶ�

    _set_thread_query_embedding(query_emb[0])



    # Check if stored data actually has tenant_id �� skip filter if not

    _has_tenant_id = False

    try:

        _sample, _ = client.scroll(

            collection_name=collection_name, limit=1,

            with_payload=True, with_vectors=False,

        )

        if _sample:

            _sample_meta = _sample[0].payload.get("metadata", {}) if _sample[0].payload else {}

            _has_tenant_id = "tenant_id" in _sample_meta

    except Exception:

        pass



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

        except Exception:

            pass

        # ���� query embedding���� compress_context ���ã����Ⲣ����̬��

        item["_query_embedding"] = query_emb[0]

        items.append(item)

    return items

