"""
Query rewriting for RAG: expand queries, generate variants.
"""
import structlog
from typing import List

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
