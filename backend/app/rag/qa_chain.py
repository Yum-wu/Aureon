"""
QA chain for RAG system.
Retrieves relevant context and generates answers using LLM.
"""

import json
import time
import os
from typing import List, Dict, Any, Optional

from app.rag.vector_store import retrieve, retrieve_keyword, format_context, save_index, embed_texts_llm, load_index, rerank
from app.rag.query_rewriter import is_cross_article_query, expand_queries_rules
from app.rag.models import RAGQueryResponse, SourceItem
from app.utils.lang_detect import detect_language, lang_instruction

import logging
import structlog

logger = structlog.get_logger()

_RRF_K = 60  # RRF constant (standard value from literature)
MULTI_QUERY_ENABLED = os.getenv("MULTI_QUERY_ENABLED", "true").lower() == "true"

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
_MIN_RELEVANCE_SCORE = float(os.getenv("MIN_RELEVANCE_SCORE", "0.015"))


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
    bm25_results = retrieve_keyword(query, top_k=top_k * 2, lang_filter=lang_filter)
    vector_results = retrieve(query, top_k=top_k * 2, use_mmr=False, lang_filter=lang_filter)

    # Use all vector results — quality check removed to avoid false discards
    # on small collections where cosine scores naturally cluster together

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
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank) * 1.1
        doc_map[key] = doc

    for rank, doc in enumerate(vector_deduped, 1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        if key not in doc_map:
            doc_map[key] = doc

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
    candidate_limit = min(len(ranked), max(top_k * 3, 10))
    candidates = []
    for key, score in ranked[:candidate_limit]:
        doc = doc_map[key].copy()
        doc["score"] = score
        candidates.append(doc)

    # Reranker disabled — RRF scores alone give better recall (93.9% vs 87.8%).
    # CRAG assessment in rag_query handles quality filtering.

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

    # Reranker is for ranking only — no score threshold here.
    # CRAG assessment (below) handles relevance filtering.

    # Relevance gate: if best RRF score is too low, both retrievers failed
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


# ── Retrieval Quality Assessment (CRAG-style) ──

_RETRIEVAL_ASSESSMENT_PROMPT = """判断以下文档能否回答用户的具体问题。

评分标准（只看能否回答，不看话题是否相关）：
- 5: 文档包含问题的明确答案
- 4: 文档包含相关信息但不完整
- 3: 文档提到相关话题但没有具体答案
- 2: 文档与问题话题相关但完全不包含答案
- 1: 文档与问题几乎无关
- 0: 文档完全无关

关键区分：如果问题是"X的Y是多少"，而文档只提到X但没有Y的信息，应该评2分。

只返回数字(0-5)，不要解释。

问题：{question}
文档：{documents}"""


def assess_retrieval_quality(query: str, chunks: List[Dict[str, Any]], llm_call_fn) -> int:
    """Assess whether retrieved chunks can answer the query. Returns 0-5 score.

    Uses a short LLM call to catch cases where the reranker passes irrelevant
    results due to vocabulary overlap (e.g., technical terms shared across articles).
    """
    if not chunks:
        return 0

    # Build short document summary (titles + first 100 chars of each chunk)
    doc_summary = "\n".join(
        f"[Doc {i+1}: {c['metadata'].get('title', 'Unknown')}] {c['text'][:100]}..."
        for i, c in enumerate(chunks[:3])
    )

    prompt = _RETRIEVAL_ASSESSMENT_PROMPT.format(question=query, documents=doc_summary)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = llm_call_fn(messages)
        # Extract number from response
        import re
        match = re.search(r'[0-5]', str(response).strip())
        if match:
            return int(match.group())
    except Exception as e:
        logger.warning("Retrieval assessment failed: %s", e)

    # Default: assume relevant (fail-open to avoid breaking valid queries)
    return 3


QA_SYSTEM_PROMPT = """你是知识库问答助手。基于提供的参考文档回答用户问题。

规则：
1. 只基于参考文档内容回答。参考文档中没有的信息，说"文档中未提及"。
2. 在回答末尾标注引用来源，格式：引用文章标题。
3. 如果问题与文档无关，礼貌说明无法回答。
4. 回答简洁准确。
{lang_instruction}

参考文档中每段以 [Source N: 文章标题] 开头。引用时用自然方式标注来源，例如：[来源: Hermes Agent 实战]。

参考文档：
{context}
"""

QA_SYSTEM_PROMPT_EN = """You are a knowledge base QA assistant. Answer user questions based on the provided reference documents.

Rules:
1. Only answer based on the reference documents. If information is not in the documents, say "not mentioned in the documents".
2. Cite sources at the end of your answer, format: article title.
3. If the question is unrelated to the documents, politely explain that you cannot answer.
4. Keep answers concise and accurate.
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


# ── Faithfulness Check (post-generation) ──

_FAITHFULNESS_PROMPT_ZH = """判断以下回答是否完全基于提供的参考文档。

规则：
1. 如果回答中的所有信息都能在参考文档中找到依据，返回 1.0
2. 如果回答包含文档中没有的信息（幻觉），返回 0.0
3. 如果回答说"文档中未提及"或"无法回答"，返回 1.0（这是诚实的回答）

只返回数字 (0.0 或 1.0)，不要解释。

参考文档：
{context}

用户问题：{query}
回答：{answer}"""

_FAITHFULNESS_PROMPT_EN = """Determine if the following answer is fully supported by the reference documents.

Rules:
1. If ALL information in the answer can be found in the reference documents, return 1.0
2. If the answer contains information NOT in the documents (hallucination), return 0.0
3. If the answer says "not mentioned" or "cannot answer", return 1.0 (honest response)

Return ONLY a number (0.0 or 1.0), no explanation.

Reference documents:
{context}

User question: {query}
Answer: {answer}"""


def check_faithfulness(query: str, answer: str, context: str, llm_call_fn, lang: str = "zh") -> float:
    """Verify that the generated answer is grounded in the retrieved context.

    Returns 1.0 if fully supported, 0.0 if hallucinated.
    Uses a single LLM call to check factual consistency.
    """
    prompt_template = _FAITHFULNESS_PROMPT_EN if lang == "en" else _FAITHFULNESS_PROMPT_ZH
    prompt = prompt_template.format(context=context[:1500], query=query, answer=answer[:500])
    messages = [{"role": "user", "content": prompt}]

    try:
        response = llm_call_fn(messages)
        import re
        match = re.search(r'(0\.0|1\.0|0|1)', str(response).strip())
        if match:
            return float(match.group())
    except Exception as e:
        logger.warning("Faithfulness check failed (fail-open): %s", e)

    return 1.0  # fail-open: assume faithful if check fails


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

    # 2. CRAG assessment disabled for production — too many false positives.
    #    The LLM scores even valid queries as "partially relevant" (3-4),
    #    and the strict threshold blocks legitimate searches.
    #    CRAG is kept for benchmark evaluation only.
    #    TODO: calibrate CRAG threshold after collecting production data.

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

    # 4. Faithfulness check: verify answer is grounded in context.
    #    Prevents hallucination when query is topically related but unanswerable.
    faithfulness = check_faithfulness(query, answer, context, llm_call_fn, lang=lang)
    if faithfulness < 0.5:
        logger.info("Faithfulness check failed (%.2f), returning no-answer for: %s",
                     faithfulness, query[:60])
        no_result_msg = (
            "Based on the available documents, I cannot provide a reliable answer to this question. Please try a different question."
            if lang == "en"
            else "根据现有文档，我无法可靠地回答这个问题。请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 5. Detect "cannot answer" responses — LLM correctly identified unanswerable query.
    #    Strip sources to avoid misleading the user.
    _NO_ANSWER_PATTERNS_ZH = ["未提及", "未找到", "无法回答", "没有提到", "没有相关信息"]
    _NO_ANSWER_PATTERNS_EN = ["not mentioned", "not found", "cannot answer", "no information"]
    answer_lower = answer.lower()
    is_no_answer = (
        any(p in answer for p in _NO_ANSWER_PATTERNS_ZH) or
        any(p in answer_lower for p in _NO_ANSWER_PATTERNS_EN)
    )
    if is_no_answer:
        return RAGQueryResponse(answer=answer, sources=[])

    # 6. Build response with sources
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
        chunk_size=300,
        chunk_overlap=30,
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


def run_index_pipeline(
    articles_dir: str,
    llm_call_fn = None,
) -> dict:
    """Full index pipeline: load → split → embed → store."""
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
    # Child:  300 chars (small chunks for precise retrieval)
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=300,
        chunk_overlap=30,
        separators=["\n", " ", ""],
    )

    chunks = []
    for doc in docs:
        parents = parent_splitter.split_text(doc["content"])
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

    # 3. Embed
    texts_to_embed = [c["text"] for c in chunks]
    embeddings = embed_texts_llm(texts_to_embed)

    # 4. Store
    save_index(chunks, embeddings)

    elapsed = time.time() - start
    print(f"[RAG] Index complete: {len(docs)} docs, {len(chunks)} chunks in {elapsed:.1f}s")

    return {
        "status": "ok",
        "documents_indexed": len(docs),
        "chunks_created": len(chunks),
        "elapsed_seconds": round(elapsed, 1),
    }
