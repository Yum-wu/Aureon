"""
Query rewriting for RAG: expand queries, generate variants.
"""
import json
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


REWRITE_PROMPT = """你是查询改写助手。将用户问题改写为更适合知识库检索的形式。

规则：
1. 把口语化表达改为书面语
2. 扩展缩写和指代不明的内容
3. 生成 2-3 个不同角度的查询变体
4. 保留原问题的核心意图

只输出 JSON 格式：{{"rewritten": "<主查询>", "variants": ["<变体1>", "<变体2>"]}}

用户问题：{query}
"""


def rewrite_query(query: str, llm) -> Dict:
    """
    Rewrite user query for better retrieval.
    Returns dict with: rewritten (str), variants (list[str]).
    Falls back to original query on failure.
    """
    prompt = REWRITE_PROMPT.format(query=query)
    try:
        resp = llm.invoke([{"role": "user", "content": prompt}])
        text = resp.content.strip().removeprefix("```json").removesuffix("```").strip()
        data = json.loads(text)
        return {
            "rewritten": data.get("rewritten", query),
            "variants": data.get("variants", [query]),
        }
    except Exception as e:
        logger.warning("Query rewriting failed: %s", e)
        return {"rewritten": query, "variants": [query]}


def expand_queries(query: str, llm) -> List[str]:
    """Return deduplicated list of expanded queries for multi-query retrieval."""
    result = rewrite_query(query, llm)
    queries = [result["rewritten"]] + result.get("variants", [])
    return list(dict.fromkeys(queries))


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
_EN_STRIP = ("the", "a", "an", "in", "of", "for", "to", "is", "are", "was", "were")


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
        for marker in _EN_SPLIT_MARKERS:
            if marker in query.lower():
                # split preserving case for fragment content
                fragments = query.lower().split(marker)
                break

    # If we got a meaningful split (2+ parts), strip and return
    if len(fragments) >= 2:
        cleaned = []
        for frag in fragments:
            frag = frag.strip()
            for word in _ZH_STRIP:
                frag = frag.replace(word, "")
            for word in _EN_STRIP:
                frag = frag.replace(word + " ", " ").replace(word, "")
            frag = frag.strip(" ,，。")
            if frag:
                cleaned.append(frag)
        if cleaned:
            queries = cleaned + [query]
            seen = dict.fromkeys(queries)
            return [q for q in seen if q][:3]

    # Fallback: remove common intent words to extract content keywords
    stripped = query
    for word in _ZH_STRIP + _EN_STRIP:
        stripped = stripped.replace(word + " ", " ").replace(word, "")
    stripped = stripped.strip(" ,，。")

    if stripped and stripped != query:
        queries = [stripped, query]
    else:
        queries = [query]

    seen = dict.fromkeys(queries)
    return [q for q in seen if q][:3]
