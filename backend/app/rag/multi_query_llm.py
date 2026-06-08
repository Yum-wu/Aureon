"""LLM-based multi-query expansion for cross-article retrieval.

Generates semantic variants of the user query to improve recall
when the query spans multiple documents.

Based on MultiQueryRetriever pattern (LangChain) and Adaptive-RAG (NAACL 2024).
Reference: docs/RAG_OPTIMIZATION_PROMPT.md §4.2
"""

import json
from typing import List, Callable, Awaitable
import structlog

logger = structlog.get_logger()


async def multi_query_llm_rewrite(
    query: str,
    llm_call_fn: Callable[..., Awaitable[str]],
    n_variants: int = 3,
) -> List[str]:
    """Generate N semantic variants of the query via LLM.

    Args:
        query: Original user query
        llm_call_fn: Async LLM function (prompt string -> response string)
        n_variants: Number of variants to generate
    Returns:
        [original_query] + up to n_variants unique variants
    """
    prompt = (
        f"将以下问题改写为 {n_variants} 个不同的表述，保持语义一致但用词和角度不同。\n"
        f"每个变体应该能独立用于检索，找到与原始问题相关的信息。\n"
        f"只返回 JSON 数组格式，不要其他内容。\n\n"
        f"原始问题: {query}\n\n"
        f"示例:\n"
        f'输入: "对比 BM25 和向量检索的优缺点"\n'
        f'输出: ["BM25 关键词检索的优势和局限性", "向量语义检索的性能特点", "BM25 vs Vector Search 各自适用场景"]'
    )

    try:
        resp = await llm_call_fn(prompt)
        variants = json.loads(str(resp))
        if not isinstance(variants, list):
            return [query]
        result = [query]
        for v in variants:
            v = str(v).strip()
            if v and v != query and v not in result:
                result.append(v)
            if len(result) >= n_variants + 1:
                break
        return result
    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.warning("Multi-query LLM rewrite failed: %s, using original", e)
        return [query]


async def decompose_complex_query(
    query: str,
    llm_call_fn: Callable[..., Awaitable[str]],
    max_sub_queries: int = 5,
) -> List[str]:
    """Break a complex/comparative query into independent sub-queries.

    Args:
        query: Complex user query
        llm_call_fn: Async LLM function
        max_sub_queries: Maximum number of sub-queries
    Returns:
        List of sub-queries
    """
    prompt = (
        f"将以下复杂问题拆解为 {max_sub_queries} 个独立的子问题，每个子问题可以单独检索回答。\n"
        f"子问题应该覆盖原始问题的不同方面。\n"
        f"只返回 JSON 数组格式，不要其他内容。\n\n"
        f"原始问题: {query}\n\n"
        f"示例:\n"
        f'输入: "对比 LangChain 和 LlamaIndex 在 RAG 场景中的优缺点"\n'
        f'输出: ["LangChain 在 RAG 场景中的主要优势是什么？", "LlamaIndex 在 RAG 场景中的主要优势是什么？", "LangChain 和 LlamaIndex 的性能对比如何？"]'
    )

    try:
        resp = await llm_call_fn(prompt)
        sub_queries = json.loads(str(resp))
        if not isinstance(sub_queries, list):
            return [query]
        result = [str(q).strip() for q in sub_queries[:max_sub_queries] if str(q).strip()]
        return result if result else [query]
    except (json.JSONDecodeError, TypeError, Exception) as e:
        logger.warning("Query decomposition failed: %s, using original", e)
        return [query]
