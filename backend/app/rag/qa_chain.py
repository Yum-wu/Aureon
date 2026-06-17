"""
QA chain for RAG system (backward-compatible facade).

This module is a thin facade that re-exports all public functions and constants
from the following sub-modules:
- app.rag.classifier  (query classification, context compression)
- app.rag.retriever   (hybrid retrieval, multi-query retrieval)
- app.rag.generator   (answer generation, RAG query pipelines)
- app.rag.indexer     (indexing pipeline, async RAG operations)
"""

# 鈹�鈹� classifier.py 鈹�鈹�
from app.rag.classifier import (
    _TITLE_KEYWORDS_ZH,
    _extract_title_keywords,
    compress_context,
    _deduplicate_chunks,
    _CONTEXT_COMPRESSION_ENABLED,
    _CONTEXT_COMPRESSION_THRESHOLD,
    _HIGH_SCORE_SKIP_THRESHOLD,
    _LOW_SCORE_THRESHOLD,
    _NEGATIVE_DETECTION_ENABLED,
    _CLASSIFIER_CACHE,
    _CLASSIFIER_CACHE_TIMESTAMPS,
    _CLASSIFIER_CACHE_TTL,
    _CLASSIFIER_CACHE_MAXSIZE,
    _CLASSIFIER_CACHE_LOCK,
    _classifier_cache_key,
    _classifier_cache_get,
    _classifier_cache_set,
    classify_query_answerable,
    _NEGATIVE_KEYWORDS_ZH,
    _is_negative_by_keywords,
    classify_query_answerable_sync,
)

# 鈹�鈹� retriever.py 鈹�鈹�
from app.rag.retriever import (
    _RRF_K,
    _RETRIEVAL_MULTIPLIER,
    _RERANK_CANDIDATES,
    _ADAPTIVE_RERANK_THRESHOLD,
    MULTI_QUERY_ENABLED,
    _ADAPTIVE_RERANK_ENABLED,
    _ENSEMBLE_RERANK_ENABLED,
    _MIN_RELEVANCE_SCORE,
    _VECTOR_MIN_COSINE,
    _VECTOR_MAX_CONTRIB,
    _VECTOR_CONFIDENCE_THRESHOLD,
    hybrid_retrieve,
    multi_query_retrieve,
)

# 鈹�鈹� generator.py 鈹�鈹�
from app.rag.generator import (
    QA_SYSTEM_PROMPT,
    QA_SYSTEM_PROMPT_EN,
    _QUERY_TYPE_INSTRUCTIONS,
    _HYDE_ENABLED,
    _HYDE_FALLBACK_THRESHOLD,
    generate_answer,
    rag_query,
    rag_query_astream,
    rag_query_with_cache,
)

# 鈹�鈹� indexer.py 鈹�鈹�
from app.rag.indexer import (
    _CONTEXTUAL_PROMPT_TEMPLATE,
    run_incremental_index,
    _generate_context_prefixes_async,
    _add_contextual_prefixes,
    run_index_pipeline,
    generate_answer_async,
    hybrid_retrieve_async,
    rag_query_async,
)

# -- embedding.py + index_manager.py (for test patches) --
from app.rag.embedding import embed_texts_llm
from app.rag.index_manager import retrieve, save_index

# Semantic chunking setting (used by run_index_pipeline and external references)
SEMANTIC_CHUNKING_ENABLED = __import__('app.config', fromlist=['settings']).settings.semantic_chunking_enabled

__all__ = [
    # classifier
    "_TITLE_KEYWORDS_ZH", "_extract_title_keywords", "compress_context", "_deduplicate_chunks",
    "_CONTEXT_COMPRESSION_ENABLED", "_CONTEXT_COMPRESSION_THRESHOLD",
    "_HIGH_SCORE_SKIP_THRESHOLD", "_LOW_SCORE_THRESHOLD", "_NEGATIVE_DETECTION_ENABLED",
    "_CLASSIFIER_CACHE", "_CLASSIFIER_CACHE_TIMESTAMPS", "_CLASSIFIER_CACHE_TTL",
    "_CLASSIFIER_CACHE_MAXSIZE", "_CLASSIFIER_CACHE_LOCK",
    "_classifier_cache_key", "_classifier_cache_get", "_classifier_cache_set",
    "classify_query_answerable", "_NEGATIVE_KEYWORDS_ZH", "_is_negative_by_keywords",
    "classify_query_answerable_sync",
    # retriever
    "_RRF_K", "_RETRIEVAL_MULTIPLIER", "_RERANK_CANDIDATES", "_ADAPTIVE_RERANK_THRESHOLD",
    "MULTI_QUERY_ENABLED", "_ADAPTIVE_RERANK_ENABLED", "_ENSEMBLE_RERANK_ENABLED",
    "_MIN_RELEVANCE_SCORE", "_VECTOR_MIN_COSINE", "_VECTOR_MAX_CONTRIB",
    "_VECTOR_CONFIDENCE_THRESHOLD", "hybrid_retrieve", "multi_query_retrieve",
    # generator
    "QA_SYSTEM_PROMPT", "QA_SYSTEM_PROMPT_EN", "_QUERY_TYPE_INSTRUCTIONS",
    "_HYDE_ENABLED", "_HYDE_FALLBACK_THRESHOLD",
    "generate_answer", "rag_query", "rag_query_astream", "rag_query_with_cache",
    # indexer
    "_CONTEXTUAL_PROMPT_TEMPLATE", "run_incremental_index",
    "_generate_context_prefixes_async", "_add_contextual_prefixes",
    "run_index_pipeline", "generate_answer_async", "hybrid_retrieve_async",
    "rag_query_async", "SEMANTIC_CHUNKING_ENABLED",
    # embedding + index_manager (test patches)
    "embed_texts_llm", "retrieve", "save_index",
]
