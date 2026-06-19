"""
QA chain for RAG system (backward-compatible facade).

This module is a thin facade that re-exports all public functions and constants
from the following sub-modules:
- app.rag.classifier  (query classification, context compression)
- app.rag.retriever   (hybrid retrieval, multi-query retrieval)
- app.rag.generator   (answer generation, RAG query pipelines)
- app.rag.indexer     (indexing pipeline, async RAG operations)
"""

# 鈹�鈹� retriever.py 鈹�鈹�
from app.rag.retriever import hybrid_retrieve, multi_query_retrieve

# 鈹�鈹� generator.py 鈹�鈹�
from app.rag.generator import (
    QA_SYSTEM_PROMPT,
    QA_SYSTEM_PROMPT_EN,
    generate_answer,
    rag_query,
    rag_query_astream,
    rag_query_with_cache,
)

# 鈹�鈹� indexer.py 鈹�鈹�
from app.rag.indexer import run_incremental_index, run_index_pipeline, rag_query_async

# -- embedding.py + index_manager.py (for test patches) --
from app.rag.embedding import embed_texts_llm
from app.rag.index_manager import retrieve, save_index

# Semantic chunking setting (used by run_index_pipeline and external references)
SEMANTIC_CHUNKING_ENABLED = __import__('app.config', fromlist=['settings']).settings.semantic_chunking_enabled

__all__ = [
    # retriever
    "hybrid_retrieve",
    "multi_query_retrieve",
    # generator
    "QA_SYSTEM_PROMPT",
    "QA_SYSTEM_PROMPT_EN",
    "generate_answer",
    "rag_query",
    "rag_query_astream",
    "rag_query_with_cache",
    # indexer
    "run_incremental_index",
    "run_index_pipeline",
    "rag_query_async",
    # settings
    "SEMANTIC_CHUNKING_ENABLED",
    # embedding + index_manager (test patches)
    "embed_texts_llm",
    "retrieve",
    "save_index",
]
