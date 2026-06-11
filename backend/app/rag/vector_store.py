"""Vector store management for RAG system.
Uses Qdrant as persistent vector store with multi-provider embedding fallback.
"""

import logging
import os
import hashlib
import threading
import time
import numpy as np
from typing import List, Dict, Any, Optional

import structlog
from app.common import mask_secret
from app.config import settings
from app.multi_tenant.middleware import get_current_tenant_id
logger = structlog.get_logger()

# GPU embedder integration
_gpu_embedder = None
_gpu_embedder_failed = False

def _get_gpu_embedder():
    """Get or create GPU embedder singleton with CUDA auto-detection."""
    global _gpu_embedder, _gpu_embedder_failed
    if _gpu_embedder_failed:
        return None
    if _gpu_embedder is None:
        from app.rag.embed_gpu import GPUEmbedder
        from app.config import settings
        try:
            # Auto-detect CUDA availability
            device = "cpu"
            if settings.gpu_enabled:
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                except ImportError:
                    pass
            _gpu_embedder = GPUEmbedder(device=device)
            # Verify it can actually load the model
            _gpu_embedder.encode(["test"], batch_size=1)
        except Exception as e:
            logger.warning("GPU embedder unavailable: %s, using fallback", e)
            _gpu_embedder_failed = True
            return None
    return _gpu_embedder

# ChromaDB support removed — Qdrant is the sole vector backend.

VECTOR_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "vectors")

# ── Embedding cache (FIFO eviction, keyed by text hash) ──
_embed_cache: Dict[str, np.ndarray] = {}
_EMBED_CACHE_MAX = 500
_embed_cache_lock = threading.Lock()  # Thread-safe access to _embed_cache

# ── Query embedding reuse (module-level) ──
# retrieve_qdrant stores the query embedding here so compress_context
# can reuse it without a redundant embedding API call.
# Uses module-level (not thread-local) because asyncio.to_thread runs
# compress_context in a different worker thread than retrieve_qdrant.
_last_query_embedding: Optional[np.ndarray] = None
_last_query_embedding_lock = threading.Lock()

# ── Local embedding model (lazy-loaded singleton) ──
_local_embed_model = None
_LOCAL_MODEL_NAME = "BAAI/bge-large-zh-v1.5"
_LOCAL_MODEL_DIM = 1024  # fallback; overridden by settings.embedding_dim at runtime
# Set True if collection was built with API (different dim than local model)
_skip_local_embed = settings.skip_local_embed


def _get_embedding_dim() -> int:
    """Return the active embedding dimension from settings or env var.

    Priority: EMBEDDING_DIMENSION env -> settings.embedding_dim -> _LOCAL_MODEL_DIM (1024).
    """
    try:
        from app.config import settings
        return settings.embedding_dim
    except Exception:
        return _LOCAL_MODEL_DIM


def _cache_key(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def get_thread_query_embedding() -> Optional[np.ndarray]:
    """Retrieve the last query embedding stored by retrieve_qdrant.

    Used by compress_context to avoid redundant embedding API calls.
    Uses module-level storage (not thread-local) to work across asyncio.to_thread boundaries.
    """
    with _last_query_embedding_lock:
        return _last_query_embedding


def _set_thread_query_embedding(emb: np.ndarray) -> None:
    """Store query embedding for downstream reuse by compress_context."""
    global _last_query_embedding
    with _last_query_embedding_lock:
        _last_query_embedding = emb


def _get_local_model():
    """Lazy-load local sentence-transformers model. Returns None if unavailable."""
    global _local_embed_model
    if _local_embed_model is None:
        try:
            # Use HF mirror for China accessibility
            os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
            from sentence_transformers import SentenceTransformer
            _local_embed_model = SentenceTransformer(_LOCAL_MODEL_NAME)
            logger.info("Local embedding model loaded: %s (%dd)", _LOCAL_MODEL_NAME, _LOCAL_MODEL_DIM)
        except Exception as e:
            logger.warning("Local model unavailable: %s, will use API fallback", e)
            _local_embed_model = False
    return _local_embed_model if _local_embed_model is not False else None


def _embed_local(texts: List[str]) -> Optional[np.ndarray]:
    """Embed texts using local sentence-transformers model. Returns None if unavailable."""
    model = _get_local_model()
    if model is None:
        return None
    try:
        embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return np.array(embeddings, dtype=np.float32)
    except Exception as e:
        logger.warning("Local embedding error: %s", e)
        return None


# (ChromaDB singleton removed — Qdrant is the sole vector backend)

# ── Keyword search index (no embeddings, <10ms queries) ──
_kw_docs: List[Dict] = []
_kw_idf: Dict[str, float] = {}
_kw_avgdl: float = 0.0
_kw_lock = threading.Lock()  # Thread-safe access to keyword index
_KW_MIN_RAW_SCORE = settings.kw_min_raw_score
_KW_MIN_IDF = 0.3  # skip only very high-frequency terms (appear in >85% docs)

# Chinese stop words — function words, interrogatives, particles.
# Applied after jieba segmentation so "什么" is a single token, not chars.
_ZH_STOPWORDS = frozenset([
    "的", "是", "了", "在", "有", "和", "与", "或", "不", "也",
    "就", "都", "而", "及", "等", "这", "那", "个", "之", "其",
    "我", "你", "他", "她", "它", "们", "所", "以", "为", "会",
    "能", "可", "将", "把", "被", "从", "到", "对", "中", "上",
    "下", "里", "着", "过", "去", "来", "又", "没", "很", "还",
    "更", "最", "已", "要", "做", "地", "得", "吗", "吧", "呢",
    "啊", "什么", "怎么", "怎样", "如何", "哪些", "哪个", "为什么",
    "多少", "几", "哪", "谁", "什么样", "怎么样", "一个", "进行",
    "使用", "通过", "可以", "需要", "应该", "如果", "因为", "所以",
    "但是", "然后", "已经", "正在", "一些", "这种", "那种",
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


# ChromaDB helper functions removed (_get_chroma, _get_collection, _reset_chroma)


# ── Keyword / BM25 retrieval (no embeddings, <10ms) ──

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
        chars = re.findall(r'[一-鿿]', text)
        zh_tokens = [chars[i] + chars[i + 1] for i in range(len(chars) - 1)]
    else:
        # jieba segmentation for Chinese text
        zh_tokens = [t.strip() for t in jieba.cut(text)
                     if t.strip() and not t.isascii()]

    # For queries: lighter filtering — only remove pure function particles
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
    Supports both ChromaDB and Qdrant backends.
    """
    global _kw_docs, _kw_idf, _kw_avgdl
    import math
    from collections import Counter
    from app.config import settings

    with _kw_lock:
        if _kw_docs and not force:
            return

    try:
        if settings.vector_backend == "qdrant":
            docs_data = _load_docs_from_qdrant()
        else:
            docs_data = _load_docs_from_chroma()

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

        # BM25 IDF — clamp to min 0.1 to prevent ubiquitous terms (RAG, AI)
        # from getting IDF≈0 and being completely ignored by scoring
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


def _load_docs_from_chroma() -> List[tuple]:
    """Load (text, metadata) pairs from ChromaDB."""
    client = _get_chroma()
    collection = _get_collection(client)
    if collection.count() == 0:
        return []
    results = collection.get(include=["documents", "metadatas"])
    return [
        (results["documents"][i] or "", results["metadatas"][i] or {})
        for i in range(len(results["ids"]))
    ]


def _load_docs_from_qdrant() -> List[tuple]:
    """Load (text, metadata) pairs from Qdrant."""
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
    """BM25+ scoring (Lv & Zhai 2011) with k1=1.2, b=0.75, δ=0.05.

    BM25+ adds a lower bound δ to TF normalization, preventing long documents
    from being unfairly penalized. Standard BM25's TF term → 0 when dl >> avgdl,
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
        # BM25+: add δ to numerator so long docs don't get zero TF contribution
        num = delta + tf * (k1 + 1.0)
        denom = tf + k1 * (1.0 - b + b * doc_len / max(avgdl, 1.0))
        qf = query_terms.count(term)
        boost = 2.0 if term.isascii() and len(term) >= 3 and term.isalpha() else 1.0
        score += idf * (num / denom) * qf * boost
    return score


def retrieve_keyword(query: str, top_k: int = 3, lang_filter: str = None) -> List[Dict[str, Any]]:
    """Fast BM25 keyword retrieval — no embedding API needed. <10ms.

    Args:
        query: 查询文本
        top_k: 返回结果数量
        lang_filter: 语言过滤（"zh" 或 "en"），None 表示不过滤
    """
    from app.config import settings
    if settings.bm25_backend == "elasticsearch":
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
    has_meaningful_term = any(
        kw_idf.get(t, 0) >= _KW_MIN_IDF for t in set(q_terms)
    )

    # 语言过滤
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


def _embed_api(texts: List[str], provider: str, batch_size: int = 10) -> np.ndarray:
    """Call a single embedding API provider. Returns (N, dim) array.

    Raises on failure — caller decides fallback strategy.

    Args:
        provider: "dashscope" | "siliconflow" | "zhipu"
    """
    from app.config import settings
    import requests

    if provider == "dashscope":
        url = f"{settings.dashscope_base_url.rstrip('/')}/embeddings"
        api_key = settings.dashscope_api_key
        model = settings.dashscope_model
        dim = settings.dashscope_dimensions
    elif provider == "siliconflow":
        url = f"{settings.siliconflow_base_url.rstrip('/')}/embeddings"
        api_key = settings.siliconflow_api_key
        model = settings.siliconflow_model
        dim = None  # model-determined
    elif provider == "zhipu":
        url = f"{settings.embedding_base_url.rstrip('/')}/embeddings"
        api_key = settings.embedding_api_key or settings.llm_api_key
        model = settings.embedding_model or "embedding-2"
        dim = None
    else:
        raise ValueError(f"Unknown provider: {provider}")

    if not api_key:
        raise RuntimeError(f"{provider}: API key not configured")

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    all_embeddings = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start:start + batch_size]
        payload = {"model": model, "input": batch}
        if dim and dim != 1024:
            payload["dimensions"] = dim
            payload["encoding_format"] = "float"  # DashScope needs this for non-default dimensions

        # Retry with backoff for transient SSL/connection errors
        last_err = None
        for attempt in range(3):
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=90)
                if not resp.ok:
                    logger.error("Embedding API %s error %d: %s", provider, resp.status_code, resp.text[:300])
                resp.raise_for_status()
                break
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                    requests.exceptions.SSLError) as e:
                last_err = e
                wait = 2 ** attempt * 5
                logger.warning("Embedding API %s attempt %d failed: %s, retrying in %ds",
                               provider, attempt + 1, e, wait)
                time.sleep(wait)
        else:
            raise last_err

        data = resp.json()
        batch_embs = [d["embedding"] for d in sorted(data["data"], key=lambda x: x["index"])]
        all_embeddings.extend(batch_embs)

    result = np.array(all_embeddings, dtype=np.float32)

    # Validate: reject zero vectors (broken API response)
    norms = np.linalg.norm(result, axis=1)
    zero_ratio = np.sum(norms < 1e-6) / len(norms)
    if zero_ratio > 0.5:
        raise RuntimeError(f"{provider}: {zero_ratio:.0%} zero vectors — API returning garbage")

    logger.info("Embedding via %s: %d texts, dim=%d", provider, len(texts), result.shape[1])
    return result


def embed_texts_as_list(texts: List[str]) -> List[np.ndarray]:
    """Embed texts and return as list of vectors (for SemanticTextSplitter).

    Wrapper around embed_texts_llm that returns a list of individual vectors
    instead of a 2D numpy array.
    """
    if not texts:
        return []
    result = embed_texts_llm(texts)
    return [result[i] for i in range(len(texts))]


def embed_texts_llm(texts: List[str], batch_size: int = 10) -> np.ndarray:
    """Multi-provider embedding with fallback chain.

    Priority: local BGE (1024d) → DashScope (768d) → SiliconFlow → Zhipu.
    Set SKIP_LOCAL_EMBED=true to skip local model (recommended for Railway/API-only).
    Raises if ALL providers fail. Never returns zero vectors.
    """
    from app.config import settings

    # 1. Check in-memory cache first (fastest)
    uncached: List[tuple[int, str]] = []
    result = [None] * len(texts)
    with _embed_cache_lock:
        for i, t in enumerate(texts):
            key = _cache_key(t)
            if key in _embed_cache:
                result[i] = _embed_cache[key]
            else:
                uncached.append((i, t))
    if not uncached:
        return np.array(result, dtype=np.float32)

    # 2. Check Redis cache for remaining texts
    try:
        from app.cache.redis_client import get_redis
        redis = get_redis()
        if redis:
            still_uncached = []
            with _embed_cache_lock:
                for idx, t in uncached:
                    key = _cache_key(t)
                    if key in _embed_cache:
                        result[idx] = _embed_cache[key]
                    else:
                        still_uncached.append((idx, t))
            uncached = still_uncached
            if uncached:
                for idx, t in uncached:
                    key = _cache_key(t)
                    cached = redis.get(f"embed:{key}")
                    if cached:
                        emb = np.frombuffer(cached, dtype=np.float32)
                        result[idx] = emb
                        with _embed_cache_lock:
                            _embed_cache[key] = emb
                    else:
                        still_uncached.append((idx, t))
                uncached = still_uncached
            if not uncached:
                return np.array(result, dtype=np.float32)
    except Exception:
        pass  # Redis unavailable, continue with API

    uncached_texts = [t for _, t in uncached]

    # 2. Try local BGE model (skip if _skip_local_embed or collection uses different dims)
    embeddings = None
    if not _skip_local_embed:
        embeddings = _embed_local(uncached_texts)
    else:
        logger.info("Skipping local BGE embed (SKIP_LOCAL_EMBED=true), using API")

    # 3. API fallback chain
    if embeddings is None:
        providers = []
        if settings.dashscope_api_key:
            providers.append("dashscope")
        if settings.siliconflow_api_key:
            providers.append("siliconflow")
        if settings.embedding_api_key or settings.llm_api_key:
            providers.append("zhipu")

        if not providers:
            raise RuntimeError(
                "No embedding provider available. Local model failed and no API keys configured. "
                "Set DASHSCOPE_API_KEY or EMBEDDING_API_KEY in .env"
            )

        last_error = None
        for p in providers:
            try:
                embeddings = _embed_api(uncached_texts, p, batch_size)
                break
            except Exception as e:
                logger.warning("Embedding provider %s failed: %s", p, e)
                last_error = e

        if embeddings is None:
            raise RuntimeError(f"All embedding providers failed. Last error: {last_error}")

    # 4. Fill results + update cache
    with _embed_cache_lock:
        for (idx, text), emb in zip(uncached, embeddings):
            result[idx] = emb
            key = _cache_key(text)
            _embed_cache[key] = emb

    # Persist to Redis outside lock (I/O operation)
    for (idx, text), emb in zip(uncached, embeddings):
        key = _cache_key(text)
        try:
            from app.cache.redis_client import get_redis
            redis = get_redis()
            if redis:
                redis.setex(f"embed:{key}", 86400 * 7, emb.astype(np.float32).tobytes())
        except Exception:
            pass

    # Evict if over limit
    with _embed_cache_lock:
        if len(_embed_cache) > _EMBED_CACHE_MAX:
            for k in list(_embed_cache.keys())[:len(_embed_cache) - _EMBED_CACHE_MAX]:
                del _embed_cache[k]

    return np.array(result, dtype=np.float32)


# ── Embedding functions (ChromaDB wrapper removed — Qdrant is sole backend) ──

    def default_space(self):
        return "cosine"


# ── Public API ──

def _invalidate_stats_cache():
    """Invalidate stats cache after index changes."""
    _stats_cache["updated_at"] = 0.0


def add_to_index(chunks: List[Dict[str, Any]], path: str = None):
    """Add chunks to an EXISTING vector collection (incremental).

    Supports both ChromaDB and Qdrant backends.
    """
    from app.config import settings
    if settings.vector_backend == "qdrant":
        return _add_to_index_qdrant(chunks)
    return _add_to_index_chroma(chunks, path)


def _add_to_index_chroma(chunks: List[Dict[str, Any]], path: str = None):
    """ChromaDB: add chunks incrementally."""
    save_path = path or VECTOR_DIR
    os.makedirs(save_path, exist_ok=True)

    client = _get_chroma(save_path)
    collection = _get_collection(client)

    # Use content-hash IDs for collision resistance (deletions don't affect new IDs)
    ids = [f"chunk_{hashlib.md5(c['text'].encode()).hexdigest()}" for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "source": c["metadata"].get("source", ""),
            "title": c["metadata"].get("title", ""),
            "slug": c["metadata"].get("slug", ""),
            "language": c["metadata"].get("language", "unknown"),
            "parent_text": c["metadata"].get("parent_text", ""),
            "parent_idx": c["metadata"].get("parent_idx", -1),
        }
        for c in chunks
    ]

    batch_size = 20
    for start in range(0, len(chunks), batch_size):
        end = min(start + batch_size, len(chunks))
        collection.add(
            ids=ids[start:end],
            documents=documents[start:end],
            metadatas=metadatas[start:end],
        )

    logger.info("Added %d chunks to existing Chroma (%s)", len(chunks), save_path)
    _build_kw_index(force=True)
    _invalidate_stats_cache()


def _add_to_index_qdrant(chunks: List[Dict[str, Any]]):
    """Qdrant: add chunks incrementally."""
    from qdrant_client.models import PointStruct
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()

    # Get current max ID to avoid collisions
    try:
        info = client.get_collection(collection_name)
        existing_count = info.points_count or 0
    except Exception:
        existing_count = 0

    # Embed texts using API (skip local model when SKIP_LOCAL_EMBED=true)
    texts = [c["text"] for c in chunks]
    if _skip_local_embed:
        embeddings = embed_texts_llm(texts)
    else:
        try:
            from app.rag.embed_gpu import get_adaptive_embedder
            embedder = get_adaptive_embedder()
            embeddings = embedder.encode(texts, batch_size=64)
        except Exception:
            embeddings = embed_texts_llm(texts)

    # Upsert in batches
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        end = min(start + batch_size, len(chunks))
        points = [
            PointStruct(
                id=existing_count + start + i,
                vector=embeddings[start + i].tolist(),
                payload={"metadata": chunks[start + i].get("metadata", {}), "text": chunks[start + i]["text"]},
            )
            for i in range(end - start)
        ]
        client.upsert(collection_name=collection_name, points=points)

    logger.info("Added %d chunks to Qdrant ('%s')", len(chunks), collection_name)
    _build_kw_index(force=True)
    _invalidate_stats_cache()


def delete_from_index(source_filename: str, path: str = None):
    """Delete all chunks whose metadata.source == source_filename.

    Supports both ChromaDB and Qdrant backends.
    """
    from app.config import settings
    if settings.vector_backend == "qdrant":
        return _delete_from_index_qdrant(source_filename)
    return _delete_from_index_chroma(source_filename, path)


def _delete_from_index_chroma(source_filename: str, path: str = None):
    """ChromaDB: delete chunks by source filename."""
    save_path = path or VECTOR_DIR
    try:
        client = _get_chroma(save_path)
        collection = _get_collection(client)
    except Exception as e:
        logger.warning("Cannot open Chroma for delete: %s", e)
        return

    count_before = collection.count()
    collection.delete(where={"source": source_filename})
    count_after = collection.count()
    deleted = count_before - count_after
    safe_name = source_filename.encode("ascii", errors="replace").decode("ascii")
    logger.info("Deleted %d chunks for '%s' from Chroma (%s)", deleted, safe_name, save_path)
    _build_kw_index(force=True)
    _invalidate_stats_cache()


def _delete_from_index_qdrant(source_filename: str):
    """Qdrant: delete chunks by source filename.

    Qdrant doesn't support conditional delete by payload field directly,
    so we scroll to find matching point IDs, then delete them.
    """
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()

    try:
        info = client.get_collection(collection_name)
        if (info.points_count or 0) == 0:
            return
    except Exception as e:
        logger.warning("Cannot open Qdrant for delete: %s", e)
        return

    # Scroll to find points with matching source
    ids_to_delete = []
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
            meta = pt.payload.get("metadata", {}) if pt.payload else {}
            if meta.get("source") == source_filename:
                ids_to_delete.append(pt.id)
        if offset is None:
            break

    if ids_to_delete:
        client.delete(
            collection_name=collection_name,
            points_selector=ids_to_delete,
        )

    safe_name = source_filename.encode("ascii", errors="replace").decode("ascii")
    logger.info("Deleted %d chunks for '%s' from Qdrant ('%s')", len(ids_to_delete), safe_name, collection_name)
    _build_kw_index(force=True)
    _invalidate_stats_cache()


def save_index(chunks: List[Dict[str, Any]], embeddings: np.ndarray = None, path: str = None):
    """Save chunks to vector storage (embeddings computed automatically).

    When vector_backend == "qdrant": writes to Qdrant only.
    When vector_backend == "chroma": writes to ChromaDB.
    Additionally, if Qdrant server is reachable (_qdrant_available),
    also writes to Qdrant (dual-write) for gradual migration.
    """
    from app.config import settings
    if settings.vector_backend == "qdrant":
        return save_index_qdrant(chunks)
    if settings.bm25_backend == "elasticsearch":
        return save_index_es(chunks)

    save_path = path or VECTOR_DIR
    os.makedirs(save_path, exist_ok=True)

    global _chroma_client, _chroma_collection
    _chroma_client = None
    _chroma_collection = None

    client = _get_chroma(save_path)

    try:
        client.delete_collection("articles")
    except Exception:
        pass

    collection = _get_collection(client)

    ids = [f"chunk_{hashlib.md5(c['text'].encode()).hexdigest()}" for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [
        {
            "source": c["metadata"].get("source", ""),
            "title": c["metadata"].get("title", ""),
            "slug": c["metadata"].get("slug", ""),
            "language": c["metadata"].get("language", "unknown"),
            "parent_text": c["metadata"].get("parent_text", ""),
            "parent_idx": c["metadata"].get("parent_idx", -1),
        }
        for c in chunks
    ]

    batch_size = 20
    for start in range(0, len(chunks), batch_size):
        end = min(start + batch_size, len(chunks))
        add_kwargs = {
            "ids": ids[start:end],
            "documents": documents[start:end],
            "metadatas": metadatas[start:end],
        }
        # Use pre-computed embeddings if provided to avoid redundant embedding computation
        if embeddings is not None:
            add_kwargs["embeddings"] = embeddings[start:end].tolist()
        collection.add(**add_kwargs)

    logger.info("Saved %d chunks to Chroma (%s)", len(chunks), save_path)
    _build_kw_index(force=True)
    _invalidate_stats_cache()

    # ── Dual-write: if Qdrant is reachable, also write there ──
    global _qdrant_available
    if _qdrant_available or _check_qdrant_available():
        try:
            save_index_qdrant(chunks)
            logger.info("Dual-write: also saved %d chunks to Qdrant", len(chunks))
        except Exception as e:
            logger.warning("Dual-write to Qdrant failed (non-critical): %s", e)


def load_index(path: str = None):
    """Check if vector collection exists and has data.

    Supports both ChromaDB and Qdrant backends.
    """
    from app.config import settings
    try:
        if settings.vector_backend == "qdrant":
            client = _get_qdrant()
            collection_name = _get_qdrant_collection_name()
            info = client.get_collection(collection_name)
            count = info.points_count or 0
        else:
            client = _get_chroma(path)
            collection = _get_collection(client)
            count = collection.count()
        if count > 0:
            return [], np.array([])
        return None, None
    except Exception:
        return None, None


def retrieve(query: str, top_k: int = 3, use_mmr: bool = True, lang_filter: str = None, tenant_id: str = None) -> List[Dict[str, Any]]:
    """Retrieve top_k chunks using vector similarity search.

    Args:
        query: 查询文本
        top_k: 返回结果数量
        use_mmr: 是否使用 MMR 多样性优化
        lang_filter: 语言过滤（"zh" 或 "en"），None 表示不过滤
        tenant_id: 租户 ID（默认从上下文获取）
    """
    from app.config import settings
    if settings.vector_backend == "qdrant":
        return retrieve_qdrant(query, top_k=top_k, tenant_id=tenant_id, lang_filter=lang_filter)

    # Get tenant_id from context if not provided
    if tenant_id is None:
        tenant_id = get_current_tenant_id()

    try:
        client = _get_chroma()
        collection = _get_collection(client)
    except Exception as e:
        logger.warning("Chroma init error: %s", e)
        return []

    if collection.count() == 0:
        logger.warning("Chroma collection is empty. Run /api/rag/index first.")
        return []

    fetch_k = max(top_k * 2, 10) if use_mmr else top_k

    try:
        # 构建过滤条件（租户 + 语言）
        where_conditions = []
        if tenant_id:
            where_conditions.append({"tenant_id": {"$eq": tenant_id}})
        if lang_filter:
            where_conditions.append({"language": {"$eq": lang_filter}})

        # 组合过滤条件
        if len(where_conditions) == 0:
            where_filter = None
        elif len(where_conditions) == 1:
            where_filter = where_conditions[0]
        else:
            where_filter = {"$and": where_conditions}

        results = collection.query(
            query_texts=[query],
            n_results=fetch_k,
            include=["documents", "metadatas", "distances", "embeddings"],
            where=where_filter,
        )
    except Exception as e:
        # Auto-detect dimension mismatch: skip local model and retry
        global _skip_local_embed
        if "dimension" in str(e).lower() and not _skip_local_embed:
            logger.warning("Embedding dimension mismatch, switching to API embeddings")
            _skip_local_embed = True
            _embed_cache.clear()  # clear cached wrong-dimension embeddings
            try:
                results = collection.query(
                    query_texts=[query],
                    n_results=fetch_k,
                    include=["documents", "metadatas", "distances"],
                    where=where_filter,
                )
            except Exception as e2:
                logger.warning("Query error after retry: %s", e2)
                return []
        else:
            logger.warning("Query error: %s", e)
            return []

    if not results["ids"] or not results["ids"][0]:
        return []

    # Extract embeddings if available (for downstream reuse in compress_context)
    stored_embeddings = results.get("embeddings")

    items = []
    for i in range(len(results["ids"][0])):
        distance = results["distances"][0][i]
        score = 1.0 / (1.0 + distance)
        cosine_score = 1.0 - distance
        item_meta = dict(results["metadatas"][0][i] or {})
        item_meta["cosine_score"] = cosine_score

        # Parent-Child chunking: use parent_text for richer context if available
        parent_text = item_meta.get("parent_text", "")
        if parent_text:
            display_text = parent_text
        else:
            display_text = results["documents"][0][i]

        item = {
            "id": results["ids"][0][i],
            "text": display_text,
            "metadata": item_meta,
            "score": score,
        }
        # Attach stored embedding for reuse (avoids recomputation in compress_context)
        if stored_embeddings is not None:
            try:
                emb = np.array(stored_embeddings[0][i], dtype=np.float32)
                if np.linalg.norm(emb) > 1e-6:  # skip zero vectors
                    item["_embedding"] = emb
            except Exception:
                pass
        items.append(item)

    if use_mmr and len(items) > top_k:
        return _simple_diversity(items, top_k)

    return items[:top_k]


def _simple_diversity(items: list, top_k: int) -> list:
    """Lightweight diversity: prefer unique sources, fill with best scores.

    No embedding API calls.
    """
    seen_sources = set()
    diverse = []
    # Pass 1: best item per unique source
    for item in sorted(items, key=lambda x: x["score"], reverse=True):
        src = item["metadata"].get("source", item["metadata"].get("title", ""))
        if src not in seen_sources:
            diverse.append(item)
            seen_sources.add(src)
            if len(diverse) >= top_k:
                return diverse
    # Pass 2: fill remaining from unused items by score
    remaining = [it for it in items if it not in diverse]
    diverse.extend(remaining[:top_k - len(diverse)])
    return diverse


def format_context(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks into context string.

    Uses parent_text when available (Parent-Child chunking) for richer context.
    Deduplicates by parent to avoid repeating the same parent text.
    """
    parts = []
    seen_parents = set()
    for i, chunk in enumerate(chunks):
        source = chunk["metadata"].get("title", chunk["metadata"].get("source", "Unknown"))
        # Prefer parent_text for richer context (Parent-Child chunking)
        parent_text = chunk.get("metadata", {}).get("parent_text")
        parent_idx = chunk.get("metadata", {}).get("parent_idx")
        parent_key = f"{source}:{parent_idx}"

        if parent_text and parent_key not in seen_parents:
            seen_parents.add(parent_key)
            parts.append(f"[Source {len(parts)+1}: {source}]\n{parent_text}")
        elif not parent_text:
            # Fallback: use child text (legacy chunks without parent)
            parts.append(f"[Source {len(parts)+1}: {source}]\n{chunk['text']}")
    return "\n\n".join(parts)


# ── Cross-Encoder Reranker (lazy-loaded singleton) ──
_reranker = None
_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"


def _get_reranker():
    """Lazy-load cross-encoder reranker. Returns None if unavailable.

    Always skips loading when:
    - RERANK_ENABLED=false (env var)
    - GPU_ENABLED=false (env var) — prevents OOM on Railway
    - Less than 500MB RAM available
    """
    global _reranker
    if _reranker is None:
        # Hard check: skip if RERANK_ENABLED is explicitly disabled
        import os
        if os.environ.get("RERANK_ENABLED", "true").lower() in ("false", "0", "no"):
            logger.info("Reranker disabled (RERANK_ENABLED=false), skipping CrossEncoder load")
            _reranker = False
            return None

        # Memory guard: skip loading if <500MB free to prevent OOM on constrained containers
        try:
            import psutil
            avail_mb = psutil.virtual_memory().available / (1024 * 1024)
            if avail_mb < 500:
                logger.warning("Skipping reranker load: only %.0fMB RAM available (need ~2200MB)", avail_mb)
                _reranker = False
                return None
        except ImportError:
            pass  # psutil not installed, proceed without memory check
        try:
            from sentence_transformers import CrossEncoder
            _reranker = CrossEncoder(_RERANKER_MODEL)
            logger.info("Cross-encoder reranker loaded: %s", _RERANKER_MODEL)
        except Exception as e:
            logger.warning("Reranker unavailable: %s", e)
            _reranker = False
    return _reranker if _reranker is not False else None


def _rerank_via_api(query: str, chunks: List[Dict[str, Any]], top_k: int = 3) -> Optional[List[Dict[str, Any]]]:
    """Rerank chunks via remote API. Returns None if unavailable.

    Provider priority (env: RERANK_PROVIDER):
    1. DashScope qwen3-rerank (same platform as embedding, <5ms from Singapore)
    2. SiliconFlow BAAI/bge-reranker-v2-m3
    3. Cohere rerank-multilingual-v3.0
    4. Jina jina-reranker-v2-base-multilingual
    """
    import os
    import httpx

    texts = [c["text"] for c in chunks]
    preferred = os.environ.get("RERANK_PROVIDER", "dashscope")

    # ── Helper: generic rerank POST ──
    def _call_rerank(url: str, api_key: str, model: str, provider_name: str,
                     extra_body: dict | None = None) -> Optional[List[Dict[str, Any]]]:
        body: dict = {
            "model": model,
            "query": query,
            "documents": texts,
            "top_n": top_k,
        }
        if extra_body:
            body.update(extra_body)
        try:
            resp = httpx.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            scored = []
            for item in data.get("results", []):
                idx = item["index"]
                score = item["relevance_score"]
                chunk = chunks[idx].copy()
                chunk["rerank_score"] = float(score)
                scored.append(chunk)
            scored.sort(key=lambda x: x["rerank_score"], reverse=True)
            logger.info("API rerank (%s): %d chunks -> %d results", provider_name, len(chunks), len(scored))
            return scored[:top_k]
        except Exception as e:
            logger.warning("%s API rerank failed: %s", provider_name, e)
            return None

    # ── Build provider list (preferred first, then fallbacks) ──
    ds_key = os.environ.get("DASHSCOPE_API_KEY") or getattr(settings, "dashscope_api_key", "")
    sf_key = os.environ.get("SILICONFLOW_API_KEY") or getattr(settings, "siliconflow_api_key", "")
    cohere_key = os.environ.get("COHERE_API_KEY") or getattr(settings, "cohere_api_key", None)
    jina_key = os.environ.get("JINA_API_KEY") or getattr(settings, "jina_api_key", None)

    providers = []
    if preferred == "dashscope" and ds_key:
        providers.append(("dashscope", ds_key, settings.dashscope_rerank_model, settings.dashscope_rerank_url))
    if sf_key:
        providers.append(("siliconflow", sf_key, "BAAI/bge-reranker-v2-m3", settings.siliconflow_base_url))
    if cohere_key:
        providers.append(("cohere", cohere_key, settings.cohere_rerank_model, "https://api.cohere.ai/v2"))
    if jina_key:
        providers.append(("jina", jina_key, "jina-reranker-v2-base-multilingual", "https://api.jina.ai/v1"))
    # Add dashscope as fallback if it wasn't the preferred
    if preferred != "dashscope" and ds_key:
        providers.append(("dashscope", ds_key, settings.dashscope_rerank_model, settings.dashscope_rerank_url))

    for name, key, model, base_url in providers:
        # DashScope qwen3-rerank uses /reranks (plural), others use /rerank
        suffix = "reranks" if name == "dashscope" else "rerank"
        url = f"{base_url.rstrip('/')}/{suffix}"
        result = _call_rerank(url, key, model, name)
        if result is not None:
            return result

    return None


def rerank(query: str, chunks: List[Dict[str, Any]], top_k: int = 3) -> List[Dict[str, Any]]:
    """Rerank chunks using cross-encoder or remote API. Returns top_k results.

    Backend selection (env: RERANK_BACKEND):
    - "api"   → Cohere / Jina remote API (no local model loading, safe for Railway)
    - "local" → CrossEncoder (GPU or CPU, requires ~500MB+ RAM)
    """
    # HARD STOP: always skip reranking when explicitly disabled
    import os
    if os.environ.get("RERANK_ENABLED", "true").lower() in ("false", "0", "no"):
        logger.debug("RERANK_ENABLED=false, returning top %d by score", top_k)
        return chunks[:top_k]

    if not chunks or len(chunks) <= 1:
        return chunks

    from app.config import settings
    if not settings.rerank_enabled:
        return chunks[:top_k]

    # ── API reranker (zero local memory, ideal for Railway / serverless) ──
    rerank_backend = os.environ.get("RERANK_BACKEND", settings.rerank_backend)
    if rerank_backend == "api":
        api_result = _rerank_via_api(query, chunks, top_k=top_k)
        if api_result is not None:
            return api_result
        # API unavailable, fall through to local reranker
        logger.warning("API reranker unavailable, falling back to local CrossEncoder")

    # Try GPU reranker first for continuous GPU utilization
    try:
        from app.rag.embed_gpu import get_gpu_reranker
        if settings.gpu_enabled:
            gpu_reranker = get_gpu_reranker()
            return gpu_reranker.rerank(query, chunks, top_k=top_k)
    except Exception as e:
        logger.debug("GPU reranker unavailable, falling back to CPU: %s", e)

    # CPU fallback
    model = _get_reranker()
    if model is None:
        return chunks[:top_k]

    pairs = [(query, c["text"]) for c in chunks]
    scores = model.predict(pairs)

    # Attach scores and sort
    for chunk, score in zip(chunks, scores):
        chunk["rerank_score"] = float(score)

    reranked = sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)

    # No score threshold or cliff detection — let CRAG handle relevance filtering.
    # The reranker's job is RANKING only: better results first.
    return reranked[:top_k]


def get_bm25_stats() -> dict:
    """Return BM25 index statistics for health endpoint."""
    # Diagnostic: sample IDF values for common terms
    sample_terms = ["是", "什么", "crewai", "rag", "hermes", "react"]
    idf_samples = {t: round(_kw_idf.get(t, 0), 3) for t in sample_terms}
    return {
        "docs": len(_kw_docs),
        "terms": len(_kw_idf),
        "avgdl": round(_kw_avgdl, 1) if _kw_avgdl else 0,
        "min_idf_threshold": _KW_MIN_IDF,
        "min_raw_score": _KW_MIN_RAW_SCORE,
        "sample_idf": idf_samples,
    }


# ── Stats cache (avoid full-scan on every health check) ──
_stats_cache: dict = {"doc_count": 0, "chunk_count": 0, "updated_at": 0.0}
_STATS_CACHE_TTL = settings.stats_cache_ttl  # seconds


def get_collection_stats() -> tuple[int, int]:
    """Return (total_docs, total_chunks) from the active vector store.

    Counts unique source documents and total chunks.
    Returns (0, 0) if collection is empty or unavailable.
    Results are cached for STATS_CACHE_TTL seconds (default 60s).
    Supports both ChromaDB and Qdrant backends.
    """
    import time as _time
    from app.config import settings
    now = _time.time()
    if (now - _stats_cache["updated_at"]) < _STATS_CACHE_TTL:
        return _stats_cache["doc_count"], _stats_cache["chunk_count"]

    try:
        if settings.vector_backend == "qdrant":
            return _get_collection_stats_qdrant(now)
        return _get_collection_stats_chroma(now)
    except Exception:
        return _stats_cache["doc_count"], _stats_cache["chunk_count"]


def _get_collection_stats_chroma(now: float) -> tuple[int, int]:
    """ChromaDB stats implementation."""
    client = _get_chroma()
    collection = _get_collection(client)
    total_chunks = collection.count()
    if total_chunks > 0:
        all_meta = collection.get(include=["metadatas"])
        unique_docs = set()
        for meta in all_meta.get("metadatas", []):
            if meta and isinstance(meta, dict):
                src = meta.get("source") or meta.get("title", "unknown")
                unique_docs.add(src)
        _stats_cache["doc_count"] = len(unique_docs)
        _stats_cache["chunk_count"] = total_chunks
        _stats_cache["updated_at"] = now
        return len(unique_docs), total_chunks
    _stats_cache["doc_count"] = 0
    _stats_cache["chunk_count"] = 0
    _stats_cache["updated_at"] = now
    return 0, 0


def _get_collection_stats_qdrant(now: float) -> tuple[int, int]:
    """Qdrant stats implementation."""
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()
    try:
        info = client.get_collection(collection_name)
        total_chunks = info.points_count or 0
    except Exception:
        return _stats_cache["doc_count"], _stats_cache["chunk_count"]

    if total_chunks > 0:
        # Scroll through points to count unique sources
        unique_docs = set()
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
                meta = pt.payload.get("metadata", {}) if pt.payload else {}
                src = meta.get("source") or meta.get("title", "unknown")
                unique_docs.add(src)
            if offset is None:
                break
        _stats_cache["doc_count"] = len(unique_docs)
        _stats_cache["chunk_count"] = total_chunks
        _stats_cache["updated_at"] = now
        return len(unique_docs), total_chunks

    _stats_cache["doc_count"] = 0
    _stats_cache["chunk_count"] = 0
    _stats_cache["updated_at"] = now
    return 0, 0


def _get_qdrant_collection_name() -> str:
    """Get Qdrant collection name from settings."""
    from app.config import settings
    return settings.qdrant_collection or "aureon"


def get_indexed_sources() -> set:
    """Return set of source filenames currently in the vector store.

    Supports both ChromaDB and Qdrant backends.
    """
    from app.config import settings
    try:
        if settings.vector_backend == "qdrant":
            return _get_indexed_sources_qdrant()
        return _get_indexed_sources_chroma()
    except Exception:
        return set()


def _get_indexed_sources_chroma() -> set:
    """ChromaDB: get indexed source filenames."""
    client = _get_chroma()
    collection = _get_collection(client)
    if collection.count() == 0:
        return set()
    all_meta = collection.get(include=["metadatas"])
    sources = set()
    for meta in all_meta.get("metadatas", []):
        if meta and isinstance(meta, dict):
            src = meta.get("source")
            if src:
                sources.add(src)
    return sources


def _get_indexed_sources_qdrant() -> set:
    """Qdrant: get indexed source filenames."""
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()
    try:
        info = client.get_collection(collection_name)
        if (info.points_count or 0) == 0:
            return set()
    except Exception:
        return set()

    sources = set()
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
            meta = pt.payload.get("metadata", {}) if pt.payload else {}
            src = meta.get("source")
            if src:
                sources.add(src)
        if offset is None:
            break
    return sources


def check_index_stale(articles_dir: str) -> dict:
    """Check if the article files on disk are out of sync with the Chroma index.

    Returns:
        {"stale": bool, "reason": str, "fs_count": int, "idx_count": int,
         "missing_files": list[str], "extra_files": list[str]}
    """
    import pathlib

    result = {
        "stale": False,
        "reason": "",
        "fs_count": 0,
        "idx_count": 0,
        "missing_files": [],
        "extra_files": [],
    }

    try:
        # Collect all .md files on disk
        articles_path = pathlib.Path(articles_dir)
        if not articles_path.is_dir():
            result["stale"] = True
            result["reason"] = "articles directory not found"
            return result

        fs_files = sorted(str(p.relative_to(articles_path))
                          for p in articles_path.rglob("*.md"))
        result["fs_count"] = len(fs_files)

        # Collect indexed sources from Chroma
        indexed = get_indexed_sources()
        result["idx_count"] = len(indexed)

        # No files but index has data → stale (files were deleted)
        if len(fs_files) == 0 and len(indexed) > 0:
            result["stale"] = True
            result["reason"] = "no articles on disk but index has data"
            return result

        # Files exist but index is empty → stale
        if len(fs_files) > 0 and len(indexed) == 0:
            result["stale"] = True
            result["reason"] = f"{len(fs_files)} articles found but index is empty"
            return result

        # Files exist but index is empty
        if len(fs_files) == 0 and len(indexed) == 0:
            return result  # both empty, not stale

        # Simple comparison: file count vs indexed doc count
        # Path matching is unreliable across platforms; count-based check is sufficient
        if len(indexed) < len(fs_files):
            result["stale"] = True
            result["reason"] = f"{len(fs_files)} articles on disk but only {len(indexed)} indexed"
        elif len(indexed) > len(fs_files):
            result["stale"] = True
            result["reason"] = f"{len(indexed)} indexed entries but only {len(fs_files)} articles on disk"

        return result
    except Exception as e:
        logger.warning("check_index_stale failed: %s", e)
        result["stale"] = True
        result["reason"] = f"check failed: {e}"
        return result


# ── Qdrant Backend ──
_qdrant_client = None
_qdrant_available = False  # Global flag: True if Qdrant is reachable


def _check_qdrant_available() -> bool:
    """Check if Qdrant server is reachable. Caches result in _qdrant_available."""
    global _qdrant_available
    try:
        client = _get_qdrant()
        client.get_collections()  # lightweight health check
        _qdrant_available = True
        return True
    except Exception:
        _qdrant_available = False
        return False


def _get_qdrant():
    """Get or create Qdrant client singleton.

    Auto-detects mode from URL scheme:
    - https:// → Qdrant Cloud (REST only, no gRPC)
    - http://localhost → local Qdrant (gRPC preferred)
    """
    global _qdrant_client
    if _qdrant_client is None:
        from qdrant_client import QdrantClient
        from app.config import settings
        url = settings.qdrant_url
        kwargs: dict = {"url": url}
        if url.startswith("https://"):
            # Qdrant Cloud: REST only, gRPC not supported
            pass
        else:
            # Local Qdrant: prefer gRPC for lower latency
            kwargs["prefer_grpc"] = True
            kwargs["grpc_port"] = 6334
        if settings.qdrant_api_key:
            kwargs["api_key"] = settings.qdrant_api_key
        _qdrant_client = QdrantClient(**kwargs)
    return _qdrant_client


def save_index_qdrant(chunks: List[Dict], collection_name: str = "aureon"):
    """Save chunks to Qdrant vector store."""
    from qdrant_client.models import VectorParams, Distance, PointStruct
    client = _get_qdrant()
    dim = _get_embedding_dim()

    # Delete and recreate collection
    try:
        client.delete_collection(collection_name)
    except Exception:
        pass

    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    # Embed all texts (skip local model when SKIP_LOCAL_EMBED=true)
    texts = [c["text"] for c in chunks]
    if _skip_local_embed:
        embeddings = embed_texts_llm(texts)
    else:
        try:
            from app.config import settings
            from app.rag.embed_gpu import get_adaptive_embedder
            embedder = get_adaptive_embedder()
            embeddings = embedder.encode(texts, batch_size=settings.embedding_batch_size)
        except Exception as e:
            logger.warning("Adaptive embedding failed: %s, falling back to API", e)
            embeddings = embed_texts_llm(texts)

    # Upsert in batches
    batch_size = 100
    for start in range(0, len(chunks), batch_size):
        end = min(start + batch_size, len(chunks))
        points = [
            PointStruct(
                id=i,
                vector=embeddings[i].tolist(),
                payload={"metadata": chunks[i].get("metadata", {}), "text": chunks[i]["text"]},
            )
            for i in range(start, end)
        ]
        client.upsert(collection_name=collection_name, points=points)

    logger.info("Qdrant: indexed %d chunks into '%s'", len(chunks), collection_name)


def retrieve_qdrant(query: str, top_k: int = 3, collection_name: str = "aureon", tenant_id: str = None, lang_filter: str = None) -> List[Dict]:
    """Retrieve from Qdrant vector store.

    Uses adaptive dispatch: CPU for single queries (lower latency),
    GPU for batch queries (higher throughput).

    Supports both old (search) and new (query_points) qdrant_client APIs.
    Supports payload filtering via Qdrant Filter (e.g. lang_filter, tenant_id).
    Supports parent_text: if parent_text exists in metadata, use it as display text.

    Args:
        query: 查询文本
        top_k: 返回结果数量
        collection_name: Qdrant collection 名称
        tenant_id: 租户 ID（默认从上下文获取）
        lang_filter: 语言过滤（"zh" 或 "en"），None 表示不过滤
    """
    client = _get_qdrant()

    # Get tenant_id from context if not provided
    if tenant_id is None:
        tenant_id = get_current_tenant_id()

    try:
        # When SKIP_LOCAL_EMBED=true, skip local model entirely — use API directly
        if _skip_local_embed:
            query_emb = embed_texts_llm([query])
        else:
            from app.rag.embed_gpu import get_adaptive_embedder
            embedder = get_adaptive_embedder()
            query_emb = embedder.encode([query])
    except Exception as e:
        logger.warning("Adaptive embedding failed: %s, falling back to API", e)
        query_emb = embed_texts_llm([query])

    query_vector = query_emb[0].tolist()

    # Store query embedding in thread-local for compress_context reuse
    _set_thread_query_embedding(query_emb[0])

    # Check if stored data actually has tenant_id — skip filter if not
    _has_tenant_id = False
    try:
        _sample, _ = client.scroll(
            collection_name=collection_name, limit=1,
            with_payload=True, with_vectors=False,
        )
        if _sample:
            _sample_meta = _sample[0].payload.get("metadata", {}) if _sample[0].payload else {}
            _has_tenant_id = "tenant_id" in _sample_meta
    except Exception:
        pass

    # Build Qdrant filter conditions (tenant + lang_filter)
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    must_conditions = []
    if tenant_id and _has_tenant_id:
        must_conditions.append(
            FieldCondition(
                key="metadata.tenant_id",
                match=MatchValue(value=tenant_id),
            )
        )
    if lang_filter:
        must_conditions.append(
            FieldCondition(
                key="metadata.language",
                match=MatchValue(value=lang_filter),
            )
        )
    query_filter = Filter(must=must_conditions) if must_conditions else None

    # Try new API first (qdrant_client >= 1.12), fall back to old
    try:
        search_kwargs = dict(
            collection_name=collection_name,
            query=query_vector,
            limit=top_k,
            with_payload=True,
            with_vectors=True,
        )
        if query_filter is not None:
            search_kwargs["query_filter"] = query_filter
        response = client.query_points(**search_kwargs)
        results = response.points
    except (AttributeError, TypeError):
        # Old API fallback
        search_kwargs = dict(
            collection_name=collection_name,
            query_vector=query_vector,
            limit=top_k,
            with_vectors=True,
        )
        if query_filter is not None:
            search_kwargs["filter"] = query_filter
        results = client.search(**search_kwargs)

    items = []
    for r in results:
        payload_meta = r.payload.get("metadata", {})

        # Parent-Child chunking: use parent_text for richer context if available
        parent_text = payload_meta.get("parent_text", "")
        if parent_text:
            display_text = parent_text
        else:
            display_text = r.payload.get("text", "")

        item = {
            "text": display_text,
            "metadata": {**payload_meta, "cosine_score": r.score},
            "score": r.score,
        }
        # Attach stored embedding for reuse (avoids recomputation in compress_context)
        try:
            if hasattr(r, 'vector') and r.vector is not None:
                emb = np.array(r.vector, dtype=np.float32)
                if np.linalg.norm(emb) > 1e-6:
                    item["_embedding"] = emb
        except Exception:
            pass
        items.append(item)
    return items



def switch_to_qdrant(batch_size: int = 100) -> dict:
    """Migrate all data from ChromaDB to Qdrant.

    Reads all documents, embeddings, and metadatas from the ChromaDB collection,
    then batch-writes them into the Qdrant collection. Returns migration statistics.

    Args:
        batch_size: Number of points to write per Qdrant upsert batch.

    Returns:
        dict with migration stats: {"status", "migrated_chunks", "source_backend", "target_backend", "elapsed_seconds"}
    """
    from qdrant_client.models import VectorParams, Distance, PointStruct
    import numpy as _np
    start_time = time.time()

    # 1. Read all data from ChromaDB
    try:
        chroma_client = _get_chroma()
        chroma_collection = _get_collection(chroma_client)
    except Exception as e:
        logger.error("Cannot connect to ChromaDB for migration: %s", e)
        return {"status": "error", "message": f"ChromaDB connection failed: {e}"}

    total = chroma_collection.count()
    if total == 0:
        logger.info("ChromaDB collection is empty, nothing to migrate")
        return {
            "status": "ok",
            "migrated_chunks": 0,
            "source_backend": "chroma",
            "target_backend": "qdrant",
            "elapsed_seconds": 0,
            "message": "ChromaDB collection is empty",
        }

    logger.info("Starting ChromaDB -> Qdrant migration: %d chunks", total)

    # 2. Read all documents, embeddings, metadatas from ChromaDB
    all_ids = []
    all_documents = []
    all_metadatas = []
    all_embeddings = []

    offset = 0
    batch_read = 500
    while offset < total:
        results = chroma_collection.get(
            include=["documents", "metadatas", "embeddings"],
            limit=batch_read,
            offset=offset,
        )
        if not results["ids"]:
            break
        all_ids.extend(results["ids"])
        all_documents.extend(results["documents"])
        all_metadatas.extend(results["metadatas"])
        if results.get("embeddings"):
            all_embeddings.extend(results["embeddings"])
        offset += len(results["ids"])

    logger.info("Read %d chunks from ChromaDB", len(all_ids))

    # 3. Prepare embeddings — if ChromaDB doesn't have them, recompute
    if len(all_embeddings) != len(all_ids):
        logger.info("Recomputing embeddings for %d chunks (ChromaDB did not store them)", len(all_ids))
        if _skip_local_embed:
            embeddings_np = embed_texts_llm(all_documents)
        else:
            try:
                from app.rag.embed_gpu import get_adaptive_embedder
                embedder = get_adaptive_embedder()
                embeddings_np = embedder.encode(all_documents, batch_size=64)
            except Exception:
                embeddings_np = embed_texts_llm(all_documents)
    else:
        embeddings_np = _np.array(all_embeddings, dtype=_np.float32)

    # 4. Ensure Qdrant collection exists with correct dimensions
    qdrant_client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()
    dim = embeddings_np.shape[1] if len(embeddings_np) > 0 else _get_embedding_dim()

    try:
        qdrant_client.delete_collection(collection_name)
    except Exception:
        pass

    qdrant_client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

    # 5. Batch write to Qdrant
    migrated = 0
    for start in range(0, len(all_ids), batch_size):
        end = min(start + batch_size, len(all_ids))
        points = []
        for i in range(start, end):
            points.append(
                PointStruct(
                    id=i,
                    vector=embeddings_np[i].tolist(),
                    payload={
                        "metadata": all_metadatas[i] if all_metadatas[i] else {},
                        "text": all_documents[i] or "",
                    },
                )
            )
        qdrant_client.upsert(collection_name=collection_name, points=points)
        migrated += len(points)
        logger.info("Migration progress: %d / %d chunks", migrated, len(all_ids))

    elapsed = time.time() - start_time
    stats = {
        "status": "ok",
        "migrated_chunks": migrated,
        "source_backend": "chroma",
        "target_backend": "qdrant",
        "elapsed_seconds": round(elapsed, 2),
        "qdrant_collection": collection_name,
        "vector_dimension": dim,
    }
    logger.info("Migration complete: %d chunks in %.2fs", migrated, elapsed)

    # Rebuild BM25 index from Qdrant
    _build_kw_index(force=True)
    _invalidate_stats_cache()

    return stats


# ── Elasticsearch BM25 Backend ──
_es_client = None


def _get_es():
    """Get or create Elasticsearch client singleton."""
    global _es_client
    if _es_client is None:
        from elasticsearch import Elasticsearch
        from app.config import settings
        kwargs = {}
        if settings.es_password:
            kwargs["basic_auth"] = ("elastic", settings.es_password)
        _es_client = Elasticsearch(settings.es_url, **kwargs)
    return _es_client


def save_index_es(chunks: List[Dict], index_name: str = None):
    """Index chunks into Elasticsearch for BM25 retrieval."""
    from app.config import settings
    index_name = index_name or settings.es_index
    es = _get_es()

    if es.indices.exists(index=index_name):
        es.indices.delete(index=index_name)

    es.indices.create(index=index_name, body={
        "settings": {"analysis": {"analyzer": {"default": {"type": "standard"}}}},
        "mappings": {"properties": {
            "text": {"type": "text"},
            "slug": {"type": "keyword"},
            "title": {"type": "text"},
            "parent_text": {"type": "text"},
        }}
    })

    for i, chunk in enumerate(chunks):
        meta = chunk.get("metadata", {})
        es.index(index=index_name, id=i, body={
            "text": chunk["text"],
            "slug": meta.get("slug", ""),
            "title": meta.get("title", ""),
            "parent_text": meta.get("parent_text", ""),
        })

    es.indices.refresh(index=index_name)
    logger.info("ES: indexed %d chunks into '%s'", len(chunks), index_name)


def retrieve_keyword_es(query: str, top_k: int = 20, index_name: str = None) -> List[Dict]:
    """BM25 retrieval via Elasticsearch."""
    from app.config import settings
    index_name = index_name or settings.es_index
    es = _get_es()

    results = es.search(index=index_name, body={
        "query": {"multi_match": {
            "query": query,
            "fields": ["text^2", "title^3", "parent_text"],
        }},
        "size": top_k,
    })

    return [
        {
            "text": hit["_source"]["text"],
            "metadata": {
                "slug": hit["_source"].get("slug", ""),
                "title": hit["_source"].get("title", ""),
            },
            "score": hit["_score"],
        }
        for hit in results["hits"]["hits"]
    ]

