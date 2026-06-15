# -*- coding: utf-8 -*-
"""BM25 / keyword search for RAG system.

In-memory BM25+ index with jieba-based Chinese tokenization and Elasticsearch fallback.
Extracted from vector_store.py.
"""

import threading
from typing import List, Dict, Any

import structlog
from app.config import settings

logger = structlog.get_logger()

# ���� Keyword search index (no embeddings, <10ms queries) ����
_kw_docs: List[Dict] = []
_kw_idf: Dict[str, float] = {}
_kw_avgdl: float = 0.0
_kw_lock = threading.Lock()  # Thread-safe access to keyword index
_KW_MIN_RAW_SCORE = settings.kw_min_raw_score
_KW_MIN_IDF = 0.3  # skip only very high-frequency terms (appear in >85% docs)

# Chinese stop words �� function words, interrogatives, particles.
# Applied after jieba segmentation so "ʲô" is a single token, not chars.
_ZH_STOPWORDS = frozenset([
    "��", "��", "��", "��", "��", "��", "��", "��", "��", "Ҳ",
    "��", "��", "��", "��", "��", "��", "��", "��", "֮", "��",
    "��", "��", "��", "��", "��", "��", "��", "��", "Ϊ", "��",
    "��", "��", "��", "��", "��", "��", "��", "��", "��", "��",
    "��", "��", "��", "��", "ȥ", "��", "��", "û", "��", "��",
    "��", "��", "��", "Ҫ", "��", "��", "��", "��", "��", "��",
    "��", "ʲô", "��ô", "����", "���", "��Щ", "�ĸ�", "Ϊʲô",
    "����", "��", "��", "˭", "ʲô��", "��ô��", "һ��", "����",
    "ʹ��", "ͨ��", "����", "��Ҫ", "Ӧ��", "���", "��Ϊ", "����",
    "����", "Ȼ��", "�Ѿ�", "����", "һЩ", "����", "����",
])

# Lazy-load jieba to avoid import cost at module level
_jieba = None


def _get_jieba():
    """Lazy-load jieba segmenter."""
    global _jieba
    if _jieba is None:
        try:
            import jieba as _jb
            _jb.setLogLevel(20)  # suppress jieba init log
            _jieba = _jb
        except ImportError:
            _jieba = False
    return _jieba if _jieba is not False else None


def _tokenize(text: str, is_query: bool = False) -> List[str]:
    """jieba-based tokenizer with stopword filtering.

    Uses jieba for proper Chinese word segmentation instead of
    character-level n-grams. English words and numbers preserved.
    Stopwords filtered for documents; lighter filtering for queries
    to preserve terms that appear in document titles/headings.
    """
    import re
    jieba = _get_jieba()

    # English words + numbers (always extracted, case-insensitive)
    en_tokens = [m.group().lower() for m in re.finditer(r'[a-zA-Z]{2,}|\d+', text)]

    if jieba is None:
        # Fallback: if jieba unavailable, use bigrams (old behavior minus single chars)
        chars = re.findall(r'[һ-?]', text)
        zh_tokens = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    else:
        # jieba segmentation for Chinese text
        zh_tokens = [t.strip() for t in jieba.cut(text)
                     if t.strip() and not t.isascii()]

    # For queries: lighter filtering �� only remove pure function particles
    # For documents: full stopword removal to reduce index noise
    if is_query:
        # Query: keep all tokens with length >= 1 (no stopword removal)
        zh_filtered = [t for t in zh_tokens if len(t) >= 1]
    else:
        # Document: remove stopwords + single-char tokens
        zh_filtered = [t for t in zh_tokens
                       if len(t) >= 2 and t not in _ZH_STOPWORDS]

    return en_tokens + zh_filtered


def _build_kw_index(force: bool = False):
    """Build in-memory BM25 index from vector store documents.

    Pre-tokenizes all documents so retrieve_keyword() avoids re-tokenizing
    hundreds of docs on every query (saves ~150ms per query).
    Uses Qdrant as the sole vector backend.
    """
    global _kw_docs, _kw_idf, _kw_avgdl
    import math
    from collections import Counter

    with _kw_lock:
        if _kw_docs and not force:
            return

    try:
        docs_data = _load_docs_from_qdrant()

        if not docs_data:
            return

        n = len(docs_data)
        df: Counter = Counter()
        docs: List[Dict] = []
        total_len = 0

        for text, meta in docs_data:
            tokens = _tokenize(text)
            docs.append({"text": text, "metadata": meta, "tokens": tokens})
            total_len += len(tokens)
            for t in set(tokens):
                df[t] += 1

        # BM25 IDF �� clamp to min 0.1 to prevent ubiquitous terms (RAG, AI)
        # from getting IDF��0 and being completely ignored by scoring
        idf: Dict[str, float] = {}
        for term, freq in df.items():
            raw_idf = math.log(1.0 + (n - freq + 0.5) / (freq + 0.5))
            idf[term] = max(raw_idf, 0.1)

        avgdl = total_len / max(n, 1)

        # Atomic swap of globals under lock
        with _kw_lock:
            _kw_docs = docs
            _kw_idf = idf
            _kw_avgdl = avgdl
        logger.info("BM25 index ready: %d docs, %d terms, avgdl=%.0f", n, len(idf), avgdl)
    except Exception as e:
        logger.warning("BM25 index build failed: %s", e)


def _load_docs_from_qdrant() -> List[tuple]:
    """Load (text, metadata) pairs from Qdrant."""
    from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()
    try:
        info = client.get_collection(collection_name)
        if (info.points_count or 0) == 0:
            return []
    except Exception:
        return []

    docs_data = []
    offset = None
    while True:
        points, offset = client.scroll(
            collection_name=collection_name,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for pt in points:
            payload = pt.payload or {}
            text = payload.get("text", "")
            meta = payload.get("metadata", {})
            docs_data.append((text, meta))
        if offset is None:
            break
    return docs_data


def _bm25_score(query_terms: List[str], doc_terms: List[str], avgdl: float) -> float:
    """BM25+ scoring (Lv & Zhai 2011) with k1=1.2, b=0.75, ��=0.05.

    BM25+ adds a lower bound �� to TF normalization, preventing long documents
    from being unfairly penalized. Standard BM25's TF term �� 0 when dl >> avgdl,
    even if the document contains the query term.

    Token filtering (stopwords, single-chars) handled upstream by _tokenize().
    Only skips terms with IDF < _KW_MIN_IDF.
    Boosts English words (3+ chars) by 2x.
    """
    from collections import Counter
    doc_tf = Counter(doc_terms)
    doc_len = len(doc_terms)
    k1, b, delta = 1.2, 0.75, 0.05
    score = 0.0

    for term in set(query_terms):
        if term not in _kw_idf:
            continue
        idf = _kw_idf[term]
        if idf < _KW_MIN_IDF:
            continue
        tf = doc_tf.get(term, 0)
        if tf == 0:
            continue
        # BM25+: add �� to numerator so long docs don't get zero TF contribution
        num = delta + tf * (k1 + 1.0)
        denom = tf + k1 * (1.0 - b + b * doc_len / max(avgdl, 1.0))
        qf = query_terms.count(term)
        boost = 2.0 if term.isascii() and len(term) >= 3 and term.isalpha() else 1.0
        score += idf * (num / denom) * qf * boost
    return score


def retrieve_keyword(query: str, top_k: int = 3, lang_filter: str = None) -> List[Dict[str, Any]]:
    """Fast BM25 keyword retrieval �� no embedding API needed. <10ms.

    Args:
        query: ��ѯ�ı�
        top_k: ���ؽ������
        lang_filter: ���Թ��ˣ�"zh" �� "en"����None ��ʾ������
    """
    from app.config import settings
    if settings.bm25_backend == "elasticsearch":
        # Lazy import to avoid circular dependency (index_manager imports bm25)
        from app.rag.index_manager import retrieve_keyword_es
        return retrieve_keyword_es(query, top_k=top_k)

    _build_kw_index()

    # Snapshot globals under lock for thread-safe access
    with _kw_lock:
        kw_docs = _kw_docs
        kw_idf = dict(_kw_idf)
        kw_avgdl = _kw_avgdl

    if not kw_docs:
        return []

    q_terms = _tokenize(query, is_query=True)
    if not q_terms:
        return []

    # Filter: require at least one query term with meaningful IDF
    any(
        kw_idf.get(t, 0) >= _KW_MIN_IDF for t in set(q_terms)
    )

    # ���Թ���
    filtered_docs = kw_docs
    if lang_filter:
        filtered_docs = [doc for doc in kw_docs if doc.get("metadata", {}).get("language") == lang_filter]

    scored = []
    for doc in filtered_docs:
        doc_terms = doc.get("tokens") or _tokenize(doc["text"])
        s = _bm25_score(q_terms, doc_terms, kw_avgdl)
        if s > 0:
            scored.append((s, doc))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return []

    # Debug: log top 3 scores
    logger.info("BM25 query=%r terms=%r top3=%s", query, q_terms,
                [(round(s, 2), d["metadata"].get("slug", "")[:30]) for s, d in scored[:3]])

    # Filter: require minimum raw BM25 score to avoid generic-term noise
    if scored[0][0] < _KW_MIN_RAW_SCORE:
        return []

    max_score = scored[0][0] if scored else 1.0
    return [
        {
            "text": d["text"],
            "metadata": d["metadata"],
            "score": s / max_score,  # normalize to 0-1
        }
        for s, d in scored[:top_k]
    ]


def get_bm25_stats() -> dict:
    """Return BM25 index statistics for health endpoint."""
    # Diagnostic: sample IDF values for common terms
    sample_terms = ["��", "ʲô", "crewai", "rag", "hermes", "react"]
    idf_samples = {t: round(_kw_idf.get(t, 0), 3) for t in sample_terms}
    return {
        "docs": len(_kw_docs),
        "terms": len(_kw_idf),
        "avgdl": round(_kw_avgdl, 1) if _kw_avgdl else 0,
        "min_idf_threshold": _KW_MIN_IDF,
        "min_raw_score": _KW_MIN_RAW_SCORE,
        "sample_idf": idf_samples,
    }
