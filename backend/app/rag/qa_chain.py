"""
QA chain for RAG system.
Retrieves relevant context and generates answers using LLM.
"""

import json
import time
import os
import numpy as np
from typing import List, Dict, Any, Optional

from app.rag.vector_store import retrieve, retrieve_keyword, format_context, save_index, embed_texts_llm, load_index, rerank
from app.rag.query_rewriter import is_cross_article_query, expand_queries_rules
from app.rag.models import RAGQueryResponse, SourceItem
from app.utils.lang_detect import detect_language, lang_instruction

import structlog

logger = structlog.get_logger()

_RRF_K = int(os.getenv("RRF_K", "200"))
_RETRIEVAL_MULTIPLIER = int(os.getenv("RETRIEVAL_MULTIPLIER", "7"))
_RERANK_CANDIDATES = int(os.getenv("RERANK_CANDIDATES", "12"))
_ADAPTIVE_RERANK_THRESHOLD = float(os.getenv("ADAPTIVE_RERANK_THRESHOLD", "0.5"))
MULTI_QUERY_ENABLED = os.getenv("MULTI_QUERY_ENABLED", "true").lower() == "true"
SEMANTIC_CHUNKING_ENABLED = os.getenv("SEMANTIC_CHUNKING_ENABLED", "true").lower() == "true"

# Keywords that uniquely identify specific articles — used for title/slug boost.
# Only terms that are specific enough to disambiguate between articles.
_TITLE_KEYWORDS_ZH = {
    "langgraph": "langgraph", "hermes": "hermes", "crewai": "crewai",
    "rag": "rag", "bm25": "bm25", "lcel": "lcel", "llamaindex": "llamaindex",
    "bge": "bge", "cross-encoder": "cross-encoder", "hyde": "hyde",
    "react": "react", "deepseek": "deepseek", "dashscope": "dashscope",
    "chromadb": "chromadb", "langchain": "langchain",
}


def _extract_title_keywords(query: str) -> List[str]:
    """Extract keywords from query that could uniquely identify an article."""
    q_lower = query.lower()
    return [kw for kw, normalized in _TITLE_KEYWORDS_ZH.items() if kw in q_lower]

# RRF score threshold: conservative floor — catches truly empty results.
# The reranker is the primary quality gate; this is just a safety net.
_MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.003"))

# Pre-RRF cosine threshold: filters vector results BEFORE fusion.
# RRF rank-1 = 1/(200+1) ≈ 0.005, so post-RRF thresholds are too low.
_VECTOR_MIN_COSINE = float(os.getenv("VECTOR_MIN_COSINE", "0.001"))

# Vector RRF contribution cap: limit how many vector results enter RRF fusion.
# Prevents low-confidence vector matches from drowning precise BM25 results.
_VECTOR_MAX_CONTRIB = int(os.getenv("VECTOR_MAX_CONTRIB", "10"))
_VECTOR_CONFIDENCE_THRESHOLD = float(os.getenv("VECTOR_CONFIDENCE_THRESHOLD", "0.01"))

# LLM-based negative detection: when top retrieval score is below this threshold,
# use an LLM classifier to decide if the query is answerable by the knowledge base.
_LOW_SCORE_THRESHOLD = float(os.getenv("LOW_SCORE_THRESHOLD", "0.004"))
_NEGATIVE_DETECTION_ENABLED = os.getenv("NEGATIVE_DETECTION_ENABLED", "true").lower() == "true"

# Context Compression: filter chunks by embedding similarity to query.
# Removes semantically irrelevant chunks before passing to LLM, reducing token waste 30-50%.
_CONTEXT_COMPRESSION_ENABLED = os.getenv("CONTEXT_COMPRESSION_ENABLED", "true").lower() == "true"
_CONTEXT_COMPRESSION_THRESHOLD = float(os.getenv("CONTEXT_COMPRESSION_THRESHOLD", "0.35"))


def compress_context(query: str, chunks: List[Dict[str, Any]], threshold: float = None) -> List[Dict[str, Any]]:
    """Filter chunks by embedding similarity to query (lightweight context compression).

    Computes cosine similarity between query embedding and each chunk embedding.
    Removes chunks below threshold to reduce token waste in LLM context.

    Uses GPU embedder when available for continuous GPU utilization.

    Args:
        query: User query text
        chunks: List of retrieved chunk dicts with 'text' field
        threshold: Minimum cosine similarity (default: _CONTEXT_COMPRESSION_THRESHOLD)

    Returns:
        Filtered list of chunks above threshold, sorted by similarity descending.
    """
    if not chunks or not _CONTEXT_COMPRESSION_ENABLED:
        return chunks

    if threshold is None:
        threshold = _CONTEXT_COMPRESSION_THRESHOLD

    try:
        # Embed query and chunks together for consistent embeddings
        texts = [query] + [c["text"] for c in chunks]

        # Try GPU embedder first for continuous GPU utilization
        embeddings = None
        try:
            from app.rag.vector_store import _get_gpu_embedder
            gpu_embedder = _get_gpu_embedder()
            if gpu_embedder is not None:
                embeddings = gpu_embedder.encode(texts, batch_size=len(texts))
        except Exception:
            pass

        if embeddings is None:
            embeddings = embed_texts_llm(texts)

        query_emb = embeddings[0]
        chunk_embs = embeddings[1:]

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
_HIGH_SCORE_SKIP_THRESHOLD = float(os.getenv("HIGH_SCORE_SKIP_THRESHOLD", "0.01"))


async def classify_query_answerable(query: str, model: str = None) -> bool:
    """Use LLM to determine if a query can be answered by the knowledge base."""
    # Fast-path: keyword heuristic before LLM call
    if _is_negative_by_keywords(query):
        return False

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
        return "YES" in response.content.upper()
    except Exception as e:
        logger.warning("LLM classifier failed: %s, defaulting to answerable", e)
        return True


# ── Negative detection: keyword fast-path ──
# Queries matching these patterns are almost certainly unanswerable by the KB.
# Checked BEFORE the LLM classifier to save API calls and improve accuracy.
_NEGATIVE_KEYWORDS_ZH = [
    "定价", "价格", "收费", "费用", "免费额度",
    "团队有多少人", "团队规模", "多少人",
    "训练数据量", "训练数据", "数据量是多少",
    "版本号", "最新版本", "当前版本",
    "什么时候发布", "发布时间", "发布日期",
    "毕业于", "教育背景", "学历",
    "创始人", "CEO", "公司地址",
]
_NEGATIVE_KEYWORDS_EN = [
    "pricing", "price", "cost", "how much",
    "team size", "how many people",
    "training data size", "training data volume",
    "version number", "latest version",
    "when was", "release date",
    "university", "education",
    "founder", "CEO", "headquarters",
]


def _is_negative_by_keywords(query: str) -> bool:
    """Fast heuristic: detect obviously unanswerable queries by keywords."""
    q = query.lower()
    for kw in _NEGATIVE_KEYWORDS_ZH:
        if kw in q:
            return True
    for kw in _NEGATIVE_KEYWORDS_EN:
        if kw in q:
            return True
    return False


def classify_query_answerable_sync(query: str, llm_call_fn) -> bool:
    """Sync version: use LLM to determine if a query can be answered by the knowledge base."""
    # Fast-path: keyword heuristic before LLM call
    if _is_negative_by_keywords(query):
        return False

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
        response = llm_call_fn([{"role": "user", "content": prompt}])
        return "YES" in str(response).upper()
    except Exception as e:
        logger.warning("Sync LLM classifier failed: %s, defaulting to answerable", e)
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

    # Adaptive Reranking: skip rerank when top-1 has high confidence
    if len(candidates) > top_k:
        top1_score = candidates[0].get("score", 0)
        top2_score = candidates[1].get("score", 0) if len(candidates) > 1 else 0
        score_gap = top1_score - top2_score if top1_score > 0 else 0
        gap_ratio = score_gap / top1_score if top1_score > 0 else 0

        if gap_ratio >= _ADAPTIVE_RERANK_THRESHOLD:
            logger.info(
                "Adaptive rerank: skipping (top1=%.4f, gap_ratio=%.2f >= %.2f threshold)",
                top1_score, gap_ratio, _ADAPTIVE_RERANK_THRESHOLD,
            )
        else:
            rerank_limit = max(top_k * 3, 10)
            candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))

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


QA_SYSTEM_PROMPT = """你是知识库问答助手。基于提供的参考文档回答用户问题。

规则：
1. 只基于参考文档内容回答。参考文档中没有的信息，说"文档中未提及"。
2. 回答必须直接针对用户问题，不要添加与问题无关的额外信息。
3. 如果问题与文档无关，礼貌说明无法回答。
4. 回答简洁准确，每个句子都必须直接回答用户的问题。
5. 在回答末尾标注引用来源，格式：[来源: 文章标题]。
{lang_instruction}

参考文档中每段以 [Source N: 文章标题] 开头。引用时用自然方式标注来源，例如：[来源: Hermes Agent 实战]。

参考文档：
{context}
"""

QA_SYSTEM_PROMPT_EN = """You are a knowledge base QA assistant. Answer user questions based on the provided reference documents.

Rules:
1. Only answer based on the reference documents. If information is not in the documents, say "not mentioned in the documents".
2. Your answer must directly address the user's question. Do not include information unrelated to the question.
3. If the question is unrelated to the documents, politely explain that you cannot answer.
4. Keep answers concise and focused. Every sentence must directly answer the user's question.
5. Cite sources at the end of your answer, format: [Source: Article Title].
{lang_instruction}

Each paragraph in the reference documents starts with [Source N: Article Title]. When citing, naturally mention the source, e.g., [Source: Hermes Agent in Practice].

Reference documents:
{context}
"""


def generate_answer(
    query: str,
    context: str,
    llm_call_fn,
    system_prompt: str = None,
    lang: str = "zh",
) -> str:
    """Call LLM with context and query. Return generated answer."""
    if system_prompt is None:
        system_prompt = QA_SYSTEM_PROMPT_EN if lang == "en" else QA_SYSTEM_PROMPT
    lang_instr = lang_instruction(lang).strip()
    prompt = system_prompt.format(context=context, lang_instruction=lang_instr)
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

    # 1. Hybrid retrieval: BM25 keyword + vector search, RRF fusion
    chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)

    # 2. CRAG assessment disabled — too many false positives on production.
    #    TODO: calibrate after collecting data.

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
    if chunks:
        chunks = compress_context(query, chunks)

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
) -> RAGQueryResponse:
    """RAG query with Redis semantic cache.

    On a cache hit returns the cached answer with sources (stored as JSON).
    On a miss, delegates to :func:`rag_query` and caches the result.
    Degrades gracefully when Redis is unavailable.
    """
    from app.cache.redis_client import get_cached, set_cached

    cached = await get_cached(query)
    if cached is not None:
        try:
            cached_data = json.loads(cached)
            answer = cached_data.get("answer", cached)
            sources = cached_data.get("sources", [])
            sources = [SourceItem(**s) for s in sources]
        except (json.JSONDecodeError, TypeError):
            answer = cached
            sources = []
        # Record cache hit
        try:
            from app.cache.redis_client import get_redis
            from app.api.rag_stats import STATS_PREFIX
            redis = get_redis()
            if redis:
                await redis.incr(f"{STATS_PREFIX}:cache_hits")
        except Exception:
            pass
        return RAGQueryResponse(answer=answer, sources=sources)

    result = rag_query(query, llm_call_fn, top_k, use_mmr, lang, filter_lang)
    cache_data = json.dumps({"answer": result.answer, "sources": [s.model_dump() for s in result.sources]})
    await set_cached(query, cache_data)

    # Record cache miss
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

    # 3. Add to existing index (incremental)
    from app.rag.vector_store import add_to_index
    add_to_index(chunks)

    elapsed = time.time() - start
    fname = os.path.basename(filepath).encode("ascii", errors="replace").decode("ascii")
    print(f"[RAG] Incremental index: {fname} -> {len(chunks)} chunks in {elapsed:.1f}s")

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

    # Group chunks by source document for batch processing
    doc_chunks: Dict[str, List[int]] = {}
    for i, chunk in enumerate(chunks):
        slug = chunk["metadata"].get("slug", "")
        if slug not in doc_chunks:
            doc_chunks[slug] = []
        doc_chunks[slug].append(i)

    total_prefixes = 0
    for slug, chunk_indices in doc_chunks.items():
        doc = doc_map.get(slug)
        if not doc:
            continue

        doc_title = doc["metadata"].get("title", slug)
        doc_content = doc["content"][:2000]  # truncate for prompt

        # Process chunks in batches
        for batch_start in range(0, len(chunk_indices), batch_size):
            batch_indices = chunk_indices[batch_start:batch_start + batch_size]

            for idx in batch_indices:
                chunk_text = chunks[idx]["text"][:300]  # truncate for prompt

                prompt = _CONTEXTUAL_PROMPT_TEMPLATE.format(
                    title=doc_title,
                    document=doc_content,
                    chunk=chunk_text,
                )

                try:
                    response = llm_call_fn([{"role": "user", "content": prompt}])
                    prefix = str(response).strip()
                    if prefix and len(prefix) < 200:  # sanity check
                        chunks[idx]["metadata"]["contextual_prefix"] = prefix
                        # Prepend prefix to text for embedding
                        chunks[idx]["text"] = f"{prefix}\n\n{chunks[idx]['text']}"
                        total_prefixes += 1
                except Exception as e:
                    logger.warning("Contextual prefix generation failed for chunk %d: %s", idx, e)

            logger.info("Contextual prefixes: %d/%d chunks processed for %s",
                       min(batch_start + batch_size, len(chunk_indices)),
                       len(chunk_indices), doc_title)

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
    print(f"[RAG] Index complete: {len(docs)} docs, {len(chunks)} chunks "
          f"({contextual_count} contextual) in {elapsed:.1f}s")

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

    # Adaptive Reranking: skip rerank when top-1 has high confidence
    # (large RRF score gap indicates clear winner already)
    if len(candidates) > top_k:
        top1_score = candidates[0].get("score", 0)
        top2_score = candidates[1].get("score", 0) if len(candidates) > 1 else 0
        score_gap = top1_score - top2_score if top1_score > 0 else 0
        gap_ratio = score_gap / top1_score if top1_score > 0 else 0

        if gap_ratio >= _ADAPTIVE_RERANK_THRESHOLD:
            logger.info(
                "Adaptive rerank: skipping (top1=%.4f, gap_ratio=%.2f >= %.2f threshold)",
                top1_score, gap_ratio, _ADAPTIVE_RERANK_THRESHOLD,
            )
            # Already well-ordered by RRF, skip CrossEncoder
        else:
            rerank_limit = max(top_k * 3, 10)
            candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))

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
) -> RAGQueryResponse:
    """Async RAG pipeline: retrieve (parallel) → compress → generate.

    Uses asyncio.gather for parallel BM25 + vector retrieval.

    Args:
        query: Query text
        llm_call_fn: LLM call function (can be sync or async)
        top_k: Number of results
        lang: Response language
        filter_lang: Document language filter
    """
    import asyncio

    if lang is None:
        lang = detect_language(query)

    # 1. Parallel retrieval
    chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)

    # 2. Negative detection: LLM classifier for queries the KB can't answer.
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

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Context compression
    if chunks:
        chunks = compress_context(query, chunks)

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Format context
    context = format_context(chunks)

    # 4. Generate (support both sync and async LLM)
    if asyncio.iscoroutinefunction(llm_call_fn):
        answer = await generate_answer_async(query, context, llm_call_fn, lang=lang)
    else:
        answer = generate_answer(query, context, llm_call_fn, lang=lang)

    # 5. Build response
    sources = [
        SourceItem(
            title=c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
            slug=c["metadata"].get("slug", ""),
            chunk=c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
            score=c.get("score"),
        )
        for c in chunks
    ]

    return RAGQueryResponse(answer=answer, sources=sources)
