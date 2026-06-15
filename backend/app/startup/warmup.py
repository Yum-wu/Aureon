"""BM25 warmup and incremental index update �� runs in background thread at startup.

Extracted from main.py to keep the application entry point slim.
"""

import os
import structlog

logger = structlog.get_logger()

# ���� Global state for health checks ����
bm25_warmup_done = False  # starts False; background thread sets True when ready
index_ready = False  # True once index check completes


def warmup_bm25():
    """Build BM25 index and auto-rebuild vector index if empty or config mismatch.

    Runs in background thread at startup. Non-blocking.
    Uses check_index_upgrade_strategy to determine:
    - skip: index is up-to-date, no action needed
    - rebuild: full rebuild (vector structure/model changed)
    - incremental: only add/remove changed files
    """
    global bm25_warmup_done, index_ready
    try:
        from app.rag.vector_store import check_index_upgrade_strategy, get_collection_stats

        # ȷ�� Qdrant Payload �������ڣ������������ݣ�
        try:
            from app.rag.vector_store import ensure_payload_indexes
            ensure_payload_indexes()
        except Exception as e:
            logger.warning("Payload index check failed (non-fatal): %s", e)

        # ����������������
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        articles_dir = os.path.join(base_dir, "data", "articles")
        strategy = check_index_upgrade_strategy(articles_dir=articles_dir)

        if strategy["action"] == "skip":
            doc_count, chunk_count = get_collection_stats()
            logger.info("Index OK (skip): %d docs, %d chunks �� %s", doc_count, chunk_count, strategy["reason"])
        elif strategy["action"] == "rebuild":
            logger.info("Index rebuild triggered: %s", strategy["reason"])
            try:
                from app.rag.qa_chain import run_index_pipeline
                result = run_index_pipeline(articles_dir)
                logger.info("Auto-rebuild complete: %d docs, %d chunks, %.1fs",
                            result.get("documents_indexed", 0),
                            result.get("chunks_created", 0),
                            result.get("elapsed_seconds", 0))
            except Exception as e:
                logger.error("Auto-rebuild failed: %s", e)
        elif strategy["action"] == "incremental":
            logger.info("Incremental update: %s", strategy["reason"])
            try:
                _incremental_update(strategy, articles_dir)
            except Exception as e:
                logger.error("Incremental update failed, falling back to full rebuild: %s", e)
                try:
                    from app.rag.qa_chain import run_index_pipeline
                    result = run_index_pipeline(articles_dir)
                    logger.info("Fallback rebuild complete: %d docs, %d chunks, %.1fs",
                                result.get("documents_indexed", 0),
                                result.get("chunks_created", 0),
                                result.get("elapsed_seconds", 0))
                except Exception as e2:
                    logger.error("Fallback rebuild also failed: %s", e2)

        # Eagerly load GPU models for faster first-request latency
        try:
            from app.rag.embed_gpu import eager_load_models
            eager_load_models()
        except Exception as e:
            logger.warning("GPU model eager loading failed (non-fatal): %s", e)

        # ���� BM25 �ؼ����������� retrieve_keyword ʹ�ã�
        try:
            from app.rag.vector_store import _build_kw_index
            _build_kw_index()
            from app.rag.vector_store import _kw_docs
            logger.info("BM25 index built: %d docs", len(_kw_docs))
        except Exception as e:
            logger.warning("BM25 index build failed (non-fatal): %s", e)

    except Exception as e:
        logger.warning("BM25 warmup / index check failed (non-fatal): %s", e)
    finally:
        index_ready = True
        bm25_warmup_done = True


def _incremental_update(strategy: dict, articles_dir: str):
    """ִ�������������£�ɾ���Ƴ����ļ��������������ļ���"""
    from app.rag.vector_store import delete_from_index, add_to_index
    from app.rag.loader import load_markdown_files

    # 1. ɾ�����Ƴ����ļ�
    for filename in strategy["files_to_del"]:
        try:
            delete_from_index(filename)
            logger.info("Incremental: deleted '%s'", filename)
        except Exception as e:
            logger.warning("Incremental: failed to delete '%s': %s", filename, e)

    # 2. ���ز������������ļ�
    if strategy["files_to_add"]:
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        except ImportError:
            from langchain_text_splitters import RecursiveCharacterTextSplitter

        # ����ȫ���ļ���Ȼ����˳���Ҫ������
        all_docs = load_markdown_files(articles_dir)
        add_set = set(strategy["files_to_add"])
        new_docs = [d for d in all_docs if d["metadata"].get("source", "") in add_set]

        all_chunks = []
        for doc in new_docs:
            parent_splitter = RecursiveCharacterTextSplitter(
                chunk_size=1500, chunk_overlap=100,
                separators=["\n## ", "\n### ", "\n\n", "\n", " ", ""],
            )
            child_splitter = RecursiveCharacterTextSplitter(
                chunk_size=512, chunk_overlap=50,
                separators=["\n", " ", ""],
            )

            parents = parent_splitter.split_text(doc["content"])
            for parent_idx, parent_text in enumerate(parents):
                children = child_splitter.split_text(parent_text)
                for child_text in children:
                    all_chunks.append({
                        "text": child_text,
                        "metadata": {
                            **doc["metadata"],
                            "parent_text": parent_text,
                            "parent_idx": parent_idx,
                        },
                    })

        if all_chunks:
            add_to_index(all_chunks)
            logger.info("Incremental: added %d chunks from %d new files",
                        len(all_chunks), len(new_docs))
