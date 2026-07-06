"""
Answer generation and query orchestration for RAG system.
Contains: generate_answer, rag_query, rag_query_astream, rag_query_with_cache.
"""

import json
import asyncio
import re
import time
from pathlib import Path

from app.rag.vector_store import format_context
from app.rag.query_rewriter import expand_queries_rules, hyde_retrieve
from app.rag.models import RAGQueryResponse, SourceItem
from app.rag.classifier import (
    compress_context,
    _deduplicate_chunks,
    classify_query_answerable,
    classify_query_answerable_sync,
    _NEGATIVE_DETECTION_ENABLED,
    _CONTEXT_COMPRESSION_THRESHOLD,
)
from app.rag.retriever import multi_query_retrieve, hybrid_retrieve
from app.utils.lang_detect import detect_language, lang_instruction
from app.config import settings
from app.rag._pipeline import should_use_hyde, should_skip_negative_detection
from app.observability.prompt_manager import register_prompt, get_prompt

import structlog

logger = structlog.get_logger()

# ── HyDE settings ──
_HYDE_ENABLED = settings.hyde_enabled
_HYDE_FALLBACK_THRESHOLD = settings.hyde_fallback_threshold

# ── Context compression (for CRAG retry threshold) ──
_CONTEXT_COMPRESSION_ENABLED = settings.context_compression_enabled

# ── Generation quality feedback ──
_UNANSWERABLE_PATTERNS = [
    "文档中未提及", "无法回答", "知识库中不包含",
    "我没有找到相关信息", "无法从提供的上下文中",
    "没有找到相关", "无法提供",
]

_FEEDBACK_LOG = Path("data/feedback_log.jsonl")


def _is_exact_lookup_query(query: str) -> bool:
    tokens = re.findall(r"[A-Za-z0-9][A-Za-z0-9_.-]{5,}", query)
    return any(any(ch.isdigit() for ch in token) or "_" in token or "-" in token for token in tokens)


def _promote_exact_lookup_chunks(query: str, chunks: list[dict], top_k: int) -> list[dict]:
    needle = query.strip().lower()

    def _rank_key(chunk: dict) -> tuple[int, float]:
        meta = chunk.get("metadata", {}) or {}
        haystack = " ".join([
            chunk.get("text", "") or "",
            str(meta.get("title", "")),
            str(meta.get("source", "")),
            str(meta.get("slug", "")),
        ]).lower()
        exact_match = 0 if needle and needle in haystack else 1
        return (exact_match, -float(chunk.get("score", 0) or 0))

    return sorted(chunks, key=_rank_key)[:top_k]


def _check_unanswerable(response_text: str) -> bool:
    """检查 LLM 输出是否表示无法回答。"""
    return any(p in response_text for p in _UNANSWERABLE_PATTERNS)


def _log_feedback(query: str, top_score: float, action: str, answer: str = ""):
    """记录检索-生成反馈，供后续分析（异步非阻塞）。"""
    entry = {
        "timestamp": time.time(),
        "query": query[:200],
        "top_score": top_score,
        "action": action,  # "retry" | "accepted" | "no_result"
        "answer_preview": answer[:100],
    }
    # Fire-and-forget: 不阻塞流式响应的 TTFT
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_async_log_feedback(entry))
        _feedback_tasks.add(task)
        task.add_done_callback(_feedback_tasks.discard)
    except RuntimeError:
        # 无事件循环（同步上下文）→ 降级同步写入
        _sync_log_feedback(entry)


_feedback_tasks: set = set()


async def _async_log_feedback(entry: dict):
    """异步写入反馈日志，失败不影响主流程。"""
    try:
        await asyncio.to_thread(_sync_log_feedback, entry)
    except Exception as e:
        logger.warning("feedback_log_write_failed", error=str(e))


def _sync_log_feedback(entry: dict):
    """同步写入反馈日志。"""
    _FEEDBACK_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_FEEDBACK_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


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

## 完整性要求
- 如果参考文档中包含多个相关要点，必须全部列出，不要遗漏
- 列表型问题（如"步骤有哪些"、"包含哪些"）必须逐条回答
- 不要因为字数限制而省略关键信息

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

## Completeness Requirements
- If the reference documents contain multiple relevant points, list ALL of them — do not omit any
- For list-type questions (e.g., "what are the steps", "what does it include"), answer item by item
- Do not omit key information due to length constraints

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


# 注册到 Prompt Manager（LangFuse 可用时会覆盖）
register_prompt("qa_system_prompt_zh", QA_SYSTEM_PROMPT, "RAG 中文系统提示词")
register_prompt("qa_system_prompt_en", QA_SYSTEM_PROMPT_EN, "RAG 英文系统提示词")

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
        if lang == "en":
            system_prompt = get_prompt("qa_system_prompt_en", QA_SYSTEM_PROMPT_EN)
        else:
            system_prompt = get_prompt("qa_system_prompt_zh", QA_SYSTEM_PROMPT)
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
    top_k: int = 12,
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

    _t0 = time.time()
    _pipeline_stages: dict[str, float] = {}

    # 1. Hybrid retrieval: BM25 keyword + vector search, RRF fusion
    #    HyDE only for medium/complex queries (skip for simple to save latency)
    from app.rag.query_classifier import route_retrieval
    route = route_retrieval(query)

    if _is_exact_lookup_query(query):
        logger.info("Exact lookup query detected: skipping HyDE and query rewrite")
        chunks = hybrid_retrieve(
            query,
            top_k=max(top_k, 10),
            lang_filter=filter_lang,
            query_complexity="simple",
        )
        chunks = _promote_exact_lookup_chunks(query, chunks, top_k)
    elif should_use_hyde(route):
        logger.info("HyDE enabled for %s query: using hypothetical answer for retrieval", route)
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
        if _HYDE_ENABLED:
            logger.info("HyDE skipped: simple query (latency priority)")
        chunks = multi_query_retrieve(query, top_k=top_k, lang_filter=filter_lang)

    # 2. Negative detection: LLM classifier for queries the KB can't answer.
    #    Skip when top RRF score is high (confident retrieval) to save LLM calls.
    #    For production, consider adding a score >= 0.1 fast-path to skip
    #    classification when retrieval confidence is very high.
    if _NEGATIVE_DETECTION_ENABLED and chunks:
        top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
        if should_skip_negative_detection(top_score):
            logger.info("Skipping negative detection (top_score=%.4f >= %.4f)", top_score, settings.high_score_skip_threshold)
        elif not classify_query_answerable_sync(query, llm_call_fn):
            return RAGQueryResponse(
                answer=(
                    "抱歉，该问题超出了知识库的覆盖范围。"
                    if lang == "zh"
                    else "Sorry, this question is outside the scope of the knowledge base."
                ),
                sources=[],
            )

    # 1b. Context compression: filter chunks by embedding similarity to query
    #     Skip for simple queries with high retrieval confidence (already optimal)
    top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
    if chunks:
        # 简单查询 + 中等置信度 → 跳过 compression（节省 ~1-2s embedding API 调用）
        if route == "simple" and top_score >= 0.3:
            logger.info("Skipping context compression: simple query, top_score=%.4f", top_score)
        else:
            chunks = compress_context(query, chunks)
            if chunks:
                chunks = _deduplicate_chunks(chunks, threshold=0.80)

    # 1c. CRAG self-correction: if compression removed all chunks or top score is low,
    #     rewrite query and re-retrieve once (lightweight corrective RAG).
    #     Skip when retrieval confidence is high (top_score >= 0.5).
    if chunks:
        top_compression = max(c.get("compression_score", 1.0) for c in chunks)
    else:
        top_compression = 0.0

    # 高置信度跳过 CRAG retry（top_score 已经很高，不需要重新检索）
    if top_score >= 0.5:
        logger.info("Skipping CRAG retry: high confidence (top_score=%.4f)", top_score)
    elif not chunks or top_compression < _CONTEXT_COMPRESSION_THRESHOLD * 1.2:
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
                    retry_chunks = _deduplicate_chunks(retry_chunks, threshold=0.85)
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

    # 记录检索阶段耗时（含 rerank）
    _pipeline_stages["retrieval_ms"] = round((time.time() - _t0) * 1000, 1)

    # 2. Format context
    context = format_context(chunks)

    # 3. Generate
    _t_gen = time.time()
    answer = generate_answer(query, context, llm_call_fn, lang=lang)
    _pipeline_stages["generation_ms"] = round((time.time() - _t_gen) * 1000, 1)

    # 记录流水线阶段延迟到 metrics collector
    try:
        from app.observability.metrics_collector import set_latest_pipeline
        from app.multi_tenant.middleware import get_current_tenant_id
        set_latest_pipeline(get_current_tenant_id(), _pipeline_stages)
    except Exception:
        pass

    # 轻量级生成质量反馈
    top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
    if _check_unanswerable(answer):
        if top_score > 0.3:
            # 检索到了相关内容但 LLM 没用上
            _log_feedback(query, top_score, "retry", answer)
            logger.info("unanswerable_with_relevant_context", top_score=top_score, query=query[:100])
        else:
            # 确实无相关信息
            _log_feedback(query, top_score, "no_result", answer)
    else:
        _log_feedback(query, top_score, "accepted", answer)

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
    top_k: int = 12,
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

    # 1. 根据查询复杂度路由检索策略（自适应混合分类器：规则 + LLM 兜底）
    from app.rag.query_classifier import route_retrieval_adaptive

    exact_lookup = _is_exact_lookup_query(query)
    if exact_lookup:
        route = "simple"
        logger.info("Exact lookup query detected in stream: skipping HyDE and query rewrite")
        chunks = await asyncio.to_thread(
            hybrid_retrieve, query, top_k=max(top_k, 10), lang_filter=filter_lang, query_complexity=route
        )
        chunks = _promote_exact_lookup_chunks(query, chunks, top_k)
    else:
        route = await route_retrieval_adaptive(query)

        if route == "simple":
            # 简单查询：hybrid retrieve（dense+sparse + title boost + rerank）
            # 不再只用 sparse/keyword，因为语义匹配对很多查询至关重要
            chunks = await asyncio.to_thread(
                hybrid_retrieve, query, top_k=top_k, lang_filter=filter_lang, query_complexity=route
            )
        elif route == "medium":
            # 中等查询：hybrid retrieve（不含 multi_query）
            chunks = await asyncio.to_thread(
                hybrid_retrieve, query, top_k=top_k, lang_filter=filter_lang, query_complexity=route
            )
        else:
            # 复杂查询：完整 pipeline + HyDE
            if should_use_hyde(route):
                logger.info("HyDE enabled for complex query in streaming mode")
                from app.rag.query_rewriter import hyde_retrieve_async
                async def _llm_call_fn(messages):
                    resp = await llm.ainvoke(messages)
                    return resp
                chunks = await hyde_retrieve_async(query, _llm_call_fn, top_k=top_k, lang=lang, lang_filter=filter_lang)
                if not chunks:
                    logger.info("HyDE: no results in streaming, falling back to multi_query")
                    chunks = await asyncio.to_thread(multi_query_retrieve, query, top_k=top_k, lang_filter=filter_lang)
            else:
                chunks = await asyncio.to_thread(multi_query_retrieve, query, top_k=top_k, lang_filter=filter_lang)

    # 2. 轻量 CRAG 评估（基于检索分数，无需 LLM 调用）
    #    "incorrect" → 仅在 top score 极低时拒绝，否则降级为 ambiguous 继续生成
    if settings.crag_enabled and chunks:
        from app.rag.retrieval_confidence import lightweight_crag_assess
        assessment = lightweight_crag_assess(
            chunks,
            high_threshold=settings.crag_high_confidence,
            low_threshold=settings.crag_low_confidence,
        )
        if assessment == "incorrect":
            top_cr = max(c.get("score", 0) for c in chunks) if chunks else 0
            if top_cr < 0.05:
                # 极低置信度 → 真正无相关内容
                no_result_msg = (
                    "No relevant content found in the knowledge base. Please try a different question."
                    if lang == "en"
                    else "知识库中暂无相关内容，请尝试其他问题。"
                )
                yield {"type": "sources", "sources": []}
                yield {"type": "text", "content": no_result_msg}
                return
            else:
                logger.info("CRAG: low confidence (top_score=%.4f), continuing with disclaimer", top_cr)
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
        if should_skip_negative_detection(top_score):
            logger.info("Skipping negative detection (top_score=%.4f >= %.4f)", top_score, settings.high_score_skip_threshold)
        else:
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

    # 1b. Context compression: filter chunks by embedding similarity to query
    #     Skip for simple queries with high retrieval confidence (already optimal)
    #     Fallback: if compression removes all chunks, keep originals (avoid empty sources)
    if chunks:
        top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
        # 简单查询 + 中等置信度 → 跳过 compression（节省 ~1-2s embedding API 调用）
        if route == "simple" and top_score >= 0.3:
            logger.info("Skipping context compression: simple query, top_score=%.4f", top_score)
        else:
            pre_compression_chunks = chunks  # 保留原始 chunks 作为 fallback
            chunks = await asyncio.to_thread(compress_context, query, chunks)
            if chunks:
                chunks = _deduplicate_chunks(chunks, threshold=0.85)
            elif pre_compression_chunks:
                # Compression 移除了所有 chunks → 使用原始结果（避免丢失 sources）
                logger.warning("Context compression removed all %d chunks, falling back to originals",
                               len(pre_compression_chunks))
                chunks = pre_compression_chunks

    # 2. Format context
    context = format_context(chunks)

    # 3. Build message
    if lang == "en":
        system_prompt = get_prompt("qa_system_prompt_en", QA_SYSTEM_PROMPT_EN)
    else:
        system_prompt = get_prompt("qa_system_prompt_zh", QA_SYSTEM_PROMPT)
    lang_instr = lang_instruction(lang).strip()
    prompt = system_prompt.format(context=context, lang_instruction=lang_instr)

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
    ]

    # 4. Yield sources event first
    #    确保 score 始终为数值（避免前端因 score=null 不显示分数条）
    sources_data = [
        {
            "title": c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
            "slug": c["metadata"].get("slug", ""),
            "score": c.get("score") if c.get("score") is not None else 0.0,
            "chunk_id": c.get("id", c["metadata"].get("chunk_id", "")),
            "chunk_text_snippet": c["text"],
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
                "score": c.get("score") if c.get("score") is not None else 0.0,
            },
        }

    # 5. Stream LLM tokens
    full_answer_parts: list[str] = []
    async for chunk in llm.astream(messages):
        content = chunk.content if hasattr(chunk, "content") else ""
        if content:
            full_answer_parts.append(content)
            yield {"type": "text", "content": content}

    # 轻量级生成质量反馈
    full_answer = "".join(full_answer_parts)
    top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
    if _check_unanswerable(full_answer):
        if top_score > 0.3:
            # 检索到了相关内容但 LLM 没用上
            _log_feedback(query, top_score, "retry", full_answer)
            logger.info("unanswerable_with_relevant_context", top_score=top_score, query=query[:100])
        else:
            # 确实无相关信息
            _log_feedback(query, top_score, "no_result", full_answer)
    else:
        _log_feedback(query, top_score, "accepted", full_answer)


async def rag_query_with_cache(
    query: str,
    llm_call_fn,
    top_k: int = 12,
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
            except Exception as e:
                logger.debug("cache_hit_stats_increment_failed", error=str(e))
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
    except Exception as e:
        logger.debug("cache_miss_stats_increment_failed", error=str(e))

    return result
