"""
Query complexity classifier for adaptive re-ranking.
Rule-based classification with <1ms latency (no LLM calls).
Adaptive hybrid classifier: rule fast-path + LLM fallback for low-confidence queries.
"""

import asyncio
from typing import Literal, Dict, Any, Optional
import structlog

logger = structlog.get_logger()

# Query complexity labels
QueryComplexity = Literal["simple", "medium", "complex"]

# Keywords that indicate complex queries
ComplexityIndicators: Dict[str, list] = {
    "comparison": ["比较", "对比", "对比分析", "区别", "差异", "vs", "versus", "compare", "difference"],
    "reasoning": ["为什么", "原因", "解释", "分析", "评估", "why", "explain", "analyze", "evaluate"],
    "multi_step": ["步骤", "流程", "如何实现", "实现方法", "step", "process", "how to", "implementation"],
    "synthesis": ["总结", "综合", "概述", "全面", "summary", "synthesize", "overview", "comprehensive"],
}


def _count_keyword_matches(query: str) -> Dict[str, int]:
    """Count matches for each complexity indicator category."""
    q_lower = query.lower()
    matches = {}
    for category, keywords in ComplexityIndicators.items():
        matches[category] = sum(1 for kw in keywords if kw in q_lower)
    return matches


def _has_multiple_questions(query: str) -> bool:
    """Check if query contains multiple question marks or question patterns."""
    question_marks = query.count("?") + query.count("？")
    return question_marks > 1


def _get_query_length_score(query: str) -> int:
    """Score based on query length (longer = more complex)."""
    length = len(query)
    if length > 100:
        return 3
    elif length > 50:
        return 2
    elif length > 20:
        return 1
    else:
        return 0


def _has_conjunction_patterns(query: str) -> bool:
    """Check for multiple topics connected by conjunctions (indicating multi-part query)."""
    conjunctions_zh = ["并且", "同时", "而且", "也", "和", "与", "以及"]
    conjunctions_en = [" and ", " also ", " plus ", " as well as "]

    q_lower = query.lower()
    for conj in conjunctions_zh:
        if conj in query:
            return True
    for conj in conjunctions_en:
        if conj in q_lower:
            return True
    return False


def _rule_classify(query: str) -> Optional[QueryComplexity]:
    """规则分类，返回 None 表示低置信度需 LLM 兜底。

    高置信度条件（满足任一即返回结果）：
    - 匹配了 2+ 个复杂度关键词
    - 包含多个问号
    - 查询长度 > 50 且匹配了 1+ 关键词
    - 包含明确的比较+分析组合模式
    - 短查询（<=20 字符）且无关键词匹配 → simple（高置信度）

    低置信度条件（返回 None，需 LLM 兜底）：
    - 仅匹配 1 个关键词且查询长度 <= 50
    - 中等长度查询且无明确模式
    """
    if not query or not query.strip():
        return "simple"

    q = query.strip()

    # Initialize score
    score = 0

    # 1. Check keyword matches (major weight)
    keyword_matches = _count_keyword_matches(q)
    total_keywords = sum(keyword_matches.values())

    if total_keywords >= 2:
        score += 3
    elif total_keywords == 1:
        score += 2
    elif total_keywords > 0:
        score += 1

    # 2. Query length score
    length_score = _get_query_length_score(q)
    score += length_score

    # 3. Multiple question marks penalty (stronger indicator)
    has_multi_q = _has_multiple_questions(q)
    if has_multi_q:
        score += 2

    # 4. Conjunction patterns (multi-part query)
    has_conj = _has_conjunction_patterns(q)
    if has_conj:
        score += 1

    # 5. Special patterns for explicit complexity
    q_lower = q.lower()

    # Explicit comparison with analysis
    has_comparison_analysis = False
    if ("比较" in q or "对比" in q or "compare" in q_lower) and (
        "解释" in q or "分析" in q or "why" in q_lower or "explain" in q_lower or "evaluate" in q_lower
    ):
        score += 1
        has_comparison_analysis = True

    # Multi-step process description
    has_multi_step = False
    if ("步骤" in q or "流程" in q or "step" in q_lower or "process" in q_lower) and (
        "如何实现" in q or "实现方法" in q or "how to" in q_lower or "implementation" in q_lower
    ):
        score += 1
        has_multi_step = True

    # Comprehensive synthesis
    has_synthesis = False
    if ("总结" in q or "综合" in q or "summary" in q_lower or "synthesize" in q_lower) and len(q) > 60:
        score += 1
        has_synthesis = True

    # Classification thresholds
    if score >= 5:
        result = "complex"
    elif score >= 3:
        result = "medium"
    else:
        result = "simple"

    # ── 置信度评估 ──
    # 高置信度条件：明确匹配了复杂度指示器
    high_confidence = (
        total_keywords >= 2          # 2+ 关键词匹配
        or has_multi_q               # 多个问号
        or has_comparison_analysis   # 比较+分析组合
        or has_multi_step            # 多步骤模式
        or has_synthesis             # 综合总结模式
        or (len(q) <= 20 and total_keywords == 0)  # 短查询无关键词 → simple
        or (len(q) > 50 and total_keywords >= 1)    # 长查询+关键词
    )

    if high_confidence:
        logger.debug(
            "Rule classify: high confidence",
            query=q[:50],
            complexity=result,
            score=score,
            keywords=keyword_matches,
        )
        return result

    # 低置信度：返回 None，由 LLM 兜底
    logger.debug(
        "Rule classify: low confidence, needs LLM fallback",
        query=q[:50],
        rule_result=result,
        score=score,
        keywords=keyword_matches,
    )
    return None


def classify_query_complexity(query: str) -> QueryComplexity:
    """Classify query complexity based on linguistic features.

    Uses rule-based classification for <1ms latency (no LLM calls).
    This is the synchronous entry point — returns rule-based result only.
    For adaptive classification with LLM fallback, use
    ``classify_query_complexity_adaptive`` instead.

    Scoring:
    - Check for explicit complexity indicators (keywords)
    - Check query length (longer = more complex)
    - Check for multiple question marks
    - Check for comparison patterns
    - Check for conjunction patterns (multi-part queries)

    Args:
        query: Query text to classify

    Returns: "simple", "medium", or "complex"

    Examples:
        >>> classify_query_complexity("什么是RAG？")
        'simple'
        >>> classify_query_complexity("比较BM25和向量检索的优缺点，并解释为什么")
        'complex'
    """
    if not query or not query.strip():
        return "simple"

    q = query.strip()

    # Initialize score
    score = 0

    # 1. Check keyword matches (major weight)
    keyword_matches = _count_keyword_matches(q)
    total_keywords = sum(keyword_matches.values())

    if total_keywords >= 2:
        score += 3
    elif total_keywords == 1:
        score += 2
    elif total_keywords > 0:
        score += 1

    # 2. Query length score
    length_score = _get_query_length_score(q)
    score += length_score

    # 3. Multiple question marks penalty (stronger indicator)
    if _has_multiple_questions(q):
        score += 2

    # 4. Conjunction patterns (multi-part query)
    if _has_conjunction_patterns(q):
        score += 1

    # 5. Special patterns for explicit complexity
    q_lower = q.lower()

    # Explicit comparison with analysis
    if ("比较" in q or "对比" in q or "compare" in q_lower) and (
        "解释" in q or "分析" in q or "why" in q_lower or "explain" in q_lower or "evaluate" in q_lower
    ):
        score += 1

    # Multi-step process description
    if ("步骤" in q or "流程" in q or "step" in q_lower or "process" in q_lower) and (
        "如何实现" in q or "实现方法" in q or "how to" in q_lower or "implementation" in q_lower
    ):
        score += 1

    # Comprehensive synthesis
    if ("总结" in q or "综合" in q or "summary" in q_lower or "synthesize" in q_lower) and len(q) > 60:
        score += 1

    # Classification thresholds
    if score >= 5:
        result = "complex"
    elif score >= 3:
        result = "medium"
    else:
        result = "simple"

    logger.debug(
        "Query classified",
        query=q[:50],
        complexity=result,
        score=score,
        keywords=keyword_matches,
    )

    return result


def get_reranking_strategy(query: str) -> Dict[str, Any]:
    """Determine re-ranking strategy based on query complexity.

    Returns strategy configuration with:
    - complexity: Query complexity level
    - strategy: Re-ranking strategy to use
    - estimated_latency_ms: Expected latency for this strategy
    - reranker_count: Number of rerankers to use

    Strategies:
    - simple: skip (0ms latency)
    - medium: single_bge (30ms latency)
    - complex: ensemble (80ms latency)

    Args:
        query: Query text to determine strategy for

    Returns: Dict with strategy configuration

    Examples:
        >>> strategy = get_re-ranking_strategy("什么是RAG？")
        >>> strategy["strategy"]
        'skip'
        >>> strategy["reranker_count"]
        0
        >>> strategy = get_re-ranking_strategy("比较BM25和向量检索，并解释适用场景")
        >>> strategy["strategy"]
        'ensemble'
    """
    complexity = classify_query_complexity(query)

    strategies = {
        "simple": {
            "complexity": complexity,
            "strategy": "skip",
            "estimated_latency_ms": 0,
            "reranker_count": 0,
        },
        "medium": {
            "complexity": complexity,
            "strategy": "single_bge",
            "estimated_latency_ms": 30,
            "reranker_count": 1,
        },
        "complex": {
            "complexity": complexity,
            "strategy": "ensemble",
            "estimated_latency_ms": 80,
            "reranker_count": 3,
        },
    }

    strategy = strategies[complexity]

    logger.debug(
        "Re-ranking strategy selected",
        query=query[:50],
        complexity=complexity,
        strategy=strategy["strategy"],
        latency_ms=strategy["estimated_latency_ms"],
    )

    return strategy


def route_retrieval(query: str) -> str:
    """根据查询复杂度决定检索策略。

    Returns:
        "simple" — 纯 sparse/keyword 检索（<10ms）
        "medium" — hybrid retrieve（100-200ms）
        "complex" — multi_query + rerank（300-500ms）
    """
    from app.config import settings

    if not settings.query_routing_enabled:
        return "complex"  # 默认走完整 pipeline

    strategy = get_reranking_strategy(query)
    return strategy["complexity"]  # "simple", "medium", or "complex"


async def route_retrieval_adaptive(query: str) -> str:
    """根据查询复杂度决定检索策略（自适应混合分类器版本）。

    规则命中且高置信度 → 直接返回（<1ms）
    规则低置信度 → LLM 兜底（~200ms）
    LLM 超时/失败 → 降级为 medium

    Returns:
        "simple" — 纯 sparse/keyword 检索（<10ms）
        "medium" — hybrid retrieve（100-200ms）
        "complex" — multi_query + rerank（300-500ms）
    """
    from app.config import settings

    if not settings.query_routing_enabled:
        return "complex"  # 默认走完整 pipeline

    complexity = await classify_query_complexity_adaptive(query)
    return complexity


async def _llm_classify(query: str) -> str:
    """用小 LLM 分类查询复杂度。"""
    from app.agent.llm import create_llm
    llm = create_llm(temperature=0.0)

    prompt = f"""Classify this query's complexity for RAG retrieval:
- simple: factual lookup, single fact answer (e.g., "什么是RAG?")
- medium: requires analysis or comparison of 1-2 documents
- complex: multi-step reasoning, synthesis across 3+ documents

Query: {query}

Respond with ONLY one word: simple, medium, or complex"""

    response = await llm.ainvoke(prompt)
    result = response.content.strip().lower()
    # 剥离 thinking 标签（某些模型可能返回 <think>...</think>）
    import re
    result = re.sub(r'<think>.*?</think>', '', result, flags=re.DOTALL).strip()
    if result in ("simple", "medium", "complex"):
        return result
    return "medium"


async def classify_query_complexity_adaptive(query: str) -> QueryComplexity:
    """混合分类器：规则快速路径 + LLM 兜底。

    规则命中且高置信度 → 直接返回（<1ms）
    规则低置信度 → LLM 兜底（~200ms）
    LLM 超时/失败 → 降级为 medium
    """
    # 1. 规则快速路径
    result = _rule_classify(query)
    if result is not None:
        return result  # 规则高置信度，直接返回

    # 2. LLM 兜底（低置信度查询）
    try:
        result = await asyncio.wait_for(
            _llm_classify(query), timeout=0.5
        )
        if result in ("simple", "medium", "complex"):
            logger.debug(
                "LLM classify: fallback result",
                query=query[:50],
                complexity=result,
            )
            return result
    except asyncio.TimeoutError:
        logger.debug("query_classifier_llm_fallback_timeout", query=query[:50])
    except Exception as e:
        logger.debug("query_classifier_llm_fallback_failed", error=str(e), query=query[:50])

    # 3. 超时降级为 medium（安全默认）
    logger.debug("query_classifier_fallback_to_medium", query=query[:50])
    return "medium"
