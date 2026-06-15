# -*- coding: utf-8 -*-

"""Index management for RAG system.



Index CRUD, stats, health checks, format helpers, and Elasticsearch BM25 backend.

Extracted from vector_store.py.

"""




import numpy as np

from typing import List, Dict, Any



import structlog

from app.config import settings



logger = structlog.get_logger()



# ���� Stats cache (avoid full-scan on every health check) ����

_stats_cache: dict = {"doc_count": 0, "chunk_count": 0, "updated_at": 0.0}
_STATS_CACHE_TTL = max(settings.stats_cache_ttl, 300)  # 至少 5 分钟，避免频繁全量滚动

# 索引来源缓存（get_indexed_sources 全量滚动代价高，缓存 5 分钟）
_sources_cache: dict = {"sources": set(), "updated_at": 0.0}
_SOURCES_CACHE_TTL = 300



# ���� Public API ����



def _invalidate_stats_cache():

    """Invalidate stats and sources cache after index changes."""

    _stats_cache["updated_at"] = 0.0
    _sources_cache["updated_at"] = 0.0





def add_to_index(chunks: List[Dict[str, Any]], path: str = None):

    """Add chunks to an EXISTING Qdrant collection (incremental)."""

    return _add_to_index_qdrant(chunks)





def _add_to_index_qdrant(chunks: List[Dict[str, Any]]):

    """Qdrant: add chunks incrementally."""

    from qdrant_client.models import PointStruct

    from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name

    from app.rag.embedding import (

        _to_sparse_vector, _embed_dense_sparse_dashscope,

        embed_texts_llm,

    )

    from app.rag.bm25 import _build_kw_index



    client = _get_qdrant()

    collection_name = _get_qdrant_collection_name()



    # Get current max ID to avoid collisions

    try:

        info = client.get_collection(collection_name)

        existing_count = info.points_count or 0

    except Exception:

        existing_count = 0



    # Embed texts �� ����ʹ�� DashScope combined API��dense+sparse һ�ε��ã�

    texts = [c["text"] for c in chunks]



    use_combined = (

        settings.sparse_enabled

        and settings.dashscope_api_key

        and "dashscope" in settings.dashscope_base_url.lower()

    )



    if use_combined:

        dense_emb, sparse_vecs = _embed_dense_sparse_dashscope(texts)

    else:
        dense_emb = embed_texts_llm(texts)
        from app.rag.sparse_embed import embed_sparse
        sparse_vecs = embed_sparse(texts) if settings.sparse_enabled else [None] * len(texts)



    # Upsert in batches

    batch_size = 100

    for start in range(0, len(chunks), batch_size):

        end = min(start + batch_size, len(chunks))

        points = []

        for i in range(end - start):

            idx = start + i

            if settings.sparse_enabled and sparse_vecs[idx] is not None:

                sv = _to_sparse_vector(sparse_vecs[idx])

                vector_data = {"dense": dense_emb[idx].tolist(), "sparse": sv}

            else:

                vector_data = dense_emb[idx].tolist()

            points.append(PointStruct(

                id=existing_count + idx,

                vector=vector_data,

                payload={"metadata": chunks[idx].get("metadata", {}), "text": chunks[idx]["text"]},

            ))

        client.upsert(collection_name=collection_name, points=points)



    logger.info("Added %d chunks to Qdrant ('%s')", len(chunks), collection_name)

    if not settings.sparse_enabled:

        _build_kw_index(force=True)

    _invalidate_stats_cache()





def delete_from_index(source_filename: str, path: str = None):

    """Delete all chunks whose metadata.source == source_filename from Qdrant."""

    return _delete_from_index_qdrant(source_filename)





def _delete_from_index_qdrant(source_filename: str):

    """Qdrant: delete chunks by source filename.



    Qdrant doesn't support conditional delete by payload field directly,

    so we scroll to find matching point IDs, then delete them.

    """

    from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name

    from app.rag.bm25 import _build_kw_index



    client = _get_qdrant()

    collection_name = _get_qdrant_collection_name()



    try:

        info = client.get_collection(collection_name)

        if (info.points_count or 0) == 0:

            return

    except Exception as e:

        logger.warning("Cannot open Qdrant for delete: %s", e)

        return



    # Scroll to find points with matching source

    ids_to_delete = []

    offset = None

    while True:

        points, offset = client.scroll(

            collection_name=collection_name,

            limit=100,

            offset=offset,

            with_payload=True,

            with_vectors=False,

        )

        for pt in points:

            meta = pt.payload.get("metadata", {}) if pt.payload else {}

            if meta.get("source") == source_filename:

                ids_to_delete.append(pt.id)

        if offset is None:

            break



    if ids_to_delete:

        client.delete(

            collection_name=collection_name,

            points_selector=ids_to_delete,

        )



    safe_name = source_filename.encode("ascii", errors="replace").decode("ascii")

    logger.info("Deleted %d chunks for '%s' from Qdrant ('%s')", len(ids_to_delete), safe_name, collection_name)

    if not settings.sparse_enabled:

        _build_kw_index(force=True)

    _invalidate_stats_cache()





def save_index(chunks: List[Dict[str, Any]], embeddings: np.ndarray = None, path: str = None):

    """Save chunks to Qdrant vector storage (embeddings computed automatically)."""

    from app.config import settings

    if settings.bm25_backend == "elasticsearch":

        return save_index_es(chunks)

    from app.rag.qdrant_ops import save_index_qdrant

    return save_index_qdrant(chunks)





def load_index(path: str = None):

    """Check if Qdrant collection exists and has data."""

    from app.config import settings

    from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name

    try:

        if settings.vector_backend == "qdrant":

            client = _get_qdrant()

            collection_name = _get_qdrant_collection_name()

            info = client.get_collection(collection_name)

            count = info.points_count or 0

        else:

            return None, None

        if count > 0:

            return [], np.array([])

        return None, None

    except Exception:

        return None, None





def retrieve(query: str, top_k: int = 3, use_mmr: bool = True, lang_filter: str = None, tenant_id: str = None) -> List[Dict[str, Any]]:

    """Retrieve top_k chunks using vector similarity search.



    Args:

        query: ��ѯ�ı�

        top_k: ���ؽ������

        use_mmr: �Ƿ�ʹ�� MMR �������Ż�

        lang_filter: ���Թ��ˣ�"zh" �� "en"����None ��ʾ������

        tenant_id: �⻧ ID��Ĭ�ϴ������Ļ�ȡ��

    """

    from app.rag.qdrant_ops import retrieve_qdrant

    return retrieve_qdrant(query, top_k=top_k, tenant_id=tenant_id, lang_filter=lang_filter)





def _simple_diversity(items: list, top_k: int) -> list:

    """Lightweight diversity: prefer unique sources, fill with best scores.



    No embedding API calls.

    """

    seen_sources = set()

    diverse = []

    # Pass 1: best item per unique source

    for item in sorted(items, key=lambda x: x["score"], reverse=True):

        src = item["metadata"].get("source", item["metadata"].get("title", ""))

        if src not in seen_sources:

            diverse.append(item)

            seen_sources.add(src)

            if len(diverse) >= top_k:

                return diverse

    # Pass 2: fill remaining from unused items by score

    remaining = [it for it in items if it not in diverse]

    diverse.extend(remaining[:top_k - len(diverse)])

    return diverse





def format_context(chunks: List[Dict[str, Any]]) -> str:

    """Format retrieved chunks into context string.



    Uses parent_text when available (Parent-Child chunking) for richer context.

    Deduplicates by parent to avoid repeating the same parent text.

    """

    parts = []

    seen_parents = set()

    for i, chunk in enumerate(chunks):

        source = chunk["metadata"].get("title", chunk["metadata"].get("source", "Unknown"))

        # Prefer parent_text for richer context (Parent-Child chunking)

        parent_text = chunk.get("metadata", {}).get("parent_text")

        parent_idx = chunk.get("metadata", {}).get("parent_idx")

        parent_key = f"{source}:{parent_idx}"



        if parent_text and parent_key not in seen_parents:

            seen_parents.add(parent_key)

            parts.append(f"[Source {len(parts)+1}: {source}]\n{parent_text}")

        elif not parent_text:

            # Fallback: use child text (legacy chunks without parent)

            parts.append(f"[Source {len(parts)+1}: {source}]\n{chunk['text']}")

    return "\n\n".join(parts)





def get_collection_stats() -> tuple[int, int]:

    """Return (total_docs, total_chunks) from Qdrant.



    Counts unique source documents and total chunks.

    Returns (0, 0) if collection is empty or unavailable.

    Results are cached for STATS_CACHE_TTL seconds (default 60s).

    """

    import time as _time

    now = _time.time()

    if (now - _stats_cache["updated_at"]) < _STATS_CACHE_TTL:

        return _stats_cache["doc_count"], _stats_cache["chunk_count"]



    try:

        return _get_collection_stats_qdrant(now)

    except Exception:

        return _stats_cache["doc_count"], _stats_cache["chunk_count"]





def _get_collection_stats_qdrant(now: float) -> tuple[int, int]:

    """Qdrant stats implementation."""

    from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name



    client = _get_qdrant()

    collection_name = _get_qdrant_collection_name()

    try:

        info = client.get_collection(collection_name)

        total_chunks = info.points_count or 0

    except Exception:

        return _stats_cache["doc_count"], _stats_cache["chunk_count"]



    if total_chunks > 0:

        # Scroll through points to count unique sources

        unique_docs = set()

        offset = None

        while True:

            points, offset = client.scroll(

                collection_name=collection_name,

                limit=100,

                offset=offset,

                with_payload=True,

                with_vectors=False,

            )

            for pt in points:

                meta = pt.payload.get("metadata", {}) if pt.payload else {}

                src = meta.get("source") or meta.get("title", "unknown")

                unique_docs.add(src)

            if offset is None:

                break

        _stats_cache["doc_count"] = len(unique_docs)

        _stats_cache["chunk_count"] = total_chunks

        _stats_cache["updated_at"] = now

        return len(unique_docs), total_chunks



    _stats_cache["doc_count"] = 0

    _stats_cache["chunk_count"] = 0

    _stats_cache["updated_at"] = now

    return 0, 0





def get_indexed_sources() -> set:

    """Return set of source filenames currently in Qdrant.

    Results are cached for _SOURCES_CACHE_TTL seconds (default 300s).
    Full scroll is expensive for large collections, so we cache aggressively.
    """
    import time as _time
    now = _time.time()
    if (now - _sources_cache["updated_at"]) < _SOURCES_CACHE_TTL:
        return _sources_cache["sources"].copy()

    try:
        sources = _get_indexed_sources_qdrant()
        _sources_cache["sources"] = sources
        _sources_cache["updated_at"] = now
        return sources.copy()
    except Exception:
        return _sources_cache["sources"].copy()





def _get_indexed_sources_qdrant() -> set:

    """Qdrant: get indexed source filenames."""

    from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name



    client = _get_qdrant()

    collection_name = _get_qdrant_collection_name()

    try:

        info = client.get_collection(collection_name)

        if (info.points_count or 0) == 0:

            return set()

    except Exception:

        return set()



    sources = set()

    offset = None

    while True:

        points, offset = client.scroll(

            collection_name=collection_name,

            limit=100,

            offset=offset,

            with_payload=True,

            with_vectors=False,

        )

        for pt in points:

            meta = pt.payload.get("metadata", {}) if pt.payload else {}

            src = meta.get("source")

            if src:

                sources.add(src)

        if offset is None:

            break

    return sources





def check_index_stale(articles_dir: str) -> dict:

    """Check if the article files on disk are out of sync with the Qdrant index.



    Returns:

        {"stale": bool, "reason": str, "fs_count": int, "idx_count": int,

         "missing_files": list[str], "extra_files": list[str]}

    """

    import pathlib



    result = {

        "stale": False,

        "reason": "",

        "fs_count": 0,

        "idx_count": 0,

        "missing_files": [],

        "extra_files": [],

    }



    try:

        # Collect all .md files on disk

        articles_path = pathlib.Path(articles_dir)

        if not articles_path.is_dir():

            result["stale"] = True

            result["reason"] = "articles directory not found"

            return result



        fs_files = sorted(str(p.relative_to(articles_path))

                          for p in articles_path.rglob("*.md"))

        result["fs_count"] = len(fs_files)



        indexed = get_indexed_sources()

        result["idx_count"] = len(indexed)



        # No files but index has data �� stale (files were deleted)

        if len(fs_files) == 0 and len(indexed) > 0:

            result["stale"] = True

            result["reason"] = "no articles on disk but index has data"

            return result



        # Files exist but index is empty �� stale

        if len(fs_files) > 0 and len(indexed) == 0:

            result["stale"] = True

            result["reason"] = f"{len(fs_files)} articles found but index is empty"

            return result



        # Files exist but index is empty

        if len(fs_files) == 0 and len(indexed) == 0:

            return result  # both empty, not stale



        # Simple comparison: file count vs indexed doc count

        # Path matching is unreliable across platforms; count-based check is sufficient

        if len(indexed) < len(fs_files):

            result["stale"] = True

            result["reason"] = f"{len(fs_files)} articles on disk but only {len(indexed)} indexed"

        elif len(indexed) > len(fs_files):

            result["stale"] = True

            result["reason"] = f"{len(indexed)} indexed entries but only {len(fs_files)} articles on disk"



        return result

    except Exception as e:

        logger.warning("check_index_stale failed: %s", e)

        result["stale"] = True

        result["reason"] = f"check failed: {e}"

        return result





def _check_qdrant_available() -> bool:

    """Check if Qdrant server is reachable. Caches result in _qdrant_available."""

    from app.rag import qdrant_ops

    try:

        client = qdrant_ops._get_qdrant()

        client.get_collections()  # lightweight health check

        qdrant_ops._qdrant_available = True

        return True

    except Exception:

        qdrant_ops._qdrant_available = False

        return False





def ensure_payload_indexes(collection_name: str = "aureon") -> None:

    """ȷ�� Qdrant collection �ϴ��ڱ���� Payload ������



    ���������� collection ������ Payload ������������֮ǰ���Ѵ�����

    �˺�����鲢Ϊȱʧ���ֶβ��� KEYWORD �����������ؽ� collection��

    """

    from qdrant_client import models as qmodels

    from app.rag.qdrant_ops import _get_qdrant

    try:

        client = _get_qdrant()

        # ��� collection �Ƿ����

        try:

            client.get_collection(collection_name)

        except Exception:

            logger.debug("Collection %s does not exist, skipping payload index check", collection_name)

            return



        required_fields = ["metadata.slug", "metadata.language", "metadata.source", "metadata.tenant_id"]

        for field_name in required_fields:

            # Qdrant create_payload_index ���ݵȵ� �� �����Ѵ���ʱ���� 400��

            # ͨ�������쳣�������Ѵ��ڵ�����

            try:

                client.create_payload_index(

                    collection_name=collection_name,

                    field_name=field_name,

                    field_schema=qmodels.PayloadSchemaType.KEYWORD,

                )

                logger.info("Created payload index for '%s' on collection '%s'", field_name, collection_name)

            except Exception as e:

                logger.debug("Payload index for '%s' already exists: %s", field_name, e)

    except Exception as e:

        logger.warning("Failed to ensure payload indexes: %s", e)





def check_vector_config_mismatch(collection_name: str = "aureon") -> bool:

    """������� collection �����������Ƿ��뵱ǰ����ƥ�䡣



    ���ά�ȣ�

    1. ����������ʽ������ "dense"/"sparse" vs δ������

    2. Dense ����ά���Ƿ��� settings.embedding_dim һ��

    3. ��������Ƿ�Ϊ COSINE



    Returns:

        True if config mismatch detected (needs rebuild), False if match.

    """

    from app.rag.qdrant_ops import _get_qdrant

    from app.rag.embedding import _get_embedding_dim



    try:

        client = _get_qdrant()

        info = client.get_collection(collection_name)

        vectors_config = info.config.params.vectors

        dim = _get_embedding_dim()



        if settings.sparse_enabled:

            # ������������ "dense" + "sparse"

            if not isinstance(vectors_config, dict) or "dense" not in vectors_config:

                logger.warning(

                    "Vector config mismatch: sparse_enabled=True but collection '%s' "

                    "has unnamed vectors (expected named 'dense'/'sparse'). Rebuild needed.",

                    collection_name,

                )

                return True

            # ��� dense ����ά��

            dense_cfg = vectors_config.get("dense")

            if hasattr(dense_cfg, "size") and dense_cfg.size != dim:

                logger.warning(

                    "Vector dim mismatch: collection has %dd but settings require %dd. Rebuild needed.",

                    dense_cfg.size, dim,

                )

                return True

            # ���������

            from qdrant_client.models import Distance

            if hasattr(dense_cfg, "distance") and dense_cfg.distance != Distance.COSINE:

                logger.warning(

                    "Distance metric mismatch: collection has %s but COSINE required. Rebuild needed.",

                    dense_cfg.distance,

                )

                return True

            return False

        else:

            # ����δ�������������� VectorParams��

            if isinstance(vectors_config, dict):

                logger.warning(

                    "Vector config mismatch: sparse_enabled=False but collection '%s' "

                    "has named vectors. Rebuild needed.",

                    collection_name,

                )

                return True

            # ���ά�Ⱥ;���

            if hasattr(vectors_config, "size") and vectors_config.size != dim:

                logger.warning(

                    "Vector dim mismatch: collection has %dd but settings require %dd. Rebuild needed.",

                    vectors_config.size, dim,

                )

                return True

            from qdrant_client.models import Distance

            if hasattr(vectors_config, "distance") and vectors_config.distance != Distance.COSINE:

                logger.warning(

                    "Distance metric mismatch: collection has %s but COSINE required. Rebuild needed.",

                    vectors_config.distance,

                )

                return True

            return False

    except Exception as e:

        logger.warning("check_vector_config_mismatch failed: %s", e)

        return False  # �޷��ж�ʱ���ش���





def get_index_config(collection_name: str = "aureon") -> dict | None:

    """�� Qdrant ���ϵĵ�һ�� point �ж�ȡ _index_config Ԫ���ݡ�



    Returns:

        ���������ֵ䣬���� embedding_dim, embedding_model, sparse_enabled, created_at��

        �������Ϊ�ջ�û�� _index_config������ None��

    """

    from app.rag.qdrant_ops import _get_qdrant

    try:

        client = _get_qdrant()

        points, _ = client.scroll(

            collection_name=collection_name,

            limit=1,

            with_payload=True,

            with_vectors=False,

        )

        if points:

            return points[0].payload.get("_index_config")

    except Exception as e:

        logger.debug("get_index_config failed: %s", e)

    return None





def check_index_upgrade_strategy(collection_name: str = "aureon", articles_dir: str = "") -> dict:

    """���������Ƿ���Ҫ���£��Լ���Ҫȫ���ؽ������������¡�



    ���ԣ�

    1. �����ṹ�����ݣ�������ʽ/ά��/������ˣ��� ����ȫ���ؽ�

    2. �����ṹ���ݵ��ļ����ݱ��� �� �������£�ֻ��������/ɾ�����ļ���

    3. �����ṹ�������ļ�û�� �� ����



    Returns:

        {

            "action": "skip" | "rebuild" | "incremental",

            "reason": str,

            "files_to_add": list[str],   # incremental ʱ��Ҫ�������ļ�

            "files_to_del": list[str],   # incremental ʱ��Ҫɾ�����ļ�

        }

    """

    import pathlib



    # 1. ��������ṹ������

    if check_vector_config_mismatch(collection_name):

        return {

            "action": "rebuild",

            "reason": "vector config mismatch (structure/dim/distance incompatible)",

            "files_to_add": [],

            "files_to_del": [],

        }



    # 2. ��� _index_config �е� embedding ģ���Ƿ�仯

    current_model = settings.dashscope_model

    idx_cfg = get_index_config(collection_name)

    if idx_cfg:


        stored_model = idx_cfg.get("embedding_model", "")

        if stored_model and stored_model != current_model:

            return {

                "action": "rebuild",

                "reason": f"embedding model changed: {stored_model} -> {current_model}",

                "files_to_add": [],

                "files_to_del": [],

            }



    # 3. �Ա��ļ�ϵͳ�������е� source �б�

    indexed_sources = get_indexed_sources()

    doc_count, _ = get_collection_stats()



    if not articles_dir:

        # û�� articles_dir ��Ϣ��ֻ�������ж�

        if doc_count > 0:

            return {"action": "skip", "reason": "index has data, no articles_dir to compare", "files_to_add": [], "files_to_del": []}

        return {"action": "rebuild", "reason": "empty index", "files_to_add": [], "files_to_del": []}



    articles_path = pathlib.Path(articles_dir)

    if not articles_path.is_dir():

        if doc_count > 0:

            return {"action": "skip", "reason": "articles dir missing but index has data", "files_to_add": [], "files_to_del": []}

        return {"action": "rebuild", "reason": "no articles dir and empty index", "files_to_add": [], "files_to_del": []}



    # �ռ������ϵ� .md �ļ���ʹ���ļ������� metadata.source ��ʽһ�£�

    # metadata.source ����� fpath.name�����ļ���������������Ҳ�ô��ļ���

    fs_files = set(p.name for p in articles_path.rglob("*.md"))



    # �������

    files_to_add = sorted(fs_files - indexed_sources)

    files_to_del = sorted(indexed_sources - fs_files)



    if not files_to_add and not files_to_del:

        return {"action": "skip", "reason": "index up-to-date", "files_to_add": [], "files_to_del": []}



    # ������쳬�� 50%��ȫ���ؽ�����Ч

    total = max(len(fs_files), len(indexed_sources), 1)

    diff_ratio = (len(files_to_add) + len(files_to_del)) / total

    if diff_ratio > 0.5:

        return {

            "action": "rebuild",

            "reason": f"too many changes ({len(files_to_add)} add, {len(files_to_del)} del, {diff_ratio:.0%} diff)",

            "files_to_add": files_to_add,

            "files_to_del": files_to_del,

        }



    return {

        "action": "incremental",

        "reason": f"{len(files_to_add)} new, {len(files_to_del)} removed files",

        "files_to_add": files_to_add,

        "files_to_del": files_to_del,

    }





# ���� Elasticsearch BM25 Backend ����

_es_client = None





def _get_es():

    """Get or create Elasticsearch client singleton."""

    global _es_client

    if _es_client is None:

        from elasticsearch import Elasticsearch

        from app.config import settings

        kwargs = {}

        if settings.es_password:

            kwargs["basic_auth"] = ("elastic", settings.es_password)

        _es_client = Elasticsearch(settings.es_url, **kwargs)

    return _es_client





def save_index_es(chunks: List[Dict], index_name: str = None):

    """Index chunks into Elasticsearch for BM25 retrieval."""

    from app.config import settings

    index_name = index_name or settings.es_index

    es = _get_es()



    if es.indices.exists(index=index_name):

        es.indices.delete(index=index_name)



    es.indices.create(index=index_name, body={

        "settings": {"analysis": {"analyzer": {"default": {"type": "standard"}}}},

        "mappings": {"properties": {

            "text": {"type": "text"},

            "slug": {"type": "keyword"},

            "title": {"type": "text"},

            "parent_text": {"type": "text"},

        }}

    })



    for i, chunk in enumerate(chunks):

        meta = chunk.get("metadata", {})

        es.index(index=index_name, id=i, body={

            "text": chunk["text"],

            "slug": meta.get("slug", ""),

            "title": meta.get("title", ""),

            "parent_text": meta.get("parent_text", ""),

        })



    es.indices.refresh(index=index_name)

    logger.info("ES: indexed %d chunks into '%s'", len(chunks), index_name)





def retrieve_keyword_es(query: str, top_k: int = 20, index_name: str = None) -> List[Dict]:

    """BM25 retrieval via Elasticsearch."""

    from app.config import settings

    index_name = index_name or settings.es_index

    es = _get_es()



    results = es.search(index=index_name, body={

        "query": {"multi_match": {

            "query": query,

            "fields": ["text^2", "title^3", "parent_text"],

        }},

        "size": top_k,

    })



    return [

        {

            "text": hit["_source"]["text"],

            "metadata": {

                "slug": hit["_source"].get("slug", ""),

                "title": hit["_source"].get("title", ""),

            },

            "score": hit["_score"],

        }

        for hit in results["hits"]["hits"]

    ]

