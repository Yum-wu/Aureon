"""
Query complexity classifier for adaptive re-ranking.
Rule-based classification with <1ms latency (no LLM calls).
"""

from typing import Literal, Dict, Any
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


def classify_query_complexity(query: str) -> QueryComplexity:
    """Classify query complexity based on linguistic features.

    Uses rule-based classification for <1ms latency (no LLM calls).

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
