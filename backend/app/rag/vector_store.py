# -*- coding: utf-8 -*-
"""Vector store management for RAG system (backward-compatible facade).

This module re-exports all public functions from the split sub-modules:
- embedding.py:    GPU embedder, embedding functions, cache utilities
- bm25.py:         BM25 / keyword search, jieba tokenizer
- reranker.py:     Cross-encoder reranker, API reranking
- qdrant_ops.py:   Qdrant client, save/search/retrieve
- index_manager.py: Index CRUD, stats, health checks, ES backend

All original imports like `from app.rag.vector_store import X` continue to work.
"""

# ── embedding.py ──
from app.rag.embedding import (  # noqa: F401
    VECTOR_DIR,
    _embed_cache,
    _EMBED_CACHE_MAX,
    _embed_cache_lock,
    _get_embedding_dim,
    _to_sparse_vector,
    _redis_sync_get,
    _redis_sync_setex,
    _cache_key,
    _embed_api,
    _embed_dense_sparse_dashscope,
    embed_texts_as_list,
    embed_texts_llm,
)

# ── bm25.py ──
from app.rag.bm25 import (  # noqa: F401
    _kw_docs,
    _kw_idf,
    _kw_avgdl,
    _kw_lock,
    _KW_MIN_RAW_SCORE,
    _KW_MIN_IDF,
    _ZH_STOPWORDS,
    _jieba,
    _get_jieba,
    _tokenize,
    _build_kw_index,
    _load_docs_from_qdrant,
    _bm25_score,
    retrieve_keyword,
    get_bm25_stats,
)

# ── reranker.py ──
from app.rag.reranker import (  # noqa: F401
    _reranker,
    _RERANKER_MODEL,
    _get_reranker,
    _rerank_via_api,
    rerank,
)

# ── qdrant_ops.py ──
from app.rag.qdrant_ops import (  # noqa: F401
    _qdrant_client,
    _qdrant_available,
    _get_qdrant,
    _get_qdrant_collection_name,
    save_index_qdrant,
    hybrid_search_qdrant,
    retrieve_qdrant,
)

# ── index_manager.py ──
from app.rag.index_manager import (  # noqa: F401
    _stats_cache,
    _STATS_CACHE_TTL,
    _invalidate_stats_cache,
    add_to_index,
    _add_to_index_qdrant,
    delete_from_index,
    _delete_from_index_qdrant,
    save_index,
    load_index,
    retrieve,
    _simple_diversity,
    format_context,
    get_collection_stats,
    _get_collection_stats_qdrant,
    get_indexed_sources,
    _get_indexed_sources_qdrant,
    check_index_stale,
    _check_qdrant_available,
    ensure_payload_indexes,
    check_vector_config_mismatch,
    get_index_config,
    check_index_upgrade_strategy,
    _es_client,
    _get_es,
    save_index_es,
    retrieve_keyword_es,
)
