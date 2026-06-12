"""
QA chain for RAG system.
Retrieves relevant context and generates answers using LLM.
"""

import json
import time
import os
import asyncio
import numpy as np
from typing import List, Dict, Any

from app.rag.vector_store import retrieve, retrieve_keyword, format_context, save_index, embed_texts_llm, rerank, get_thread_query_embedding
from app.rag.query_rewriter import is_cross_article_query, expand_queries_rules, hyde_retrieve, hyde_retrieve_async
from app.rag.models import RAGQueryResponse, SourceItem
from app.rag.ensemble_reranker import get_ensemble_reranker
from app.utils.lang_detect import detect_language, lang_instruction

from app.config import settings

import structlog

logger = structlog.get_logger()

_RRF_K = settings.rrf_k
_RETRIEVAL_MULTIPLIER = settings.retrieval_multiplier
_RERANK_CANDIDATES = settings.rerank_candidates
_ADAPTIVE_RERANK_THRESHOLD = settings.adaptive_rerank_threshold
MULTI_QUERY_ENABLED = settings.multi_query_enabled
SEMANTIC_CHUNKING_ENABLED = settings.semantic_chunking_enabled

# Adaptive re-ranking based on query complexity
_ADAPTIVE_RERANK_ENABLED = settings.adaptive_rerank_enabled
_ENSEMBLE_RERANK_ENABLED = settings.ensemble_rerank_enabled

# Keywords that uniquely identify specific articles — used for title/slug boost.
# Only terms that are specific enough to disambiguate between articles.
_TITLE_KEYWORDS_ZH = {
    "langgraph": "langgraph", "hermes": "hermes", "crewai": "crewai",
    "rag": "rag", "bm25": "bm25", "lcel": "lcel", "llamaindex": "llamaindex",
    "bge": "bge", "cross-encoder": "cross-encoder", "hyde": "hyde",
    "react": "react", "qwen": "qwen", "dashscope": "dashscope",
    "chromadb": "chromadb", "langchain": "langchain",
}


def _extract_title_keywords(query: str) -> List[str]:
    """Extract keywords from query that could uniquely identify an article."""
    q_lower = query.lower()
    return [kw for kw, normalized in _TITLE_KEYWORDS_ZH.items() if kw in q_lower]

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

# LLM-based negative detection: when top retrieval score is below this threshold,
# use an LLM classifier to decide if the query is answerable by the knowledge base.
_LOW_SCORE_THRESHOLD = settings.low_score_threshold
_NEGATIVE_DETECTION_ENABLED = settings.negative_detection_enabled

# Context Compression: filter chunks by embedding similarity to query.
# Removes semantically irrelevant chunks before passing to LLM, reducing token waste 30-50%.
_CONTEXT_COMPRESSION_ENABLED = settings.context_compression_enabled
_CONTEXT_COMPRESSION_THRESHOLD = settings.context_compression_threshold

# HyDE (Hypothetical Document Embedding): generate hypothetical answer for retrieval.
# Improves retrieval accuracy by using LLM-generated answer instead of raw query.
# Reference: Gao et al., 2022 "Precise Zero-Shot Dense Retrieval without Relevance Labels"
_HYDE_ENABLED = settings.hyde_enabled
_HYDE_FALLBACK_THRESHOLD = settings.hyde_fallback_threshold


def compress_context(query: str, chunks: List[Dict[str, Any]], threshold: float = None,
                     query_embedding: np.ndarray = None) -> List[Dict[str, Any]]:
    """Filter chunks by embedding similarity to query (lightweight context compression).

    Computes cosine similarity between query embedding and each chunk embedding.
    Removes chunks below threshold to reduce token waste in LLM context.

    Reuses pre-computed chunk embeddings (_embedding field from retrieval phase)
    when available, avoiding redundant embedding computation.

    Args:
        query: User query text
        chunks: List of retrieved chunk dicts with 'text' field and optional '_embedding'
        threshold: Minimum cosine similarity (default: _CONTEXT_COMPRESSION_THRESHOLD)
        query_embedding: Pre-computed query embedding (avoids redundant API call).
            When None, retrieved from thread-local or computed via API.

    Returns:
        Filtered list of chunks above threshold, sorted by similarity descending.
    """
    if not chunks or not _CONTEXT_COMPRESSION_ENABLED:
        return chunks

    if threshold is None:
        threshold = _CONTEXT_COMPRESSION_THRESHOLD

    # 优先级：参数 > chunks 中携带 > 全局变量
    emb = query_embedding
    if emb is None and chunks:
        emb = chunks[0].get("_query_embedding")
    if emb is None:
        emb = get_thread_query_embedding()
    if emb is None:
        return chunks  # 无 embedding 可用，不过滤

    try:
        # Check which chunks have pre-computed embeddings from retrieval phase
        cached_indices = {i for i, c in enumerate(chunks) if "_embedding" in c}
        has_cached = len(cached_indices) > 0

        if has_cached:
            # Reuse stored embeddings: embed only uncached chunks (NOT the query).
            # Query embedding is reused from retrieve_qdrant via thread-local storage,
            # avoiding a redundant embedding API call.
            uncached_texts = [chunks[i]["text"] for i in range(len(chunks)) if i not in cached_indices]
            if uncached_texts:
                new_embeddings = embed_texts_llm(uncached_texts)
            else:
                new_embeddings = np.empty((0, 0), dtype=np.float32)

            # 使用函数入口处解析的 query embedding（优先级：参数 > chunks 携带 > 全局变量）
            query_emb = emb

            chunk_embs = []
            uncached_iter = iter(new_embeddings) if len(new_embeddings) > 0 else iter([])
            for i in range(len(chunks)):
                if i in cached_indices:
                    chunk_embs.append(chunks[i]["_embedding"])
                else:
                    chunk_embs.append(next(uncached_iter))
            chunk_embs = np.array(chunk_embs, dtype=np.float32)

            logger.debug(
                "Context compression: reused %d/%d cached embeddings",
                len(cached_indices), len(chunks),
            )
        else:
            # No cached embeddings: compute chunk embeddings only (query_emb already resolved)
            chunk_texts = [c["text"] for c in chunks]

            embeddings = None
            from app.rag.vector_store import _skip_local_embed
            if not _skip_local_embed:
                try:
                    from app.rag.vector_store import _get_gpu_embedder
                    gpu_embedder = _get_gpu_embedder()
                    if gpu_embedder is not None:
                        embeddings = gpu_embedder.encode(chunk_texts, batch_size=len(chunk_texts))
                except Exception:
                    pass

            if embeddings is None:
                embeddings = embed_texts_llm(chunk_texts)

            query_emb = emb
            chunk_embs = embeddings

        # Normalize embeddings before computing cosine similarity
        # API embeddings (DashScope/SiliconFlow/Zhipu) are NOT pre-normalized
        query_norm = query_emb / (np.linalg.norm(query_emb) + 1e-8)
        chunk_norms = chunk_embs / (np.linalg.norm(chunk_embs, axis=1, keepdims=True) + 1e-8)
        similarities = np.dot(chunk_norms, query_norm)

        # Filter and sort by similarity
        scored_chunks = []
        for chunk, sim in zip(chunks, similarities):
            if sim >= threshold:
                chunk_copy = dict(chunk)
                chunk_copy["compression_score"] = float(sim)
                # Remove _embedding from output to save memory (no longer needed)
                chunk_copy.pop("_embedding", None)
                scored_chunks.append(chunk_copy)

        scored_chunks.sort(key=lambda c: c["compression_score"], reverse=True)

        if len(scored_chunks) < len(chunks):
            logger.info(
                "Context compression: %d/%d chunks kept (threshold=%.2f)",
                len(scored_chunks), len(chunks), threshold,
            )

        return scored_chunks

    except Exception as e:
        logger.warning("Context compression failed, returning all chunks: %s", e)
        return chunks

# Skip Negative Detection when top RRF score is above this threshold.
# High scores indicate confident retrieval — LLM classifier is wasteful.
_HIGH_SCORE_SKIP_THRESHOLD = settings.high_score_skip_threshold

# LLM Classifier cache: avoid redundant API calls for the same query.
# Keyed by normalized query hash, TTL-based expiry, thread-safe with LRU eviction.
import hashlib as _hashlib
import threading as _threading
from collections import OrderedDict as _OrderedDict

_CLASSIFIER_CACHE: _OrderedDict[str, bool] = _OrderedDict()
_CLASSIFIER_CACHE_TIMESTAMPS: Dict[str, float] = {}
_CLASSIFIER_CACHE_TTL = settings.classifier_cache_ttl  # seconds
_CLASSIFIER_CACHE_MAXSIZE = 1000
_CLASSIFIER_CACHE_LOCK = _threading.Lock()


def _classifier_cache_key(query: str) -> str:
    """Deterministic cache key for classifier results."""
    return _hashlib.md5(query.strip().lower().encode()).hexdigest()


def _classifier_cache_get(query: str) -> bool | None:
    """Return cached result or None if miss/expired. Thread-safe with LRU promotion."""
    if _CLASSIFIER_CACHE_TTL <= 0:
        return None
    key = _classifier_cache_key(query)
    with _CLASSIFIER_CACHE_LOCK:
        ts = _CLASSIFIER_CACHE_TIMESTAMPS.get(key)
        if ts is not None and (time.time() - ts) < _CLASSIFIER_CACHE_TTL:
            value = _CLASSIFIER_CACHE.get(key)
            if value is not None:
                _CLASSIFIER_CACHE.move_to_end(key)  # LRU promotion
            return value
    return None


def _classifier_cache_set(query: str, answerable: bool) -> None:
    """Store classifier result in memory cache. Thread-safe with LRU eviction."""
    if _CLASSIFIER_CACHE_TTL <= 0:
        return
    key = _classifier_cache_key(query)
    with _CLASSIFIER_CACHE_LOCK:
        if key in _CLASSIFIER_CACHE:
            _CLASSIFIER_CACHE.move_to_end(key)
        else:
            if len(_CLASSIFIER_CACHE) >= _CLASSIFIER_CACHE_MAXSIZE:
                _CLASSIFIER_CACHE.popitem(last=False)  # evict oldest
            _CLASSIFIER_CACHE[key] = answerable
        _CLASSIFIER_CACHE_TIMESTAMPS[key] = time.time()


async def classify_query_answerable(query: str, model: str = None) -> bool:
    """Use LLM to determine if a query can be answered by the knowledge base."""
    # Fast-path: keyword heuristic before LLM call
    if _is_negative_by_keywords(query):
        return False

    # Cache check: skip LLM call for repeated queries
    cached = _classifier_cache_get(query)
    if cached is not None:
        logger.debug("Classifier cache hit: query=%s answerable=%s", query[:40], cached)
        return cached

    from app.agent.llm import create_llm

    llm = create_llm(model=model, temperature=0.0, streaming=False)
    prompt = (
        "你是一个企业知识库的查询分类器。判断以下查询是否能在"
        "\"AI技术、开发经验、部署实践\"相关的知识库中找到答案。\n\n"
        f"查询：{query}\n\n"
        "只回答 YES 或 NO。如果查询涉及以下内容，回答 NO：\n"
        "- 未在知识库中覆盖的具体技术细节（如特定云服务商配置、定价、团队规模）\n"
        "- 与知识库主题无关的领域（如量子计算、生物医学）\n"
        "- 要求最新实时信息的问题（如当前股价、今日天气）\n\n"
        "如果查询涉及以下内容，回答 YES：\n"
        "- RAG、LangChain、LangGraph、BM25、向量检索等 AI 技术\n"
        "- 开发流程、部署实践、性能优化\n"
        "- 知识库中可能涵盖的通用技术问题"
    )

    try:
        response = await llm.ainvoke(prompt)
        answerable = "YES" in response.content.upper()
        _classifier_cache_set(query, answerable)
        return answerable
    except Exception as e:
        logger.warning("LLM classifier failed: %s, defaulting to not answerable", e)
        return False


# ── Negative detection: keyword fast-path ──
# Queries matching these patterns are almost certainly unanswerable by the KB.
# Pure rule-based (no LLM call) — eliminates 3-5s latency per query.
_NEGATIVE_KEYWORDS_ZH = [
    # Pricing / cost
    "定价", "价格", "收费", "费用", "免费额度", "成本是多少", "售价",
    # Team / people
    "团队有多少人", "团队规模", "多少人",
    # Training data
    "训练数据量", "训练数据", "数据量是多少",
    # Version / release
    "版本号", "最新版本", "当前版本", "什么时候发布", "发布时间", "发布日期",
    "最新更新",
    # Education / personal
    "毕业于", "教育背景", "学历",
    # Company info
    "创始人", "CEO", "公司地址",
    # Competitive / external
    "更适合", "对比", "哪个更好",
    # Future plans
    "下一步计划", "未来规划", "路线图",
    # Stars / popularity
    "GitHub Stars", "star 数", "有多少 star",
    # Pricing (English)
    "pricing", "price", "cost", "how much",
    "team size", "how many people",
    "training data size", "training data volume",
    "version number", "latest version",
    "when was", "release date",
    "university", "education",
    "founder", "CEO", "headquarters",
    "roadmap", "next steps",
]


def _is_negative_by_keywords(query: str) -> bool:
    """Fast heuristic: detect obviously unanswerable queries by keywords."""
    q = query.lower()
    for kw in _NEGATIVE_KEYWORDS_ZH:
        if kw.lower() in q:
            return True
    return False


def classify_query_answerable_sync(query: str, llm_call_fn=None) -> bool:
    """Rule-based classifier: no LLM call. Eliminates 3-5s latency per query.

    Returns False for queries about pricing, versions, team size, external facts, etc.
    """
    if _is_negative_by_keywords(query):
        return False
    return True


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
                # Single BGE reranker (balance latency/quality)
                logger.info(
                    "Adaptive rerank: SINGLE_BGE (medium complexity)"
                )
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
            elif complexity == "complex" and _ENSEMBLE_RERANK_ENABLED:
                # Ensemble reranking not available in sync path; fall back to single BGE
                # Use hybrid_retrieve_async for ensemble reranking
                logger.info(
                    "Adaptive rerank: SINGLE_BGE (complex, ensemble unavailable in sync)"
                )
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
            else:
                # Default: single BGE reranker
                logger.info(
                    "Adaptive rerank: SINGLE_BGE (default)"
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


QA_SYSTEM_PROMPT = """你是精准的知识库问答助手。你的唯一任务是回答用户的问题。

## 核心原则
- 先理解用户的问题意图，再从参考文档中提取答案
- 每个句子必须直接回应用户的问题
- 如果文档中有答案，直接给出答案
- 如果文档中没有答案，直接说"文档中未提及"

## 回答结构（必须遵守）
1. **直接回答**（1-2 句话，直接回答问题核心，控制在 200 字以内）
2. **补充细节**（仅当用户问题需要更详细解释时，不超过 500 字）
3. **引用来源**（格式：[来源: 文章标题]）

## 字数限制
- 总回答长度控制在 500 字以内
- 能用一句话回答的不要用两句话

## 禁止行为
- ❌ 禁止以"根据文档"、"文档介绍了"、"参考文档提到"开头
- ❌ 禁止复述文档内容而不回答问题
- ❌ 禁止添加用户未要求的背景信息
- ❌ 禁止使用"总的来说"、"综上所述"、"需要注意的是"等总结性语句
- ❌ 禁止在回答开头加前言或铺垫

## 正确示例

用户问："BM25 的核心原理是什么？"
✅ 正确："BM25 通过词频饱和度和文档长度归一化计算关键词匹配分数，核心公式包含 TF（词频）和 IDF（逆文档频率）两个组件。[来源: RAG 优化实战]"
❌ 错误："文档介绍了 RAG 系统中使用的多种检索技术。BM25 是其中一种经典的排序算法，它的核心原理是..."

用户问："如何配置 Redis 缓存？"
✅ 正确："配置步骤：1) 安装 redis-py；2) 设置 REDIS_URL 环境变量；3) 在 config.py 中启用缓存层。[来源: Redis 集成指南]"
❌ 错误："Redis 是一个高性能的内存数据库，在 RAG 系统中常用于缓存。下面文档介绍了如何配置..."

## 负面回答模式
如果参考文档中没有相关信息，直接回答：
"文档中未提及该信息。"

不要猜测、不要补充你认为可能正确的信息。

{lang_instruction}

参考文档中每段以 [Source N: 文章标题] 开头。引用时用自然方式标注来源，例如：[来源: Hermes Agent 实战]。

参考文档：
{context}
"""

QA_SYSTEM_PROMPT_EN = """You are a precise knowledge base QA assistant. Your only task is to answer the user's question.

## Core Principles
- Understand the user's question intent first, then extract the answer from reference documents
- Every sentence must directly address the user's question
- If the documents contain the answer, give it directly
- If the documents don't contain the answer, say "Not mentioned in the documents"

## Answer Structure (mandatory)
1. **Direct answer** (1-2 sentences, addressing the core question)
2. **Supporting details** (only when the user needs more explanation)
3. **Source citation** (format: [Source: Article Title])

## Prohibited Patterns
- ❌ Do NOT start with "Based on the documents", "The documents mention", "According to the reference"
- ❌ Do NOT summarize document content without answering the question
- ❌ Do NOT add background information the user didn't ask for
- ❌ Do NOT use "In summary", "To summarize", "It's worth noting" as transitions
- ❌ Do NOT add preamble or setup before the actual answer

## Correct Examples

User: "What is the core principle of BM25?"
✅ Correct: "BM25 calculates keyword matching scores through term frequency saturation and document length normalization, with TF and IDF as its two core components. [Source: RAG Optimization Guide]"
❌ Wrong: "The documents describe various retrieval techniques used in RAG systems. BM25 is one of the classic ranking algorithms. Its core principle is..."

User: "How to configure Redis caching?"
✅ Correct: "Steps: 1) Install redis-py; 2) Set REDIS_URL environment variable; 3) Enable cache layer in config.py. [Source: Redis Integration Guide]"
❌ Wrong: "Redis is a high-performance in-memory database commonly used for caching in RAG systems. The following documents describe how to configure..."

## Negative Response
If the reference documents don't contain the relevant information, answer directly:
"The documents do not contain information about this topic."

Do not guess or supplement information you think might be correct.

{lang_instruction}

Each paragraph in the reference documents starts with [Source N: Article Title]. When citing, naturally mention the source, e.g., [Source: Hermes Agent in Practice].

Reference documents:
{context}
"""


# ── Query type adaptive instructions ──
_QUERY_TYPE_INSTRUCTIONS = {
    "factual": {
        "zh": "给出明确的事实答案（时间、名称、数字）。一句话回答即可。",
        "en": "Give a clear factual answer (dates, names, numbers). One sentence is sufficient.",
    },
    "comparison": {
        "zh": "用表格或并列结构对比各项差异。每个维度直接回应用户关心的方面。",
        "en": "Use a table or parallel structure to compare differences. Each dimension should directly address what the user cares about.",
    },
    "how_to": {
        "zh": "给出清晰的步骤列表。每步操作直接可执行。",
        "en": "Provide a clear step-by-step list. Each step should be directly actionable.",
    },
    "reasoning": {
        "zh": "给出推理过程和结论。每个推理步骤都要有文档依据。",
        "en": "Provide reasoning process and conclusion. Each reasoning step should have document evidence.",
    },
}


def generate_answer(
    query: str,
    context: str,
    llm_call_fn,
    system_prompt: str = None,
    lang: str = "zh",
    query_type: str = None,
) -> str:
    """Call LLM with context and query. Return generated answer."""
    if system_prompt is None:
        system_prompt = QA_SYSTEM_PROMPT_EN if lang == "en" else QA_SYSTEM_PROMPT
    lang_instr = lang_instruction(lang).strip()

    # Inject query type instruction if available
    type_instruction = ""
    if query_type and query_type in _QUERY_TYPE_INSTRUCTIONS:
        type_instruction = "\n" + _QUERY_TYPE_INSTRUCTIONS[query_type].get(lang, "")

    prompt = system_prompt.format(context=context, lang_instruction=lang_instr + type_instruction)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
    ]
    return llm_call_fn(messages)


def rag_query(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    use_mmr: bool = True,
    lang: str | None = None,
    filter_lang: str | None = None,
) -> RAGQueryResponse:
    """Full RAG pipeline: retrieve → format → generate.

    Args:
        query: 查询文本
        llm_call_fn: LLM 调用函数
        top_k: 返回结果数量
        use_mmr: 是否使用 MMR 多样性优化
        lang: 回复语言（None 则自动检测）
        filter_lang: 文档语言过滤（"zh" 或 "en"），None 表示不过滤
    """
    if lang is None:
        lang = detect_language(query)

    # 1. Hybrid retrieval: BM25 keyword + vector search, RRF fusion
    #    If HyDE is enabled, use hypothetical answer for retrieval
    if _HYDE_ENABLED:
        logger.info("HyDE enabled: using hypothetical answer for retrieval")
        chunks = hyde_retrieve(
            query,
            llm_call_fn,
            top_k=top_k,
            lang=lang,
            lang_filter=filter_lang,
        )
        # If HyDE returns poor results, fallback to multi_query_retrieve
        if chunks:
            top_score = max(c.get("score", 0) for c in chunks)
            if top_score < _HYDE_FALLBACK_THRESHOLD:
                logger.info(
                    "HyDE: poor results (score=%.4f < %.4f), falling back to hybrid retrieval",
                    top_score, _HYDE_FALLBACK_THRESHOLD,
                )
                chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)
        else:
            logger.info("HyDE: no results, falling back to hybrid retrieval")
            chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)
    else:
        chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)

    # 2. Negative detection: LLM classifier for queries the KB can't answer.
    #    Skip when top RRF score is high (confident retrieval) to save LLM calls.
    #    For production, consider adding a score >= 0.1 fast-path to skip
    #    classification when retrieval confidence is very high.
    if _NEGATIVE_DETECTION_ENABLED and chunks:
        top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
        if top_score < _HIGH_SCORE_SKIP_THRESHOLD:
            if not classify_query_answerable_sync(query, llm_call_fn):
                return RAGQueryResponse(
                    answer=(
                        "抱歉，该问题超出了知识库的覆盖范围。"
                        if lang == "zh"
                        else "Sorry, this question is outside the scope of the knowledge base."
                    ),
                    sources=[],
                )
        else:
            logger.info("Skipping negative detection (top_score=%.4f >= %.4f)", top_score, _HIGH_SCORE_SKIP_THRESHOLD)

    # 1b. Context compression: filter chunks by embedding similarity to query
    if chunks:
        chunks = compress_context(query, chunks)

    # 1c. CRAG self-correction: if compression removed all chunks or top score is low,
    #     rewrite query and re-retrieve once (lightweight corrective RAG).
    if chunks:
        top_compression = max(c.get("compression_score", 1.0) for c in chunks)
    else:
        top_compression = 0.0

    if not chunks or top_compression < _CONTEXT_COMPRESSION_THRESHOLD * 1.2:
        # Try expanding query with rule-based variants
        variants = expand_queries_rules(query)
        if len(variants) > 1:
            logger.info("CRAG: low retrieval quality (score=%.3f), retrying with variant: %s",
                        top_compression, variants[1] if len(variants) > 1 else "none")
            retry_query = variants[1] if len(variants) > 1 else variants[0]
            retry_chunks = multi_query_retrieve(retry_query, top_k=top_k, lang_filter=filter_lang)
            if retry_chunks:
                retry_chunks = compress_context(retry_query, retry_chunks)
                if retry_chunks:
                    # Use whichever set has better top compression score
                    retry_top = max(c.get("compression_score", 0) for c in retry_chunks)
                    if retry_top > top_compression:
                        chunks = retry_chunks
                        logger.info("CRAG: retry improved (score %.3f -> %.3f)", top_compression, retry_top)

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base. Please try a different question."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(
            answer=no_result_msg,
            sources=[],
        )

    # 2. Format context
    context = format_context(chunks)

    # 3. Generate
    answer = generate_answer(query, context, llm_call_fn, lang=lang)

    # 4. Build response with sources
    sources = [
        SourceItem(
            title=c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
            slug=c["metadata"].get("slug", ""),
            chunk=c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
            score=c.get("score"),
            chunk_id=c.get("id", c["metadata"].get("chunk_id", "")),
            chunk_text_snippet=c["text"][:200],
        )
        for c in chunks
    ]

    return RAGQueryResponse(answer=answer, sources=sources)


async def rag_query_astream(
    query: str,
    llm,
    top_k: int = 3,
    use_mmr: bool = True,
    lang: str | None = None,
    filter_lang: str | None = None,
    model: str = None,
):
    """Async streaming RAG: BM25 keyword retrieve → stream LLM tokens.

    Uses fast BM25 keyword retrieval (<10ms, no embedding API) for instant
    first-token latency. Yields SSE dicts: sources first, then text tokens.

    *llm* must support ``.astream()`` (e.g. ``ChatOpenAI``).

    Args:
        query: 查询文本
        llm: LLM 实例
        top_k: 返回结果数量
        use_mmr: 是否使用 MMR 多样性优化
        lang: 回复语言（None 则自动检测）
        filter_lang: 文档语言过滤（"zh" 或 "en"），None 表示不过滤
        model: 模型标识（传给 LLM 负面检测分类器）
    """
    if lang is None:
        lang = detect_language(query)

    # 1. 根据查询复杂度路由检索策略
    #    Wrapped in asyncio.to_thread to avoid blocking the event loop
    import asyncio
    from app.rag.query_classifier import route_retrieval

    route = route_retrieval(query)
    if route == "simple":
        # 简单查询：只走 sparse/keyword 检索
        if settings.sparse_enabled:
            from app.rag.vector_store import hybrid_search_qdrant
            chunks = await asyncio.to_thread(
                hybrid_search_qdrant, query, top_k=top_k, lang_filter=filter_lang
            )
        else:
            chunks = await asyncio.to_thread(
                retrieve_keyword, query, top_k=top_k, lang_filter=filter_lang
            )
    elif route == "medium":
        # 中等查询：hybrid retrieve（不含 multi_query）
        chunks = await asyncio.to_thread(
            hybrid_retrieve, query, top_k=top_k, lang_filter=filter_lang
        )
    else:
        # 复杂查询：完整 pipeline
        chunks = await asyncio.to_thread(multi_query_retrieve, query, top_k=top_k, lang_filter=filter_lang)

    # 2. 轻量 CRAG 评估（基于检索分数，无需 LLM 调用）
    if settings.crag_enabled and chunks:
        from app.rag.retrieval_confidence import lightweight_crag_assess
        assessment = lightweight_crag_assess(
            chunks,
            high_threshold=settings.crag_high_confidence,
            low_threshold=settings.crag_low_confidence,
        )
        if assessment == "incorrect":
            no_result_msg = (
                "No relevant content found in the knowledge base. Please try a different question."
                if lang == "en"
                else "知识库中暂无相关内容，请尝试其他问题。"
            )
            yield {"type": "sources", "sources": []}
            yield {"type": "text", "content": no_result_msg}
            return
        # "correct" 和 "ambiguous" 都继续执行

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base. Please try a different question."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        yield {"type": "sources", "sources": []}
        yield {"type": "text", "content": no_result_msg}
        return

    # LLM Negative Detection: skip when top RRF score is high (confident retrieval).
    # This saves one LLM call per high-confidence query (~50% of production traffic).
    if _NEGATIVE_DETECTION_ENABLED and chunks:
        top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
        if top_score < _HIGH_SCORE_SKIP_THRESHOLD:
            answerable = await classify_query_answerable(query, model=model)
            if not answerable:
                yield {"type": "sources", "sources": []}
                no_answer_msg = (
                    "Sorry, this question is outside the scope of the knowledge base."
                    if lang == "en"
                    else "抱歉，该问题超出了知识库的覆盖范围。"
                )
                yield {"type": "text", "content": no_answer_msg}
                return
        else:
            logger.info("Skipping negative detection (top_score=%.4f >= %.4f)", top_score, _HIGH_SCORE_SKIP_THRESHOLD)

    # 1b. Context compression: filter chunks by embedding similarity to query
    #     Wrapped in asyncio.to_thread to avoid blocking event loop with sync embedding API
    if chunks:
        chunks = await asyncio.to_thread(compress_context, query, chunks)

    # 2. Format context
    context = format_context(chunks)

    # 3. Build message
    system_prompt = QA_SYSTEM_PROMPT_EN if lang == "en" else QA_SYSTEM_PROMPT
    lang_instr = lang_instruction(lang).strip()
    prompt = system_prompt.format(context=context, lang_instruction=lang_instr)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
    ]

    # 4. Yield sources event first
    sources_data = [
        {
            "title": c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
            "slug": c["metadata"].get("slug", ""),
            "score": c.get("score"),
            "chunk_id": c.get("id", c["metadata"].get("chunk_id", "")),
            "chunk_text_snippet": c["text"][:200],
        }
        for c in chunks
    ]
    yield {"type": "sources", "sources": sources_data, "model": llm.model if hasattr(llm, "model") else ""}

    # 4b. Yield individual citation events with chunk text (for progressive citation UX)
    for i, c in enumerate(chunks, 1):
        yield {
            "type": "citation",
            "source": {
                "index": i,
                "title": c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
                "slug": c["metadata"].get("slug", ""),
                "chunk": c["text"][:300] + "..." if len(c["text"]) > 300 else c["text"],
                "score": c.get("score"),
            },
        }

    # 5. Stream LLM tokens
    async for chunk in llm.astream(messages):
        content = chunk.content if hasattr(chunk, "content") else ""
        if content:
            yield {"type": "text", "content": content}


async def rag_query_with_cache(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    use_mmr: bool = True,
    lang: str | None = None,
    filter_lang: str | None = None,
    model: str = None,
) -> RAGQueryResponse:
    """RAG query with two-layer Redis semantic cache.

    Two-layer cache architecture:
    - Layer 1: Exact match via token-bag hash (fastest, <1ms)
    - Layer 2: Semantic similarity via embeddings (medium, ~10ms)
    - LLM fallback: actual generation (slowest, ~2s)

    On a cache hit returns the cached answer with sources (stored as JSON).
    On a miss, delegates to :func:`rag_query` and caches the result.
    Degrades gracefully when Redis or semantic cache is unavailable.

    Args:
        query: User query text
        llm_call_fn: LLM invocation function
        top_k: Number of retrieved chunks
        use_mmr: Whether to use MMR diversity optimization
        lang: Response language (None = auto-detect)
        filter_lang: Document language filter
        model: LLM model name (for semantic cache parameterization)

    Returns:
        RAGQueryResponse with answer and source citations
    """
    from app.cache.redis_client import get_cached_with_semantic, set_cached_with_semantic, increment_cache_miss

    # Layer 1+2: Two-layer cache lookup (exact → semantic)
    cached = await get_cached_with_semantic(
        query=query,
        model=model or settings.llm_model,
        temperature=0.0,
        max_tokens=500,
    )
    if cached is not None:
        try:
            cached_data = json.loads(cached)
            answer = cached_data.get("answer", cached)
            sources = cached_data.get("sources", [])
            sources = [SourceItem(**s) for s in sources]
        except (json.JSONDecodeError, TypeError):
            # Corrupt cache entry (raw string, not JSON) — skip and re-query.
            # The next successful query will overwrite with correct JSON.
            logger.warning("Corrupt cache entry detected (non-JSON), re-querying")
            cached = None
        if cached is not None:
            # Record cache hit in stats
            try:
                from app.cache.redis_client import get_redis
                from app.api.rag_stats import STATS_PREFIX
                redis = get_redis()
                if redis:
                    await redis.incr(f"{STATS_PREFIX}:cache_hits")
            except Exception:
                pass
            return RAGQueryResponse(answer=answer, sources=sources)

    # Cache miss: run RAG pipeline（避免阻塞事件循环）
    import asyncio
    result = await asyncio.to_thread(rag_query, query, llm_call_fn, top_k, use_mmr, lang, filter_lang)

    # Cache the result in both exact and semantic caches
    cache_data = json.dumps({"answer": result.answer, "sources": [s.model_dump() for s in result.sources]})
    await set_cached_with_semantic(
        query=query,
        response=cache_data,
        model=model or settings.llm_model,
        temperature=0.0,
        max_tokens=500,
        ttl=3600,
    )

    # Record cache miss in stats
    increment_cache_miss()
    try:
        from app.cache.redis_client import get_redis
        from app.api.rag_stats import STATS_PREFIX
        redis = get_redis()
        if redis:
            await redis.incr(f"{STATS_PREFIX}:cache_misses")
    except Exception:
        pass

    return result


def run_incremental_index(filepath: str) -> dict:
    """Incremental index for a single uploaded file.

    Loads → splits → adds to existing Chroma collection (does NOT rebuild).
    """
    start = time.time()

    from app.rag.loader import load_single_document
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 1. Load single document
    doc = load_single_document(filepath)
    if not doc or not doc.get("content", "").strip():
        return {
            "status": "error",
            "filename": os.path.basename(filepath),
            "documents_indexed": 0,
            "chunks_created": 0,
            "elapsed_seconds": 0,
            "message": "文件为空或无法读取",
        }

    # 2. Split into parent-child structure
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
        separators=["\n", " ", ""],
    )

    parents = parent_splitter.split_text(doc["content"])
    chunks = []
    for parent_idx, parent_text in enumerate(parents):
        children = child_splitter.split_text(parent_text)
        for child_text in children:
            chunks.append({
                "text": child_text,
                "metadata": {
                    **doc["metadata"],
                    "parent_text": parent_text,
                    "parent_idx": parent_idx,
                },
            })

    # 3. 删除该文件的旧块，避免重复索引
    from app.rag.vector_store import add_to_index, delete_from_index
    filename = os.path.basename(filepath)
    delete_from_index(filename)
    logger.info("Deleted old chunks for '%s' before re-indexing", filename)

    # 4. Add to existing index (incremental)
    add_to_index(chunks)

    elapsed = time.time() - start
    fname = os.path.basename(filepath).encode("ascii", errors="replace").decode("ascii")
    logger.info("rag.incremental_index", file=fname, chunks=len(chunks), elapsed_s=round(elapsed, 1))

    return {
        "status": "ok",
        "filename": os.path.basename(filepath),
        "documents_indexed": 1,
        "chunks_created": len(chunks),
        "elapsed_seconds": round(elapsed, 1),
    }


# ── Contextual Retrieval: LLM-generated context prefixes ──
# Anthropic's technique: prepend each chunk with a brief context explaining
# its source document and position. Reduces retrieval errors by up to 49%.
# Reference: https://www.anthropic.com/news/contextual-retrieval

_CONTEXTUAL_PROMPT_TEMPLATE = """Generate a short context prefix (1-2 sentences) for the following text chunk. The prefix should explain:
1. Which document this chunk comes from (use the document title)
2. What topic/section this chunk covers within that document

Keep the prefix under 50 words. Write in the same language as the chunk (Chinese or English).

Document title: {title}
Full document (for reference):
{document}

Text chunk:
{chunk}

Context prefix:"""


async def _generate_context_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10):
    """并发生成 contextual prefixes。"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_one(chunk_text, doc_text):
        async with semaphore:
            prompt = f"""<document>
{doc_text}
</document>
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
            result = await asyncio.to_thread(llm_call_fn, [{"role": "user", "content": prompt}])
            return result if isinstance(result, str) else str(result)

    tasks = [_process_one(c, d) for c, d in chunks_with_docs]
    return await asyncio.gather(*tasks)


def _add_contextual_prefixes(
    chunks: List[Dict[str, Any]],
    docs: List[Dict[str, Any]],
    llm_call_fn,
    batch_size: int = 10,
) -> List[Dict[str, Any]]:
    """Add LLM-generated context prefixes to each chunk.

    For each chunk, generates a brief prefix explaining its source document
    and position within the document. The prefix is prepended to the chunk text
    for embedding, and stored in metadata for display.

    Uses concurrent LLM calls via _generate_context_prefixes_async
    for improved throughput compared to serial processing.

    Args:
        chunks: List of chunk dicts with "text" and "metadata" fields
        docs: List of document dicts with "metadata" and "content" fields
        llm_call_fn: LLM invocation function (messages -> response)
        batch_size: Number of chunks to process per LLM call (for efficiency)

    Returns:
        Chunks with contextual prefixes added to text and metadata
    """
    # Build doc lookup by slug
    doc_map = {doc["metadata"]["slug"]: doc for doc in docs}

    # Build (chunk_text, doc_text) pairs for concurrent processing
    chunks_with_docs = []
    valid_indices = []  # Track which chunks have a matching document
    for i, chunk in enumerate(chunks):
        slug = chunk["metadata"].get("slug", "")
        doc = doc_map.get(slug)
        if doc:
            doc_text = doc["content"][:2000]  # truncate for prompt
            chunk_text = chunk["text"][:300]  # truncate for prompt
            chunks_with_docs.append((chunk_text, doc_text))
            valid_indices.append(i)

    if not chunks_with_docs:
        return chunks

    # 并发生成 contextual prefixes
    prefixes = asyncio.run(_generate_context_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10))

    total_prefixes = 0
    for idx, prefix in zip(valid_indices, prefixes):
        prefix = prefix.strip()
        if prefix and len(prefix) < 200:  # sanity check
            chunks[idx]["metadata"]["contextual_prefix"] = prefix
            # Prepend prefix to text for embedding
            chunks[idx]["text"] = f"{prefix}\n\n{chunks[idx]['text']}"
            total_prefixes += 1

    logger.info("Contextual Retrieval: added %d prefixes to %d chunks", total_prefixes, len(chunks))
    return chunks


def run_index_pipeline(
    articles_dir: str,
    llm_call_fn = None,
    enable_contextual: bool = True,
) -> dict:
    """Full index pipeline: load → split → [contextual prefix] → embed → store.

    When enable_contextual=True and llm_call_fn is provided, each chunk gets
    an LLM-generated context prefix explaining its source document and position.
    This is Anthropic's Contextual Retrieval technique — reduces retrieval errors
    by up to 49% (https://www.anthropic.com/news/contextual-retrieval).
    """
    start = time.time()

    from app.rag.loader import load_markdown_files
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 1. Load
    docs = load_markdown_files(articles_dir)
    if not docs:
        return {
            "status": "error",
            "documents_indexed": 0,
            "chunks_created": 0,
            "elapsed_seconds": 0,
            "message": "没有找到 Markdown 文件",
        }

    # 2. Split into parent-child structure
    # Parent: 1500 chars (rich context for LLM)
    # Child:  512 chars (small chunks for precise retrieval)
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=50,
        separators=["\n", " ", ""],
    )

    chunks = []
    for doc in docs:
        parents = parent_splitter.split_text(doc["content"])
        for parent_idx, parent_text in enumerate(parents):
            # Use semantic chunking if enabled, otherwise fixed-size splitting
            if SEMANTIC_CHUNKING_ENABLED:
                try:
                    from app.rag.semantic_splitter import SemanticTextSplitter
                    from app.rag.vector_store import embed_texts_as_list
                    semantic_splitter = SemanticTextSplitter(
                        embed_fn=embed_texts_as_list,
                        breakpoint_threshold=80.0,
                        max_chunk_size=800,
                        min_chunk_size=100,
                    )
                    children = semantic_splitter.split_text(parent_text)
                except Exception as e:
                    logger.warning("Semantic chunking failed for parent %d: %s, falling back to fixed", parent_idx, e)
                    children = child_splitter.split_text(parent_text)
            else:
                children = child_splitter.split_text(parent_text)
            for child_text in children:
                chunks.append({
                    "text": child_text,
                    "metadata": {
                        **doc["metadata"],
                        "parent_text": parent_text,
                        "parent_idx": parent_idx,
                    },
                })

    # 3. Contextual Retrieval: add LLM-generated context prefix to each chunk
    contextual_count = 0
    if enable_contextual and llm_call_fn and chunks:
        chunks = _add_contextual_prefixes(chunks, docs, llm_call_fn)
        contextual_count = sum(1 for c in chunks if c.get("metadata", {}).get("contextual_prefix"))

    # 4. Embed (text includes contextual prefix if enabled)
    texts_to_embed = [c["text"] for c in chunks]
    embeddings = embed_texts_llm(texts_to_embed)

    # 5. Store
    save_index(chunks, embeddings)

    elapsed = time.time() - start
    logger.info("rag.index_complete", docs=len(docs), chunks=len(chunks), contextual=contextual_count, elapsed_s=round(elapsed, 1))

    return {
        "status": "ok",
        "documents_indexed": len(docs),
        "chunks_created": len(chunks),
        "contextual_prefixes": contextual_count,
        "elapsed_seconds": round(elapsed, 1),
    }


# ── Async RAG Pipeline ──
# Parallel BM25 + Vector retrieval via asyncio.gather


async def generate_answer_async(
    query: str,
    context: str,
    llm_call_fn,
    system_prompt: str = None,
    lang: str = "zh",
) -> str:
    """Async version of generate_answer. Call LLM with context and query."""
    if system_prompt is None:
        system_prompt = QA_SYSTEM_PROMPT_EN if lang == "en" else QA_SYSTEM_PROMPT
    lang_instr = lang_instruction(lang).strip()
    prompt = system_prompt.format(context=context, lang_instruction=lang_instr)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
    ]
    return await llm_call_fn(messages)


async def hybrid_retrieve_async(
    query: str,
    top_k: int = 3,
    lang_filter: str = None,
) -> List[Dict[str, Any]]:
    """Async hybrid retrieval: BM25 + Vector in parallel via asyncio.gather.

    Runs BM25 keyword search and vector search concurrently,
    then fuses results with RRF. Includes all quality filters from sync version.

    Args:
        query: Query text
        top_k: Number of results to return
        lang_filter: Optional language filter

    Returns:
        List of top_k document chunks
    """
    import asyncio

    # Run both retrievers in parallel
    bm25_task = asyncio.to_thread(retrieve_keyword, query, top_k=top_k * _RETRIEVAL_MULTIPLIER, lang_filter=lang_filter)

    from app.config import settings
    if settings.vector_backend == "qdrant":
        vector_task = asyncio.to_thread(retrieve, query, top_k=top_k * _RETRIEVAL_MULTIPLIER, lang_filter=lang_filter)
    else:
        vector_task = asyncio.to_thread(retrieve, query, top_k=top_k * _RETRIEVAL_MULTIPLIER, use_mmr=False, lang_filter=lang_filter)

    bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)

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

    # RRF fusion with deduplication
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

    # Title/slug boost
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

    # Take candidates for diversity selection
    candidate_limit = min(len(ranked), max(_RERANK_CANDIDATES, top_k * 3))
    candidates = []
    for key, score in ranked[:candidate_limit]:
        doc = doc_map[key].copy()
        doc["score"] = score
        candidates.append(doc)

    # ── Adaptive Re-ranking based on Query Complexity ──
    if _ADAPTIVE_RERANK_ENABLED and len(candidates) > top_k:
        try:
            strategy = get_reranking_strategy(query)
            complexity = strategy["complexity"]

            if complexity == "simple":
                logger.info("Adaptive rerank: SKIP (simple query)")
            elif complexity == "medium":
                logger.info("Adaptive rerank: SINGLE_BGE (medium)")
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
            elif complexity == "complex" and _ENSEMBLE_RERANK_ENABLED:
                logger.info("Adaptive rerank: ENSEMBLE (complex)")
                ensemble = get_ensemble_reranker()
                candidates = await ensemble.rerank(query, candidates, top_k=min(len(candidates), top_k * 3))
            else:
                logger.info("Adaptive rerank: SINGLE_BGE (default)")
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
        except Exception as e:
            logger.warning("Adaptive re-ranking failed, using RRF candidates as-is: %s", e)

    # Diversity selection for cross-article queries
    if is_cross_article_query(query):
        selected = []
        seen_slugs = set()
        for doc in candidates:
            slug = doc.get("metadata", {}).get("slug", "")
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                selected.append(doc)
                if len(selected) >= top_k:
                    break
        if len(selected) < top_k:
            for doc in candidates:
                if doc not in selected:
                    selected.append(doc)
                    if len(selected) >= top_k:
                        break
    else:
        selected = candidates[:top_k]

    # Relevance gate
    if selected and selected[0].get("score", 0) < _MIN_RELEVANCE_SCORE:
        logger.info("All results below relevance threshold (max=%.4f < %.4f), returning empty",
                     selected[0]["score"], _MIN_RELEVANCE_SCORE)
        return []

    return selected


async def rag_query_async(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    lang: str | None = None,
    filter_lang: str | None = None,
    chunking_strategy: str = "default",
    request_id: str = None,
) -> RAGQueryResponse:
    """Async RAG pipeline: retrieve (parallel) -> compress -> generate.

    Uses asyncio.gather for parallel BM25 + vector retrieval.

    Args:
        query: Query text
        llm_call_fn: LLM call function (can be sync or async)
        top_k: Number of results
        lang: Response language
        filter_lang: Document language filter
        chunking_strategy: Chunking strategy to use:
            - "default": Use existing chunking (parent-child from index pipeline)
            - "parent_child": Explicitly use ParentChildSplitter for document splitting
        request_id: Optional request ID for tracing
    """
    import asyncio
    from app.observability import QueryTracer
    from app.observability.tracing import create_span

    # Initialize tracer if request_id provided
    tracer = QueryTracer(request_id=request_id or '', query=query) if request_id else None

    if lang is None:
        lang = detect_language(query)

    # If parent_child strategy requested, apply it at query time for
    # ad-hoc documents. For pre-indexed data, the strategy was applied
    # during indexing (run_index_pipeline already uses parent-child).
    if chunking_strategy == "parent_child":
        logger.info("Using parent_child chunking strategy for query: %s", query[:50])

    # 1. Parallel retrieval (with tracing span)
    with create_span("retrieval", {"query_length": len(query), "top_k": top_k}) as retrieval_span:
        #    If HyDE is enabled, use hypothetical answer for retrieval
        if _HYDE_ENABLED:
            logger.info("HyDE enabled (async): using hypothetical answer for retrieval")
            chunks = await hyde_retrieve_async(
                query,
                llm_call_fn,
                top_k=top_k,
                lang=lang,
                lang_filter=filter_lang,
            )
            # If HyDE returns poor results, fallback to hybrid_retrieve_async
            if chunks:
                top_score = max(c.get("score", 0) for c in chunks)
                if top_score < _HYDE_FALLBACK_THRESHOLD:
                    logger.info(
                        "HyDE async: poor results (score=%.4f < %.4f), falling back to hybrid retrieval",
                        top_score, _HYDE_FALLBACK_THRESHOLD,
                    )
                    chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)
            else:
                logger.info("HyDE async: no results, falling back to hybrid retrieval")
                chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)
        else:
            chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)
        if retrieval_span is not None:
            retrieval_span.set_attribute("chunk_count", len(chunks))

    # 2. Negative detection: LLM classifier for queries the KB can't answer.
    if _NEGATIVE_DETECTION_ENABLED and chunks:
        top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
        if top_score < _HIGH_SCORE_SKIP_THRESHOLD:
            if not await asyncio.to_thread(classify_query_answerable_sync, query, llm_call_fn):
                return RAGQueryResponse(
                    answer=(
                        "抱歉，该问题超出了知识库的覆盖范围。"
                        if lang == "zh"
                        else "Sorry, this question is outside the scope of the knowledge base."
                    ),
                    sources=[],
                )
        else:
            logger.info("Skipping negative detection (top_score=%.4f >= %.4f)", top_score, _HIGH_SCORE_SKIP_THRESHOLD)

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Context compression (with tracing span)
    with create_span("compression", {"input_chunk_count": len(chunks)}) as compression_span:
        if chunks:
            chunks = await asyncio.to_thread(compress_context, query, chunks)
        if compression_span is not None:
            compression_span.set_attribute("output_chunk_count", len(chunks))

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Format context
    context = format_context(chunks)

    # 4. Generate (with tracing span)
    with create_span("llm_generation", {"context_length": len(context)}) as llm_span:
        if asyncio.iscoroutinefunction(llm_call_fn):
            answer = await generate_answer_async(query, context, llm_call_fn, lang=lang)
        else:
            answer = generate_answer(query, context, llm_call_fn, lang=lang)
        if llm_span is not None:
            llm_span.set_attribute("answer_length", len(answer))

    # 5. Build response
    sources = [
        SourceItem(
            title=c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
            slug=c["metadata"].get("slug", ""),
            chunk=c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
            score=c.get("score"),
            chunk_id=c.get("id", c["metadata"].get("chunk_id", "")),
            chunk_text_snippet=c["text"][:200],
        )
        for c in chunks
    ]

    # 6. Record trace if tracer is active
    if tracer:
        tracer.end_retrieval([{"chunk_id": s.chunk_id, "title": s.title, "slug": s.slug} for s in sources])
        tracer.end_rerank([{"chunk_id": s.chunk_id, "title": s.title} for s in sources])
        tracer.record()

    return RAGQueryResponse(answer=answer, sources=sources)
