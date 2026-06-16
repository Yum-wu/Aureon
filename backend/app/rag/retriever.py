"""
Hybrid retrieval for RAG system.
Contains: BM25 + vector hybrid retrieval, multi-query retrieval, RRF fusion.
"""

from typing import List, Dict, Any

from app.rag.vector_store import retrieve, retrieve_keyword, rerank
from app.rag.reranker import rerank_batched
from app.rag.query_rewriter import is_cross_article_query, expand_queries_rules
from app.rag.classifier import _extract_title_keywords
from app.config import settings

import structlog

logger = structlog.get_logger()

# ── Retrieval constants ──
_RRF_K = settings.rrf_k
_RETRIEVAL_MULTIPLIER = settings.retrieval_multiplier
_RERANK_CANDIDATES = settings.rerank_candidates
_ADAPTIVE_RERANK_THRESHOLD = settings.adaptive_rerank_threshold
MULTI_QUERY_ENABLED = settings.multi_query_enabled

# Adaptive re-ranking based on query complexity
_ADAPTIVE_RERANK_ENABLED = settings.adaptive_rerank_enabled
_ENSEMBLE_RERANK_ENABLED = settings.ensemble_rerank_enabled

# RRF score threshold: conservative floor — catches truly empty results.
# The reranker is the primary quality gate; this is just a safety net.
_MIN_RELEVANCE_SCORE = settings.min_relevance_score

# Pre-RRF cosine threshold: filters vector results BEFORE fusion.
# RRF rank-1 = 1/(200+1) ≈ 0.005, so post-RRF thresholds are too low.
_VECTOR_MIN_COSINE = settings.vector_min_cosine

# Vector RRF contribution cap: limit how many vector results enter RRF fusion.
# Prevents low-confidence vector matches from drowning precise BM25 results.
_VECTOR_MAX_CONTRIB = settings.vector_max_contrib
_VECTOR_CONFIDENCE_THRESHOLD = settings.vector_confidence_threshold


def hybrid_retrieve(query: str, top_k: int = 3, lang_filter: str = None) -> List[Dict[str, Any]]:
    """Hybrid retrieval: BM25 keyword + vector search, fused via RRF.

    Runs both retrievers and combines results using Reciprocal Rank Fusion.
    BM25 handles exact keyword matches; vector handles semantic similarity.

    Auto-degrades to BM25-only if vector results look broken (all same score).

    Args:
        query: 查询文本
        top_k: 返回结果数量
        lang_filter: 语言过滤（"zh" 或 "en"）
    """
    # 当 sparse 向量启用时，优先使用 Qdrant 原生混合搜索
    if settings.sparse_enabled:
        from app.rag.vector_store import hybrid_search_qdrant
        return hybrid_search_qdrant(query, top_k=top_k, lang_filter=lang_filter)

    bm25_results = retrieve_keyword(query, top_k=top_k * _RETRIEVAL_MULTIPLIER, lang_filter=lang_filter)
    vector_results = retrieve(query, top_k=top_k * _RETRIEVAL_MULTIPLIER, use_mmr=False, lang_filter=lang_filter)

    # Use all vector results — quality check removed to avoid false discards
    # on small collections where cosine scores naturally cluster together

    # ── Pre-RRF score filtering ──
    if vector_results:
        filtered_vector = [
            r for r in vector_results
            if r.get("metadata", {}).get("cosine_score", 1.0) >= _VECTOR_MIN_COSINE
        ]
        if not filtered_vector and vector_results:
            logger.info(
                "All %d vector results below cosine threshold %.2f, degrading to BM25-only",
                len(vector_results), _VECTOR_MIN_COSINE,
            )
        vector_results = filtered_vector

    # If only one retriever has results, use it directly
    if not bm25_results and not vector_results:
        return []
    if not vector_results:
        return bm25_results[:top_k]
    if not bm25_results:
        return vector_results[:top_k]

    # RRF fusion: score each doc by 1/(k + rank) from each retriever
    # BM25 gets 10% bonus — keyword matches are more precise for entity/topic queries
    # Deduplicate chunks by slug BEFORE ranking — same article should count once per retriever
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict] = {}

    def _doc_key(doc: Dict) -> str:
        """Unique key for deduplication — uses slug (article ID)."""
        return doc.get("metadata", {}).get("slug", "") or doc.get("text", "")[:50]

    # Dedup by slug within each retriever: keep best rank per source
    def _dedup_by_source(results: List[Dict]) -> List[Dict]:
        seen: Dict[str, int] = {}
        deduped = []
        for rank, doc in enumerate(results, 1):
            key = _doc_key(doc)
            if key not in seen:
                seen[key] = rank
                deduped.append(doc)
            # else: already have a better-ranked chunk from this source
        return deduped

    bm25_deduped = _dedup_by_source(bm25_results)
    vector_deduped = _dedup_by_source(vector_results)

    for rank, doc in enumerate(bm25_deduped, 1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        doc_map[key] = doc

    _vector_contrib_count = 0
    for rank, doc in enumerate(vector_deduped, 1):
        if _vector_contrib_count >= _VECTOR_MAX_CONTRIB:
            break
        cosine = doc.get("metadata", {}).get("cosine_score", 1.0)
        if cosine < _VECTOR_CONFIDENCE_THRESHOLD:
            continue
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        if key not in doc_map:
            doc_map[key] = doc
        elif "_embedding" in doc:
            # Preserve embedding from vector result for downstream reuse
            doc_map[key]["_embedding"] = doc["_embedding"]
        _vector_contrib_count += 1

    # Title/slug boost: if query terms match a document's title or slug,
    # boost its RRF score. Helps disambiguate when multiple articles share
    # terminology (e.g., "LangGraph" should prioritize the LangGraph article).
    _title_boost_keywords = _extract_title_keywords(query)
    if _title_boost_keywords:
        for key, doc in doc_map.items():
            title = (doc.get("metadata", {}).get("title", "") + " " +
                     doc.get("metadata", {}).get("slug", "")).lower()
            matches = sum(1 for kw in _title_boost_keywords if kw in title)
            if matches > 0:
                boost = 1.0 + 0.5 * matches  # 50% boost per matching keyword
                rrf_scores[key] *= boost

    # Sort by RRF score descending
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Take candidates for diversity selection (more than top_k)
    candidate_limit = min(len(ranked), max(_RERANK_CANDIDATES, top_k * 3))
    candidates = []
    for key, score in ranked[:candidate_limit]:
        doc = doc_map[key].copy()
        doc["score"] = score
        candidates.append(doc)

    # ── NEW: Adaptive Re-ranking based on Query Complexity ──
    if _ADAPTIVE_RERANK_ENABLED and len(candidates) > top_k:
        try:
            # Get query complexity and re-ranking strategy
            from app.rag.query_classifier import get_reranking_strategy
            strategy = get_reranking_strategy(query)
            complexity = strategy["complexity"]

            if complexity == "simple":
                # Skip re-ranking for simple queries (latency priority)
                logger.info(
                    "Adaptive rerank: SKIP (simple query, latency priority)"
                )
            elif complexity == "medium":
                # Single reranker (balance latency/quality)
                logger.info(
                    "Adaptive rerank: SINGLE (medium complexity)"
                )
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
            elif complexity == "complex":
                # Aggressive reranking for complex queries:
                # - More candidates to rerank (top_k * 5 vs * 3)
                # - Batch parallel reranking for latency optimization
                logger.info(
                    "Adaptive rerank: AGGRESSIVE (complex query, max quality)"
                )
                rerank_limit = max(top_k * 5, 15)
                candidates = rerank_batched(query, candidates, top_k=min(len(candidates), rerank_limit))
            else:
                # Default: single reranker
                logger.info(
                    "Adaptive rerank: SINGLE (default)"
                )
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
        except Exception as e:
            logger.warning("Adaptive re-ranking failed, using RRF candidates as-is: %s", e)

    # Diversity selection: only for cross-article queries (comparisons, summaries).
    # For simple factual queries, return top-k by score — this maximizes precision
    # since the correct article's chunks should cluster at the top.
    if is_cross_article_query(query):
        selected = []
        seen_slugs = set()
        # Pass 1: best chunk per unique article
        for doc in candidates:
            slug = doc.get("metadata", {}).get("slug", "")
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                selected.append(doc)
                if len(selected) >= top_k:
                    break
        # Pass 2: fill remaining with best scores from duplicates
        if len(selected) < top_k:
            for doc in candidates:
                if doc not in selected:
                    selected.append(doc)
                    if len(selected) >= top_k:
                        break
    else:
        selected = candidates[:top_k]

    # Relevance gate: if best score is too low, both retrievers failed
    if selected and selected[0].get("score", 0) < _MIN_RELEVANCE_SCORE:
        logger.info("All results below relevance threshold (max=%.4f < %.4f), returning empty",
                     selected[0]["score"], _MIN_RELEVANCE_SCORE)
        return []

    return selected


def multi_query_retrieve(query: str, top_k: int = 3, lang_filter: str = None) -> List[Dict[str, Any]]:
    """Multi-query retrieval for cross-article queries.

    Detects cross-article queries (comparisons, contrasts, etc.) and expands
    them into multiple focused sub-queries. Each variant is retrieved independently
    and results are fused via RRF, with diversity selection to maximize coverage.

    For simple single-article queries, this delegates directly to hybrid_retrieve
    with zero overhead.

    Note: lang_filter is accepted for API compatibility but search always covers
    all languages. Language filtering only applies to document list display.

    Args:
        query: 查询文本
        top_k: 返回结果数量
        lang_filter: 语言过滤（已弃用，搜索始终覆盖所有语言）

    Returns:
        List of top_k document chunks, deduplicated by slug with diversity
    """
    # Fast path: skip expansion for simple queries or when disabled
    if not MULTI_QUERY_ENABLED or not is_cross_article_query(query):
        return hybrid_retrieve(query, top_k=top_k)

    # Cross-article path: expand into variants and retrieve each
    variants = expand_queries_rules(query)

    # Collect all results with their source variant for RRF scoring
    all_results: List[Dict[str, Any]] = []
    for variant in variants:
        variant_results = hybrid_retrieve(variant, top_k=top_k * 2)
        all_results.append(variant_results)

    # RRF fusion across all variant result lists
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict] = {}

    def _doc_key(doc: Dict) -> str:
        return doc.get("metadata", {}).get("slug", "") or doc.get("text", "")[:50]

    for variant_results in all_results:
        # Deduplicate within each variant's results by slug
        seen: Dict[str, int] = {}
        deduped = []
        for rank, doc in enumerate(variant_results, 1):
            key = _doc_key(doc)
            if key not in seen:
                seen[key] = rank
                deduped.append(doc)

        for rank, doc in enumerate(deduped, 1):
            key = _doc_key(doc)
            rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
            if key not in doc_map:
                doc_map[key] = doc
            elif "_embedding" in doc:
                # Preserve embedding from vector result for downstream reuse
                doc_map[key]["_embedding"] = doc["_embedding"]

    # Title/slug boost (same logic as hybrid_retrieve)
    _title_boost_keywords = _extract_title_keywords(query)
    if _title_boost_keywords:
        for key, doc in doc_map.items():
            title = (doc.get("metadata", {}).get("title", "") + " " +
                     doc.get("metadata", {}).get("slug", "")).lower()
            matches = sum(1 for kw in _title_boost_keywords if kw in title)
            if matches > 0:
                boost = 1.0 + 0.5 * matches
                rrf_scores[key] *= boost

    # Sort by RRF score descending
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Build candidate list
    candidates = []
    for key, score in ranked:
        doc = doc_map[key].copy()
        doc["score"] = score
        candidates.append(doc)

    # Reranker disabled — RRF alone gives better recall.
    # CRAG assessment in rag_query handles quality filtering.

    # Diversity selection: one per unique slug, then fill remaining slots
    selected = []
    seen_slugs = set()
    # Pass 1: best chunk per unique article
    for doc in candidates:
        slug = doc.get("metadata", {}).get("slug", "")
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            selected.append(doc)
            if len(selected) >= top_k:
                break
    # Pass 2: fill remaining with best scores from duplicates
    if len(selected) < top_k:
        for doc in candidates:
            if doc not in selected:
                selected.append(doc)
                if len(selected) >= top_k:
                    break

    # Relevance gate (same as hybrid_retrieve): check RRF score
    if selected and selected[0].get("score", 0) < _MIN_RELEVANCE_SCORE:
        logger.info("multi_query: all results below relevance threshold (max=%.4f < %.4f)",
                     selected[0]["score"], _MIN_RELEVANCE_SCORE)
        return []

    # Reranker is for ranking only — no score threshold here.
    # CRAG assessment (in rag_query) handles relevance filtering.

    return selected
