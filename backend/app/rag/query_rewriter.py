"""
Query rewriting for RAG: expand queries, generate variants.

Includes HyDE (Hypothetical Document Embedding) implementation:
1. User query → LLM generates hypothetical answer
2. Hypothetical answer embedding → vector retrieval
3. Return retrieval results
"""
import structlog
from typing import List, Dict, Any

logger = structlog.get_logger()



# ── Cross-article query detection & rule-based expansion ──

_CROSS_ARTICLE_ZH = (
    "比较", "对比", "区别", "差异", "异同", "共同点", "相同", "相似", "类似",
    "两篇", "多篇", "哪些文章", "所有文章", "综合", "总结", "汇总",
)

_CROSS_ARTICLE_EN = (
    "compare", "comparison", "difference", "differences", "common",
    "commonalities", "similarities", "similar", "between",
    "across articles", "across documents", "all articles", "all documents",
    "both articles", "summarize", "summarise", "overview",
)

_ZH_SPLIT_MARKERS = ("和", "与", "以及")
_EN_SPLIT_MARKERS = (" and ", " vs ", " versus ", " compared to ", " compared with ")

_ZH_STRIP = ("的", "是什么", "是", "有", "哪些", "什么")


def is_cross_article_query(query: str) -> bool:
    """Detect whether *query* implies a cross-article / comparative intent.

    Bilingual: matches Chinese and English patterns (case-insensitive).
    Returns False for empty or None queries.
    """
    if not query:
        return False
    q_lower = query.lower()
    for pattern in _CROSS_ARTICLE_ZH:
        if pattern in query:
            return True
    for pattern in _CROSS_ARTICLE_EN:
        if pattern in q_lower:
            return True
    return False


def expand_queries_rules(query: str) -> List[str]:
    """Rule-based query expansion (no LLM needed).

    1. Split at conjunction markers and strip comparison boilerplate.
    2. If no split possible, extract content keywords by removing intent words.
    3. Always include original query as fallback.
    Returns deduplicated List[str] of non-empty strings, max 3 variants.
    """
    if not query:
        return [query] if query is not None else []

    fragments: List[str] = []

    # Try splitting on Chinese markers first, then English
    for marker in _ZH_SPLIT_MARKERS:
        if marker in query:
            fragments = query.split(marker)
            break

    if not fragments:
        q_lower = query.lower()
        for marker in _EN_SPLIT_MARKERS:
            if marker in q_lower:
                idx = q_lower.index(marker)
                fragments = [query[:idx], query[idx + len(marker):]]
                break

    # If we got a meaningful split (2+ parts), strip and return
    if len(fragments) >= 2:
        cleaned = []
        for frag in fragments:
            frag = frag.strip()
            for word in _ZH_STRIP:
                frag = frag.replace(word, "")
            frag = frag.strip(" ,，。")
            if frag:
                cleaned.append(frag)
        if cleaned:
            queries = cleaned + [query]
            seen = dict.fromkeys(queries)
            return [q for q in seen if q][:3]

    # Fallback: remove common intent words to extract content keywords
    stripped = query
    for word in _ZH_STRIP:
        stripped = stripped.replace(word + " ", " ").replace(word, "")
    stripped = stripped.strip(" ,，。")

    if stripped and stripped != query:
        queries = [stripped, query]
    else:
        queries = [query]

    seen = dict.fromkeys(queries)
    return [q for q in seen if q][:3]


# ── HyDE (Hypothetical Document Embedding) ──
# Gao et al., 2022: "Precise Zero-Shot Dense Retrieval without Relevance Labels"
# Generates a hypothetical answer to improve retrieval accuracy.

_HYDE_PROMPT_ZH = """你是一个知识库助手。请根据以下问题，生成一个详细、准确的回答。

要求：
1. 回答应该像一篇真实文档中的内容
2. 包含具体的技术细节和解释
3. 使用专业但易懂的语言
4. 长度约100-200字

问题：{query}

回答："""

_HYDE_PROMPT_EN = """You are a knowledge base assistant. Generate a detailed and accurate answer for the following question.

Requirements:
1. The answer should read like content from a real document
2. Include specific technical details and explanations
3. Use professional but accessible language
4. Length: approximately 100-200 words

Question: {query}

Answer:"""


def generate_hypothetical_answer(
    query: str,
    llm_call_fn,
    lang: str = "zh",
) -> str:
    """Generate a hypothetical answer using LLM for HyDE retrieval.

    Args:
        query: User query text
        llm_call_fn: LLM invocation function (messages -> response)
        lang: Language ("zh" or "en")

    Returns:
        Hypothetical answer text
    """
    prompt = _HYDE_PROMPT_EN if lang == "en" else _HYDE_PROMPT_ZH
    messages = [{"role": "user", "content": prompt.format(query=query)}]

    try:
        response = llm_call_fn(messages)
        # Handle both string and object responses
        if hasattr(response, "content"):
            return response.content.strip()
        return str(response).strip()
    except Exception as e:
        logger.warning("HyDE: failed to generate hypothetical answer: %s", e)
        return ""


def hyde_retrieve(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    lang: str = "zh",
    lang_filter: str = None,
) -> List[Dict[str, Any]]:
    """HyDE retrieval: generate hypothetical answer and use it for vector search.

    Implements the HyDE technique:
    1. Generate a hypothetical answer to the query using LLM
    2. Use the hypothetical answer (not the query) for vector similarity search
    3. Return the retrieved chunks

    This often retrieves more relevant documents because the hypothetical answer
    is semantically closer to actual documents than the original query.

    Args:
        query: User query text
        llm_call_fn: LLM invocation function
        top_k: Number of results to return
        lang: Language for hypothetical answer generation
        lang_filter: Document language filter ("zh" or "en")

    Returns:
        List of retrieved document chunks
    """
    # 1. Generate hypothetical answer
    hypothetical = generate_hypothetical_answer(query, llm_call_fn, lang=lang)
    if not hypothetical:
        logger.info("HyDE: empty hypothetical answer, falling back to direct retrieval")
        from app.rag.qa_chain import hybrid_retrieve
        return hybrid_retrieve(query, top_k=top_k, lang_filter=lang_filter)

    logger.info(
        "HyDE: generated hypothetical answer (%d chars), retrieving with it",
        len(hypothetical),
    )

    # 2. 使用混合检索（BM25 + 向量），而非纯向量检索
    from app.rag.qa_chain import hybrid_retrieve
    results = hybrid_retrieve(hypothetical, top_k=top_k, lang_filter=lang_filter)

    # 3. If HyDE returns no results, fallback to direct query retrieval
    if not results:
        logger.info("HyDE: no results with hypothetical answer, falling back to direct retrieval")
        results = hybrid_retrieve(query, top_k=top_k, lang_filter=lang_filter)

    return results


async def hyde_retrieve_async(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    lang: str = "zh",
    lang_filter: str = None,
) -> List[Dict[str, Any]]:
    """Async version of HyDE retrieval.

    Args:
        query: User query text
        llm_call_fn: Async LLM invocation function
        top_k: Number of results to return
        lang: Language for hypothetical answer generation
        lang_filter: Document language filter

    Returns:
        List of retrieved document chunks
    """
    from app.rag.qa_chain import hybrid_retrieve_async

    # 1. Generate hypothetical answer (async)
    prompt = _HYDE_PROMPT_EN if lang == "en" else _HYDE_PROMPT_ZH
    messages = [{"role": "user", "content": prompt.format(query=query)}]

    try:
        response = await llm_call_fn(messages)
        if hasattr(response, "content"):
            hypothetical = response.content.strip()
        else:
            hypothetical = str(response).strip()
    except Exception as e:
        logger.warning("HyDE async: failed to generate hypothetical answer: %s", e)
        hypothetical = ""

    if not hypothetical:
        logger.info("HyDE async: empty hypothetical answer, falling back to direct retrieval")
        return await hybrid_retrieve_async(query, top_k=top_k, lang_filter=lang_filter)

    logger.info(
        "HyDE async: generated hypothetical answer (%d chars), retrieving with it",
        len(hypothetical),
    )

    # 2. 使用混合检索（BM25 + 向量），而非纯向量检索
    results = await hybrid_retrieve_async(hypothetical, top_k=top_k, lang_filter=lang_filter)

    # 3. Fallback to direct query if no results
    if not results:
        logger.info("HyDE async: no results with hypothetical answer, falling back to direct retrieval")
        results = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=lang_filter)

    return results
