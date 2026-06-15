"""
Answer generation and query orchestration for RAG system.
Contains: generate_answer, rag_query, rag_query_astream, rag_query_with_cache.
"""

import json
import asyncio

from app.rag.vector_store import format_context, retrieve_keyword
from app.rag.query_rewriter import expand_queries_rules, hyde_retrieve
from app.rag.models import RAGQueryResponse, SourceItem
from app.rag.classifier import (
    compress_context,
    classify_query_answerable,
    classify_query_answerable_sync,
    _NEGATIVE_DETECTION_ENABLED,
    _HIGH_SCORE_SKIP_THRESHOLD,
    _CONTEXT_COMPRESSION_THRESHOLD,
)
from app.rag.retriever import multi_query_retrieve, hybrid_retrieve
from app.utils.lang_detect import detect_language, lang_instruction
from app.config import settings

import structlog

logger = structlog.get_logger()

# ── HyDE settings ──
_HYDE_ENABLED = settings.hyde_enabled
_HYDE_FALLBACK_THRESHOLD = settings.hyde_fallback_threshold

# ── Context compression (for CRAG retry threshold) ──
_CONTEXT_COMPRESSION_ENABLED = settings.context_compression_enabled


QA_SYSTEM_PROMPT = """你是精准的知识库问答助手。你的唯一任务是回答用户的问题。

## 核心原则
- 先理解用户的问题意图，再从参考文档中提取答案
- 每个句子必须直接回应用户的问题
- 如果文档中有答案，直接给出答案
- 如果文档中没有答案，直接说"文档中未提及"

## 严格约束（必须遵守）
- **只使用参考文档中的信息回答问题**
- **禁止使用你的训练数据或外部知识**
- **如果参考文档中没有相关信息，必须回答"文档中未提及该信息"**
- **禁止推测、猜测或补充文档中没有的信息**

## 回答结构（必须遵守）
1. **直接回答**（1-2 句话，直接回答问题核心，控制在 200 字以内）
2. **补充细节**（仅当用户问题需要更详细解释时，不超过 500 字）
3. **引用来源**（格式：[来源: 文章标题]）

## 字数限制
- 总回答长度控制在 500 字以内
- 能用一句话回答的不要用两句话

## 禁止行为
- ? 禁止以"根据文档"、"文档介绍了"、"参考文档提到"开头
- ? 禁止复述文档内容而不回答问题
- ? 禁止添加用户未要求的背景信息
- ? 禁止使用"总的来说"、"综上所述"、"需要注意的是"等总结性语句
- ? 禁止在回答开头加前言或铺垫
- ? 禁止使用文档中没有的信息来补充答案

## 正确示例

用户问："BM25 的核心原理是什么？"
? 正确："BM25 通过词频饱和度和文档长度归一化计算关键词匹配分数，核心公式包含 TF（词频）和 IDF（逆文档频率）两个组件。[来源: RAG 优化实战]"
? 错误："文档介绍了 RAG 系统中使用的多种检索技术。BM25 是其中一种经典的排序算法，它的核心原理是..."

用户问："如何配置 Redis 缓存？"
? 正确："配置步骤：1) 安装 redis-py；2) 设置 REDIS_URL 环境变量；3) 在 config.py 中启用缓存层。[来源: Redis 集成指南]"
? 错误："Redis 是一个高性能的内存数据库，在 RAG 系统中常用于缓存。下面文档介绍了如何配置..."

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

## Strict Constraints (mandatory)
- **Only use information from the reference documents to answer questions**
- **Do NOT use your training data or external knowledge**
- **If the reference documents don't contain relevant information, you MUST answer "The documents do not contain information about this topic"**
- **Do NOT speculate, guess, or supplement information not present in the documents**

## Answer Structure (mandatory)
1. **Direct answer** (1-2 sentences, addressing the core question)
2. **Supporting details** (only when the user needs more explanation)
3. **Source citation** (format: [Source: Article Title])

## Prohibited Patterns
- ? Do NOT start with "Based on the documents", "The documents mention", "According to the reference"
- ? Do NOT summarize document content without answering the question
- ? Do NOT add background information the user didn't ask for
- ? Do NOT use "In summary", "To summarize", "It's worth noting" as transitions
- ? Do NOT add preamble or setup before the actual answer
- ? Do NOT supplement answers with information not in the documents

## Correct Examples

User: "What is the core principle of BM25?"
? Correct: "BM25 calculates keyword matching scores through term frequency saturation and document length normalization, with TF and IDF as its two core components. [Source: RAG Optimization Guide]"
? Wrong: "The documents describe various retrieval techniques used in RAG systems. BM25 is one of the classic ranking algorithms. Its core principle is..."

User: "How to configure Redis caching?"
? Correct: "Steps: 1) Install redis-py; 2) Set REDIS_URL environment variable; 3) Enable cache layer in config.py. [Source: Redis Integration Guide]"
? Wrong: "Redis is a high-performance in-memory database commonly used for caching in RAG systems. The following documents describe how to configure..."

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
            chunk_text_snippet=c["text"],  # 完整文本，供 benchmark 评估用
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
            "chunk_text_snippet": c["text"],  # 完整文本，供 benchmark 评估用
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
