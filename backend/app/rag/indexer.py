"""
Indexing pipeline and async RAG operations for RAG system.
Contains: run_incremental_index, run_index_pipeline, contextual retrieval,
          async generate/retrieve/query functions.
"""

import os
import time
import asyncio
from typing import List, Dict, Any

from app.rag.vector_store import (
    retrieve,
    retrieve_keyword,
    format_context,
    save_index,
    rerank,
)
from app.rag.query_rewriter import is_cross_article_query, hyde_retrieve_async
from app.rag.models import RAGQueryResponse, SourceItem
from app.rag.ensemble_reranker import get_ensemble_reranker
from app.rag.classifier import (
    _extract_title_keywords,
    compress_context,
    classify_query_answerable_sync,
    _NEGATIVE_DETECTION_ENABLED,
    _HIGH_SCORE_SKIP_THRESHOLD,
)
from app.rag.generator import (
    QA_SYSTEM_PROMPT,
    QA_SYSTEM_PROMPT_EN,
    generate_answer,
    _HYDE_ENABLED,
    _HYDE_FALLBACK_THRESHOLD,
)
from app.utils.lang_detect import detect_language, lang_instruction
from app.config import settings

import structlog

logger = structlog.get_logger()

# ── Retrieval constants (shared with retriever.py) ──
_RRF_K = settings.rrf_k
_RETRIEVAL_MULTIPLIER = settings.retrieval_multiplier
_RERANK_CANDIDATES = settings.rerank_candidates
_ADAPTIVE_RERANK_ENABLED = settings.adaptive_rerank_enabled
_ENSEMBLE_RERANK_ENABLED = settings.ensemble_rerank_enabled
_MIN_RELEVANCE_SCORE = settings.min_relevance_score
_VECTOR_MIN_COSINE = settings.vector_min_cosine
_VECTOR_MAX_CONTRIB = settings.vector_max_contrib
_VECTOR_CONFIDENCE_THRESHOLD = settings.vector_confidence_threshold


def run_incremental_index(filepath: str) -> dict:
    """Incremental index for a single uploaded file.

    Loads → splits → adds to existing Chroma collection (does NOT rebuild).
    """
    start = time.time()

    from app.rag.loader import load_single_document
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 1. Load single document
    doc = load_single_document(filepath)
    if not doc or not doc.get("content", "").strip():
        return {
            "status": "error",
            "filename": os.path.basename(filepath),
            "documents_indexed": 0,
            "chunks_created": 0,
            "elapsed_seconds": 0,
            "message": "文件为空或无法读取",
        }

    # 2. Split into parent-child structure
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=80,
        separators=["\n", " ", ""],
    )

    parents = parent_splitter.split_text(doc["content"])
    chunks = []
    for parent_idx, parent_text in enumerate(parents):
        children = child_splitter.split_text(parent_text)
        for child_text in children:
            chunks.append({
                "text": child_text,
                "metadata": {
                    **doc["metadata"],
                    "parent_text": parent_text,
                    "parent_idx": parent_idx,
                },
            })

    # 3. 删除该文件的旧块，避免重复索引
    from app.rag.vector_store import add_to_index, delete_from_index
    filename = os.path.basename(filepath)
    delete_from_index(filename)
    logger.info("Deleted old chunks for '%s' before re-indexing", filename)

    # 4. Add to existing index (incremental)
    add_to_index(chunks)

    elapsed = time.time() - start
    fname = os.path.basename(filepath).encode("ascii", errors="replace").decode("ascii")
    logger.info("rag.incremental_index", file=fname, chunks=len(chunks), elapsed_s=round(elapsed, 1))

    return {
        "status": "ok",
        "filename": os.path.basename(filepath),
        "documents_indexed": 1,
        "chunks_created": len(chunks),
        "elapsed_seconds": round(elapsed, 1),
    }


# ── Contextual Retrieval: LLM-generated context prefixes ──
# Anthropic's technique: prepend each chunk with a brief context explaining
# its source document and position. Reduces retrieval errors by up to 49%.
# Reference: https://www.anthropic.com/news/contextual-retrieval

_CONTEXTUAL_PROMPT_TEMPLATE = """Generate a short context prefix (1-2 sentences) for the following text chunk. The prefix should explain:
1. Which document this chunk comes from (use the document title)
2. What topic/section this chunk covers within that document

Keep the prefix under 50 words. Write in the same language as the chunk (Chinese or English).

Document title: {title}
Full document (for reference):
{document}

Text chunk:
{chunk}

Context prefix:"""


async def _generate_context_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10):
    """并发生成 contextual prefixes。"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _process_one(chunk_text, doc_text):
        async with semaphore:
            prompt = f"""<document>
{doc_text}
</document>
Here is the chunk we want to situate within the whole document
<chunk>
{chunk_text}
</chunk>
Please give a short succinct context to situate this chunk within the overall document for the purposes of improving search retrieval of the chunk. Answer only with the succinct context and nothing else."""
            result = await asyncio.to_thread(llm_call_fn, [{"role": "user", "content": prompt}])
            return result if isinstance(result, str) else str(result)

    tasks = [_process_one(c, d) for c, d in chunks_with_docs]
    return await asyncio.gather(*tasks)


def _add_contextual_prefixes(
    chunks: List[Dict[str, Any]],
    docs: List[Dict[str, Any]],
    llm_call_fn,
    batch_size: int = 10,
) -> List[Dict[str, Any]]:
    """Add LLM-generated context prefixes to each chunk.

    For each chunk, generates a brief prefix explaining its source document
    and position within the document. The prefix is prepended to the chunk text
    for embedding, and stored in metadata for display.

    Uses concurrent LLM calls via _generate_context_prefixes_async
    for improved throughput compared to serial processing.

    Args:
        chunks: List of chunk dicts with "text" and "metadata" fields
        docs: List of document dicts with "metadata" and "content" fields
        llm_call_fn: LLM invocation function (messages -> response)
        batch_size: Number of chunks to process per LLM call (for efficiency)

    Returns:
        Chunks with contextual prefixes added to text and metadata
    """
    # Build doc lookup by slug
    doc_map = {doc["metadata"]["slug"]: doc for doc in docs}

    # Build (chunk_text, doc_text) pairs for concurrent processing
    chunks_with_docs = []
    valid_indices = []  # Track which chunks have a matching document
    for i, chunk in enumerate(chunks):
        slug = chunk["metadata"].get("slug", "")
        doc = doc_map.get(slug)
        if doc:
            doc_text = doc["content"][:2000]  # truncate for prompt
            chunk_text = chunk["text"][:300]  # truncate for prompt
            chunks_with_docs.append((chunk_text, doc_text))
            valid_indices.append(i)

    if not chunks_with_docs:
        return chunks

    # 并发生成 contextual prefixes
    prefixes = asyncio.run(_generate_context_prefixes_async(chunks_with_docs, llm_call_fn, max_concurrent=10))

    total_prefixes = 0
    for idx, prefix in zip(valid_indices, prefixes):
        prefix = prefix.strip()
        if prefix and len(prefix) < 200:  # sanity check
            chunks[idx]["metadata"]["contextual_prefix"] = prefix
            # Prepend prefix to text for embedding
            chunks[idx]["text"] = f"{prefix}\n\n{chunks[idx]['text']}"
            total_prefixes += 1

    logger.info("Contextual Retrieval: added %d prefixes to %d chunks", total_prefixes, len(chunks))
    return chunks


def run_index_pipeline(
    articles_dir: str,
    llm_call_fn = None,
    enable_contextual: bool = True,
    enable_semantic_chunking: bool = False,
) -> dict:
    """Full index pipeline: load → split → [contextual prefix] → embed → store.

    When enable_contextual=True and llm_call_fn is provided, each chunk gets
    an LLM-generated context prefix explaining its source document and position.
    This is Anthropic's Contextual Retrieval technique — reduces retrieval errors
    by up to 49% (https://www.anthropic.com/news/contextual-retrieval).

    enable_semantic_chunking defaults to False because it requires embedding API
    calls during the splitting phase, which is very slow and prone to stalling.
    """
    start = time.time()

    from app.rag.loader import load_markdown_files
    try:
        from langchain.text_splitter import RecursiveCharacterTextSplitter
    except ImportError:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

    # 1. Load
    docs = load_markdown_files(articles_dir)
    if not docs:
        return {
            "status": "error",
            "documents_indexed": 0,
            "chunks_created": 0,
            "elapsed_seconds": 0,
            "message": "没有找到 Markdown 文件",
        }
    logger.info("run_index_pipeline: loaded %d docs, starting chunking (semantic=%s)", len(docs), enable_semantic_chunking)

    # 2. Split into parent-child structure
    # Parent: 1500 chars (rich context for LLM)
    # Child:  512 chars (medium chunks for balanced retrieval, 80 overlap)
    parent_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1500,
        chunk_overlap=100,
        separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
    )
    child_splitter = RecursiveCharacterTextSplitter(
        chunk_size=512,
        chunk_overlap=80,
        separators=["\n", " ", ""],
    )

    chunks = []
    for doc in docs:
        parents = parent_splitter.split_text(doc["content"])
        for parent_idx, parent_text in enumerate(parents):
            # Use semantic chunking if enabled, otherwise fixed-size splitting
            if enable_semantic_chunking:
                try:
                    from app.rag.semantic_splitter import SemanticTextSplitter
                    from app.rag.vector_store import embed_texts_as_list
                    semantic_splitter = SemanticTextSplitter(
                        embed_fn=embed_texts_as_list,
                        breakpoint_threshold=80.0,
                        max_chunk_size=1024,
                        min_chunk_size=150,
                    )
                    children = semantic_splitter.split_text(parent_text)
                except Exception as e:
                    logger.warning("Semantic chunking failed for parent %d: %s, falling back to fixed", parent_idx, e)
                    children = child_splitter.split_text(parent_text)
            else:
                children = child_splitter.split_text(parent_text)
            for child_text in children:
                chunks.append({
                    "text": child_text,
                    "metadata": {
                        **doc["metadata"],
                        "parent_text": parent_text,
                        "parent_idx": parent_idx,
                    },
                })

    # 3. Contextual Retrieval: add LLM-generated context prefix to each chunk
    contextual_count = 0
    if enable_contextual and llm_call_fn and chunks:
        chunks = _add_contextual_prefixes(chunks, docs, llm_call_fn)
        contextual_count = sum(1 for c in chunks if c.get("metadata", {}).get("contextual_prefix"))

    # 4. Store (save_index_qdrant handles embedding internally via stream embed-upsert)
    logger.info("run_index_pipeline: %d chunks created, starting embed+upsert", len(chunks))
    save_index(chunks)

    elapsed = time.time() - start
    logger.info("rag.index_complete", docs=len(docs), chunks=len(chunks), contextual=contextual_count, elapsed_s=round(elapsed, 1))

    return {
        "status": "ok",
        "documents_indexed": len(docs),
        "chunks_created": len(chunks),
        "contextual_prefixes": contextual_count,
        "elapsed_seconds": round(elapsed, 1),
    }


# ── Async RAG Pipeline ──
# Parallel BM25 + Vector retrieval via asyncio.gather


async def generate_answer_async(
    query: str,
    context: str,
    llm_call_fn,
    system_prompt: str = None,
    lang: str = "zh",
) -> str:
    """Async version of generate_answer. Call LLM with context and query."""
    if system_prompt is None:
        system_prompt = QA_SYSTEM_PROMPT_EN if lang == "en" else QA_SYSTEM_PROMPT
    lang_instr = lang_instruction(lang).strip()
    prompt = system_prompt.format(context=context, lang_instruction=lang_instr)
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": query},
    ]
    return await llm_call_fn(messages)


async def hybrid_retrieve_async(
    query: str,
    top_k: int = 3,
    lang_filter: str = None,
) -> List[Dict[str, Any]]:
    """Async hybrid retrieval: BM25 + Vector in parallel via asyncio.gather.

    Runs BM25 keyword search and vector search concurrently,
    then fuses results with RRF. Includes all quality filters from sync version.

    Args:
        query: Query text
        top_k: Number of results to return
        lang_filter: Optional language filter

    Returns:
        List of top_k document chunks
    """
    import asyncio

    # Run both retrievers in parallel
    bm25_task = asyncio.to_thread(retrieve_keyword, query, top_k=top_k * _RETRIEVAL_MULTIPLIER, lang_filter=lang_filter)

    from app.config import settings
    if settings.vector_backend == "qdrant":
        vector_task = asyncio.to_thread(retrieve, query, top_k=top_k * _RETRIEVAL_MULTIPLIER, lang_filter=lang_filter)
    else:
        vector_task = asyncio.to_thread(retrieve, query, top_k=top_k * _RETRIEVAL_MULTIPLIER, use_mmr=False, lang_filter=lang_filter)

    bm25_results, vector_results = await asyncio.gather(bm25_task, vector_task)

    # ── Pre-RRF score filtering ──
    if vector_results:
        filtered_vector = [
            r for r in vector_results
            if r.get("metadata", {}).get("cosine_score", 1.0) >= _VECTOR_MIN_COSINE
        ]
        if not filtered_vector and vector_results:
            logger.info(
                "All %d vector results below cosine threshold %.2f, degrading to BM25-only",
                len(vector_results), _VECTOR_MIN_COSINE,
            )
        vector_results = filtered_vector

    # If only one retriever has results, use it directly
    if not bm25_results and not vector_results:
        return []
    if not vector_results:
        return bm25_results[:top_k]
    if not bm25_results:
        return vector_results[:top_k]

    # RRF fusion with deduplication
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict] = {}

    def _doc_key(doc: Dict) -> str:
        """Unique key for deduplication — uses slug (article ID)."""
        return doc.get("metadata", {}).get("slug", "") or doc.get("text", "")[:50]

    # Dedup by slug within each retriever: keep best rank per source
    def _dedup_by_source(results: List[Dict]) -> List[Dict]:
        seen: Dict[str, int] = {}
        deduped = []
        for rank, doc in enumerate(results, 1):
            key = _doc_key(doc)
            if key not in seen:
                seen[key] = rank
                deduped.append(doc)
        return deduped

    bm25_deduped = _dedup_by_source(bm25_results)
    vector_deduped = _dedup_by_source(vector_results)

    for rank, doc in enumerate(bm25_deduped, 1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        doc_map[key] = doc

    _vector_contrib_count = 0
    for rank, doc in enumerate(vector_deduped, 1):
        if _vector_contrib_count >= _VECTOR_MAX_CONTRIB:
            break
        cosine = doc.get("metadata", {}).get("cosine_score", 1.0)
        if cosine < _VECTOR_CONFIDENCE_THRESHOLD:
            continue
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        if key not in doc_map:
            doc_map[key] = doc
        elif "_embedding" in doc:
            # Preserve embedding from vector result for downstream reuse
            doc_map[key]["_embedding"] = doc["_embedding"]
        _vector_contrib_count += 1

    # Title/slug boost
    _title_boost_keywords = _extract_title_keywords(query)
    if _title_boost_keywords:
        for key, doc in doc_map.items():
            title = (doc.get("metadata", {}).get("title", "") + " " +
                     doc.get("metadata", {}).get("slug", "")).lower()
            matches = sum(1 for kw in _title_boost_keywords if kw in title)
            if matches > 0:
                boost = 1.0 + 0.5 * matches
                rrf_scores[key] *= boost

    # Sort by RRF score descending
    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # Take candidates for diversity selection
    candidate_limit = min(len(ranked), max(_RERANK_CANDIDATES, top_k * 3))
    candidates = []
    for key, score in ranked[:candidate_limit]:
        doc = doc_map[key].copy()
        doc["score"] = score
        candidates.append(doc)

    # ── Adaptive Re-ranking based on Query Complexity ──
    if _ADAPTIVE_RERANK_ENABLED and len(candidates) > top_k:
        try:
            from app.rag.query_classifier import get_reranking_strategy
            strategy = get_reranking_strategy(query)
            complexity = strategy["complexity"]

            if complexity == "simple":
                logger.info("Adaptive rerank: SKIP (simple query)")
            elif complexity == "medium":
                logger.info("Adaptive rerank: SINGLE_BGE (medium)")
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
            elif complexity == "complex" and _ENSEMBLE_RERANK_ENABLED:
                logger.info("Adaptive rerank: ENSEMBLE (complex)")
                ensemble = get_ensemble_reranker()
                candidates = await ensemble.rerank(query, candidates, top_k=min(len(candidates), top_k * 3))
            else:
                logger.info("Adaptive rerank: SINGLE_BGE (default)")
                rerank_limit = max(top_k * 3, 10)
                candidates = rerank(query, candidates, top_k=min(len(candidates), rerank_limit))
        except Exception as e:
            logger.warning("Adaptive re-ranking failed, using RRF candidates as-is: %s", e)

    # Diversity selection for cross-article queries
    if is_cross_article_query(query):
        selected = []
        seen_slugs = set()
        for doc in candidates:
            slug = doc.get("metadata", {}).get("slug", "")
            if slug not in seen_slugs:
                seen_slugs.add(slug)
                selected.append(doc)
                if len(selected) >= top_k:
                    break
        if len(selected) < top_k:
            for doc in candidates:
                if doc not in selected:
                    selected.append(doc)
                    if len(selected) >= top_k:
                        break
    else:
        selected = candidates[:top_k]

    # Relevance gate
    if selected and selected[0].get("score", 0) < _MIN_RELEVANCE_SCORE:
        logger.info("All results below relevance threshold (max=%.4f < %.4f), returning empty",
                     selected[0]["score"], _MIN_RELEVANCE_SCORE)
        return []

    return selected


async def rag_query_async(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    lang: str | None = None,
    filter_lang: str | None = None,
    chunking_strategy: str = "default",
    request_id: str = None,
) -> RAGQueryResponse:
    """Async RAG pipeline: retrieve (parallel) -> compress -> generate.

    Uses asyncio.gather for parallel BM25 + vector retrieval.

    Args:
        query: Query text
        llm_call_fn: LLM call function (can be sync or async)
        top_k: Number of results
        lang: Response language
        filter_lang: Document language filter
        chunking_strategy: Chunking strategy to use:
            - "default": Use existing chunking (parent-child from index pipeline)
            - "parent_child": Explicitly use ParentChildSplitter for document splitting
        request_id: Optional request ID for tracing
    """
    import asyncio
    from app.observability import QueryTracer
    from app.observability.tracing import create_span

    # Initialize tracer if request_id provided
    tracer = QueryTracer(request_id=request_id or '', query=query) if request_id else None

    if lang is None:
        lang = detect_language(query)

    # If parent_child strategy requested, apply it at query time for
    # ad-hoc documents. For pre-indexed data, the strategy was applied
    # during indexing (run_index_pipeline already uses parent-child).
    if chunking_strategy == "parent_child":
        logger.info("Using parent_child chunking strategy for query: %s", query[:50])

    # 1. Parallel retrieval (with tracing span)
    with create_span("retrieval", {"query_length": len(query), "top_k": top_k}) as retrieval_span:
        #    If HyDE is enabled, use hypothetical answer for retrieval
        if _HYDE_ENABLED:
            logger.info("HyDE enabled (async): using hypothetical answer for retrieval")
            chunks = await hyde_retrieve_async(
                query,
                llm_call_fn,
                top_k=top_k,
                lang=lang,
                lang_filter=filter_lang,
            )
            # If HyDE returns poor results, fallback to hybrid_retrieve_async
            if chunks:
                top_score = max(c.get("score", 0) for c in chunks)
                if top_score < _HYDE_FALLBACK_THRESHOLD:
                    logger.info(
                        "HyDE async: poor results (score=%.4f < %.4f), falling back to hybrid retrieval",
                        top_score, _HYDE_FALLBACK_THRESHOLD,
                    )
                    chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)
            else:
                logger.info("HyDE async: no results, falling back to hybrid retrieval")
                chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)
        else:
            chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)
        if retrieval_span is not None:
            retrieval_span.set_attribute("chunk_count", len(chunks))

    # 2. Negative detection: LLM classifier for queries the KB can't answer.
    if _NEGATIVE_DETECTION_ENABLED and chunks:
        top_score = max(c.get("score", 0) for c in chunks) if chunks else 0
        if top_score < _HIGH_SCORE_SKIP_THRESHOLD:
            if not await asyncio.to_thread(classify_query_answerable_sync, query, llm_call_fn):
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

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Context compression (with tracing span)
    with create_span("compression", {"input_chunk_count": len(chunks)}) as compression_span:
        if chunks:
            chunks = await asyncio.to_thread(compress_context, query, chunks)
        if compression_span is not None:
            compression_span.set_attribute("output_chunk_count", len(chunks))

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Format context
    context = format_context(chunks)

    # 4. Generate (with tracing span)
    with create_span("llm_generation", {"context_length": len(context)}) as llm_span:
        if asyncio.iscoroutinefunction(llm_call_fn):
            answer = await generate_answer_async(query, context, llm_call_fn, lang=lang)
        else:
            answer = generate_answer(query, context, llm_call_fn, lang=lang)
        if llm_span is not None:
            llm_span.set_attribute("answer_length", len(answer))

    # 5. Build response
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

    # 6. Record trace if tracer is active
    if tracer:
        tracer.end_retrieval([{"chunk_id": s.chunk_id, "title": s.title, "slug": s.slug} for s in sources])
        tracer.end_rerank([{"chunk_id": s.chunk_id, "title": s.title} for s in sources])
        tracer.record()

    return RAGQueryResponse(answer=answer, sources=sources)
