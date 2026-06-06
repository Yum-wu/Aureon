# RAG Performance Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ChromaDB with Qdrant, enable GPU embedding/reranker, async RAG pipeline, and concurrent test infrastructure to support 1000+ document scale.

**Architecture:** Qdrant (Rust vector DB) replaces ChromaDB for 10-100x performance. BGE-large-zh runs on GPU with fp16 for 13x embedding speedup. BM25 + Vector retrieval runs in parallel via asyncio.gather. pytest-xdist enables parallel test execution.

**Tech Stack:** Qdrant, sentence-transformers (GPU fp16), asyncio, pytest-xdist, pytest-asyncio, FastAPI async

**Spec:** `docs/superpowers/specs/2026-06-06-rag-performance-optimization-design.md`

---

## File Structure

### New Files
| File | Responsibility |
|------|---------------|
| `backend/app/rag/qdrant_store.py` | Qdrant vector store operations (save, retrieve, delete, stats) |
| `backend/app/rag/embed_gpu.py` | GPU-accelerated embedding and reranking with fp16 |
| `backend/tests/benchmark_concurrent.py` | Concurrent benchmark framework with asyncio |
| `backend/tests/test_qdrant_store.py` | Unit tests for Qdrant store |
| `backend/tests/test_embed_gpu.py` | Unit tests for GPU embedding |
| `backend/tests/test_async_pipeline.py` | Unit tests for async RAG pipeline |

### Modified Files
| File | Changes |
|------|---------|
| `docker-compose.yml` | Add Qdrant service |
| `backend/requirements.txt` | Add qdrant-client, pytest-xdist |
| `backend/app/config.py` | Add qdrant_url, gpu_enabled settings |
| `backend/app/rag/vector_store.py` | Delegate to qdrant_store when backend=qdrant |
| `backend/app/rag/qa_chain.py` | Add async versions of hybrid_retrieve, rag_query |
| `backend/app/routers/rag.py` | Use async RAG pipeline |
| `backend/tests/conftest.py` | pytest-xdist isolation, async fixtures |
| `pyproject.toml` | pytest-xdist config |

---

## Phase 1: Qdrant + GPU Infrastructure

### Task 1: Add Qdrant Docker Service

**Files:**
- Modify: `docker-compose.yml`

- [ ] **Step 1: Add Qdrant service to docker-compose.yml**

```yaml
# Add after existing services
  qdrant:
    image: qdrant/qdrant:v1.12.1
    ports:
      - "6333:6333"
      - "6334:6334"
    volumes:
      - qdrant_data:/qdrant/storage
    environment:
      QDRANT__SERVICE__GRPC_PORT: 6334
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:6333/healthz"]
      interval: 10s
      timeout: 5s
      retries: 3

# Add to volumes section
volumes:
  qdrant_data:
```

- [ ] **Step 2: Start Qdrant and verify health**

Run: `docker-compose up -d qdrant && sleep 5 && curl http://localhost:6333/healthz`
Expected: `{"status":"ok"}` or similar health response

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add Qdrant vector database service"
```

---

### Task 2: Add Dependencies and Config

**Files:**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/config.py`

- [ ] **Step 1: Add qdrant-client to requirements.txt**

Add to `backend/requirements.txt`:
```
qdrant-client>=1.12.0
pytest-xdist>=3.5.0
```

- [ ] **Step 2: Install dependencies**

Run: `cd backend && pip install qdrant-client pytest-xdist`
Expected: Successfully installed

- [ ] **Step 3: Add Qdrant and GPU settings to config.py**

Add to the Settings class in `backend/app/config.py`:
```python
# Qdrant settings
qdrant_url: str = "http://localhost:6333"
qdrant_api_key: str = ""
qdrant_collection: str = "aureon"

# GPU settings
gpu_enabled: bool = True
embedding_batch_size: int = 64
reranker_device: str = "cuda"  # "cuda" or "cpu"
```

- [ ] **Step 4: Commit**

```bash
git add backend/requirements.txt backend/app/config.py
git commit -m "feat: add Qdrant and GPU configuration settings"
```

---

### Task 3: Implement Qdrant Store

**Files:**
- Create: `backend/app/rag/qdrant_store.py`
- Create: `backend/tests/test_qdrant_store.py`

- [ ] **Step 1: Write tests for Qdrant store**

Create `backend/tests/test_qdrant_store.py`:
```python
"""Tests for Qdrant vector store backend."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestQdrantStore:
    """Test Qdrant store operations."""

    def test_create_collection(self):
        """Test collection creation with correct params."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        # Mock client
        store._client = MagicMock()
        store.create_collection(dimension=1024)
        store._client.create_collection.assert_called_once()

    def test_save_chunks(self):
        """Test batch saving of chunks."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()

        chunks = [
            {"text": "test chunk", "metadata": {"slug": "test", "title": "Test"}},
            {"text": "another chunk", "metadata": {"slug": "test2", "title": "Test2"}},
        ]
        embeddings = np.random.rand(2, 1024).astype(np.float32)

        store.save_chunks(chunks, embeddings)
        store._client.upsert.assert_called()

    def test_retrieve_top_k(self):
        """Test retrieval returns correct number of results."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()

        # Mock search results
        mock_result = MagicMock()
        mock_result.id = "chunk_0"
        mock_result.score = 0.95
        mock_result.payload = {"text": "test", "metadata": {"slug": "test"}}
        store._client.search.return_value = [mock_result]

        results = store.retrieve(query_embedding=np.random.rand(1024), top_k=3)
        assert len(results) <= 3
        assert results[0]["score"] == 0.95

    def test_delete_by_source(self):
        """Test deletion by source filename."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()

        store.delete_by_source("test.md")
        store._client.delete.assert_called()

    def test_get_collection_stats(self):
        """Test collection statistics."""
        from app.rag.qdrant_store import QdrantStore
        store = QdrantStore(url="http://localhost:6333")
        store._client = MagicMock()
        store._client.get_collection.return_value.points_count = 100

        count = store.get_point_count()
        assert count == 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_qdrant_store.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'app.rag.qdrant_store'"

- [ ] **Step 3: Implement QdrantStore**

Create `backend/app/rag/qdrant_store.py`:
```python
"""Qdrant vector store backend for RAG system.

Replaces ChromaDB for production deployments. Supports:
- Persistent storage with mmap for large collections
- GPU-accelerated index building
- Metadata filtering (language, source, etc.)
- Batch operations for indexing
"""
import os
from typing import List, Dict, Any, Optional
import numpy as np

import structlog

logger = structlog.get_logger(__name__)

try:
    from qdrant_client import QdrantClient
    from qdrant_client.models import (
        VectorParams, Distance, PointStruct, Filter,
        FieldCondition, MatchValue
    )
    HAS_QDRANT = True
except ImportError:
    HAS_QDRANT = False
    logger.warning("qdrant-client not installed, Qdrant backend unavailable")


class QdrantStore:
    """Qdrant vector store for RAG embeddings.

    Args:
        url: Qdrant server URL (default: http://localhost:6333)
        api_key: Optional API key for authentication
        collection_name: Name of the collection (default: aureon)
    """

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str = "",
        collection_name: str = "aureon",
    ):
        if not HAS_QDRANT:
            raise ImportError("qdrant-client not installed. Run: pip install qdrant-client")

        self.url = url
        self.collection_name = collection_name
        self._client: Optional[QdrantClient] = None
        self._api_key = api_key

    def _get_client(self) -> QdrantClient:
        """Lazy-init Qdrant client."""
        if self._client is None:
            kwargs = {"url": self.url}
            if self._api_key:
                kwargs["api_key"] = self._api_key
            self._client = QdrantClient(**kwargs)
            logger.info("Qdrant client connected: %s", self.url)
        return self._client

    def create_collection(self, dimension: int = 1024, force: bool = False) -> None:
        """Create or recreate collection.

        Args:
            dimension: Vector dimension (default 1024 for BGE-large-zh)
            force: If True, delete existing collection first
        """
        client = self._get_client()

        if force:
            try:
                client.delete_collection(self.collection_name)
                logger.info("Deleted existing collection: %s", self.collection_name)
            except Exception:
                pass

        try:
            client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=dimension,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created collection: %s (dim=%d)", self.collection_name, dimension)
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info("Collection already exists: %s", self.collection_name)
            else:
                raise

    def save_chunks(
        self,
        chunks: List[Dict[str, Any]],
        embeddings: np.ndarray,
        batch_size: int = 100,
    ) -> None:
        """Save chunks with pre-computed embeddings.

        Args:
            chunks: List of chunk dicts with 'text' and 'metadata'
            embeddings: Pre-computed embeddings array (N x dim)
            batch_size: Batch size for upsert operations
        """
        client = self._get_client()

        for start in range(0, len(chunks), batch_size):
            end = min(start + batch_size, len(chunks))
            points = []

            for i in range(start, end):
                chunk = chunks[i]
                meta = chunk.get("metadata", {})
                points.append(PointStruct(
                    id=i,
                    vector=embeddings[i].tolist(),
                    payload={
                        "text": chunk["text"],
                        "source": meta.get("source", ""),
                        "title": meta.get("title", ""),
                        "slug": meta.get("slug", ""),
                        "language": meta.get("language", "unknown"),
                        "parent_text": meta.get("parent_text", ""),
                        "parent_idx": meta.get("parent_idx", -1),
                    },
                ))

            client.upsert(collection_name=self.collection_name, points=points)

        logger.info("Saved %d chunks to Qdrant (%s)", len(chunks), self.collection_name)

    def retrieve(
        self,
        query_embedding: np.ndarray,
        top_k: int = 3,
        lang_filter: Optional[str] = None,
        score_threshold: float = 0.0,
    ) -> List[Dict[str, Any]]:
        """Retrieve top-k similar chunks.

        Args:
            query_embedding: Query vector (1D array)
            top_k: Number of results to return
            lang_filter: Optional language filter ("zh" or "en")
            score_threshold: Minimum similarity score

        Returns:
            List of chunk dicts with text, metadata, and score
        """
        client = self._get_client()

        query_filter = None
        if lang_filter:
            query_filter = Filter(
                must=[FieldCondition(key="language", match=MatchValue(value=lang_filter))]
            )

        results = client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding.tolist(),
            limit=top_k,
            query_filter=query_filter,
            score_threshold=score_threshold,
        )

        return [
            {
                "text": r.payload.get("text", ""),
                "metadata": {
                    "source": r.payload.get("source", ""),
                    "title": r.payload.get("title", ""),
                    "slug": r.payload.get("slug", ""),
                    "language": r.payload.get("language", "unknown"),
                    "parent_text": r.payload.get("parent_text", ""),
                    "parent_idx": r.payload.get("parent_idx", -1),
                    "cosine_score": r.score,
                },
                "score": r.score,
            }
            for r in results
        ]

    def delete_by_source(self, source_filename: str) -> int:
        """Delete all chunks from a specific source file.

        Args:
            source_filename: The source filename to delete

        Returns:
            Number of points deleted (approximate)
        """
        client = self._get_client()

        count_before = self.get_point_count()
        client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="source", match=MatchValue(value=source_filename))]
            ),
        )
        count_after = self.get_point_count()

        deleted = count_before - count_after
        logger.info("Deleted %d chunks for '%s' from Qdrant", deleted, source_filename)
        return deleted

    def get_point_count(self) -> int:
        """Get total number of points in collection."""
        client = self._get_client()
        info = client.get_collection(self.collection_name)
        return info.points_count

    def get_indexed_sources(self) -> set:
        """Get set of source filenames currently indexed."""
        client = self._get_client()
        # Scroll through all points to collect unique sources
        sources = set()
        offset = None
        while True:
            result = client.scroll(
                collection_name=self.collection_name,
                limit=100,
                offset=offset,
                with_payload=["source"],
            )
            points, next_offset = result
            for point in points:
                source = point.payload.get("source", "")
                if source:
                    sources.add(source)
            if next_offset is None:
                break
            offset = next_offset
        return sources

    def health_check(self) -> dict:
        """Check Qdrant connection and collection status."""
        try:
            client = self._get_client()
            collections = client.get_collections().collections
            collection_names = [c.name for c in collections]

            if self.collection_name in collection_names:
                info = client.get_collection(self.collection_name)
                return {
                    "status": "ok",
                    "collection": self.collection_name,
                    "points_count": info.points_count,
                    "status": str(info.status),
                }
            else:
                return {
                    "status": "warning",
                    "message": f"Collection '{self.collection_name}' not found",
                    "available_collections": collection_names,
                }
        except Exception as e:
            return {"status": "error", "message": str(e)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_qdrant_store.py -v`
Expected: All 5 tests PASS (with mocked Qdrant client)

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/qdrant_store.py backend/tests/test_qdrant_store.py
git commit -m "feat: implement Qdrant vector store backend"
```

---

### Task 4: GPU Embedding Optimization

**Files:**
- Create: `backend/app/rag/embed_gpu.py`
- Create: `backend/tests/test_embed_gpu.py`

- [ ] **Step 1: Write tests for GPU embedding**

Create `backend/tests/test_embed_gpu.py`:
```python
"""Tests for GPU-accelerated embedding."""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock


class TestGPUEmbedding:
    """Test GPU embedding wrapper."""

    def test_gpu_embed_returns_correct_shape(self):
        """Test embedding output shape matches input."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")  # cpu for CI
        texts = ["Hello world", "Test sentence"]
        result = embedder.encode(texts)
        assert result.shape[0] == 2
        assert result.shape[1] > 0  # Has dimensions

    def test_gpu_embed_empty_input(self):
        """Test embedding empty input returns empty array."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
        result = embedder.encode([])
        assert result.shape[0] == 0

    def test_gpu_embed_single_text(self):
        """Test embedding single text."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
        result = embedder.encode(["Single test"])
        assert result.shape[0] == 1

    def test_gpu_embed_normalized(self):
        """Test embeddings are L2 normalized."""
        from app.rag.embed_gpu import GPUEmbedder
        embedder = GPUEmbedder(model_name="BAAI/bge-large-zh-v1.5", device="cpu")
        result = embedder.encode(["Test normalization"])
        norms = np.linalg.norm(result, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_gpu_reranker_returns_scores(self):
        """Test reranker returns score for each pair."""
        from app.rag.embed_gpu import GPUReranker
        reranker = GPUReranker(model_name="BAAI/bge-reranker-v2-m3", device="cpu")
        query = "What is RAG?"
        docs = [
            {"text": "RAG is retrieval augmented generation"},
            {"text": "Python is a programming language"},
        ]
        scores = reranker.rerank(query, docs)
        assert len(scores) == 2
        assert all(isinstance(s, float) for s in scores)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_embed_gpu.py -v`
Expected: FAIL with "ModuleNotFoundError"

- [ ] **Step 3: Implement GPUEmbedder and GPUReranker**

Create `backend/app/rag/embed_gpu.py`:
```python
"""GPU-accelerated embedding and reranking for RAG system.

Uses sentence-transformers with fp16 precision for maximum throughput.
Supports both embedding (bi-encoder) and reranking (cross-encoder).
"""
import os
from typing import List, Dict, Any, Optional
import numpy as np

import structlog

logger = structlog.get_logger(__name__)

# Singleton instances for model reuse
_embedder_instance = None
_reranker_instance = None


class GPUEmbedder:
    """GPU-accelerated text embedding with fp16 precision.

    Args:
        model_name: HuggingFace model name (default: BAAI/bge-large-zh-v1.5)
        device: Device to use ("cuda" or "cpu")
        use_fp16: Use half precision for 2x speedup (default: True on GPU)
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-large-zh-v1.5",
        device: str = "cuda",
        use_fp16: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.use_fp16 = use_fp16 and device == "cuda"
        self._model = None

    def _load_model(self):
        """Lazy-load the model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import SentenceTransformer

            model_kwargs = {}
            if self.use_fp16:
                model_kwargs["torch_dtype"] = "float16"

            self._model = SentenceTransformer(
                self.model_name,
                device=self.device,
                model_kwargs=model_kwargs,
            )

            logger.info(
                "GPU Embedder loaded: %s on %s (fp16=%s)",
                self.model_name, self.device, self.use_fp16,
            )
        except Exception as e:
            logger.error("Failed to load embedding model: %s", e)
            raise

    def encode(
        self,
        texts: List[str],
        batch_size: int = 64,
        normalize: bool = True,
        show_progress: bool = False,
    ) -> np.ndarray:
        """Encode texts to embeddings.

        Args:
            texts: List of text strings
            batch_size: Batch size for encoding (larger = faster on GPU)
            normalize: L2 normalize embeddings
            show_progress: Show progress bar

        Returns:
            numpy array of shape (N, dim)
        """
        if not texts:
            return np.array([], dtype=np.float32).reshape(0, 0)

        self._load_model()

        embeddings = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=normalize,
            show_progress_bar=show_progress,
        )

        return np.array(embeddings, dtype=np.float32)

    @property
    def dimension(self) -> int:
        """Get embedding dimension."""
        self._load_model()
        return self._model.get_sentence_embedding_dimension()


class GPUReranker:
    """GPU-accelerated cross-encoder reranker.

    Args:
        model_name: HuggingFace model name (default: BAAI/bge-reranker-v2-m3)
        device: Device to use ("cuda" or "cpu")
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        device: str = "cuda",
    ):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _load_model(self):
        """Lazy-load the cross-encoder model."""
        if self._model is not None:
            return

        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info("GPU Reranker loaded: %s on %s", self.model_name, self.device)
        except Exception as e:
            logger.error("Failed to load reranker model: %s", e)
            raise

    def rerank(
        self,
        query: str,
        chunks: List[Dict[str, Any]],
        top_k: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Rerank chunks by relevance to query.

        Args:
            query: Query text
            chunks: List of chunk dicts with 'text' field
            top_k: Return only top-k results (None = all)

        Returns:
            Chunks sorted by rerank score (descending), with rerank_score added
        """
        if not chunks:
            return []

        if len(chunks) <= 1:
            if chunks:
                chunks[0]["rerank_score"] = 1.0
            return chunks

        self._load_model()

        pairs = [(query, c["text"]) for c in chunks]
        scores = self._model.predict(pairs)

        for chunk, score in zip(chunks, scores):
            chunk["rerank_score"] = float(score)

        reranked = sorted(chunks, key=lambda x: x.get("rerank_score", 0), reverse=True)

        if top_k:
            reranked = reranked[:top_k]

        return reranked


def get_gpu_embedder(
    model_name: str = "BAAI/bge-large-zh-v1.5",
    device: str = "cuda",
) -> GPUEmbedder:
    """Get or create singleton GPU embedder."""
    global _embedder_instance
    if _embedder_instance is None:
        _embedder_instance = GPUEmbedder(model_name=model_name, device=device)
    return _embedder_instance


def get_gpu_reranker(
    model_name: str = "BAAI/bge-reranker-v2-m3",
    device: str = "cuda",
) -> GPUReranker:
    """Get or create singleton GPU reranker."""
    global _reranker_instance
    if _reranker_instance is None:
        _reranker_instance = GPUReranker(model_name=model_name, device=device)
    return _reranker_instance
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_embed_gpu.py -v`
Expected: All 5 tests PASS (on CPU for CI)

- [ ] **Step 5: Commit**

```bash
git add backend/app/rag/embed_gpu.py backend/tests/test_embed_gpu.py
git commit -m "feat: implement GPU-accelerated embedding and reranking"
```

---

### Task 5: Integrate Qdrant + GPU into Vector Store

**Files:**
- Modify: `backend/app/rag/vector_store.py`

- [ ] **Step 1: Add Qdrant import and delegation in vector_store.py**

Add at the top of `backend/app/rag/vector_store.py` after existing imports:
```python
# Qdrant backend integration
_qdrant_store = None

def _get_qdrant_store():
    """Get or create Qdrant store singleton."""
    global _qdrant_store
    if _qdrant_store is None:
        from app.rag.qdrant_store import QdrantStore
        from app.config import settings
        _qdrant_store = QdrantStore(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            collection_name=settings.qdrant_collection,
        )
    return _qdrant_store
```

- [ ] **Step 2: Add GPU embedder integration**

Add after the Qdrant integration:
```python
# GPU embedder integration
_gpu_embedder = None

def _get_gpu_embedder():
    """Get or create GPU embedder singleton."""
    global _gpu_embedder
    if _gpu_embedder is None:
        from app.rag.embed_gpu import GPUEmbedder
        from app.config import settings
        if settings.gpu_enabled:
            _gpu_embedder = GPUEmbedder(device="cuda")
        else:
            _gpu_embedder = GPUEmbedder(device="cpu")
    return _gpu_embedder
```

- [ ] **Step 3: Update save_index to support Qdrant backend**

In the `save_index` function, add Qdrant branch:
```python
def save_index(chunks, embeddings=None, path=None):
    from app.config import settings
    if settings.vector_backend == "qdrant":
        store = _get_qdrant_store()
        embedder = _get_gpu_embedder()
        texts = [c["text"] for c in chunks]
        embs = embedder.encode(texts, batch_size=settings.embedding_batch_size)
        store.create_collection(dimension=embs.shape[1], force=True)
        store.save_chunks(chunks, embs)
        logger.info("Saved %d chunks to Qdrant", len(chunks))
        _build_kw_index(force=True)
        return
    # ... existing ChromaDB logic ...
```

- [ ] **Step 4: Update retrieve to support Qdrant backend**

In the `retrieve` function, add Qdrant branch:
```python
def retrieve(query, top_k=3, use_mmr=True, lang_filter=None):
    from app.config import settings
    if settings.vector_backend == "qdrant":
        store = _get_qdrant_store()
        embedder = _get_gpu_embedder()
        query_emb = embedder.encode([query])[0]
        results = store.retrieve(
            query_embedding=query_emb,
            top_k=top_k,
            lang_filter=lang_filter,
        )
        return results
    # ... existing ChromaDB logic ...
```

- [ ] **Step 5: Run existing tests**

Run: `cd backend && python -m pytest tests/test_vector_store.py -v -x`
Expected: Existing tests still pass (ChromaDB fallback)

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/vector_store.py
git commit -m "feat: integrate Qdrant and GPU embedding into vector store"
```

---

## Phase 2: Async RAG Pipeline

### Task 6: Async Hybrid Retrieve

**Files:**
- Modify: `backend/app/rag/qa_chain.py`
- Create: `backend/tests/test_async_pipeline.py`

- [ ] **Step 1: Write test for async hybrid retrieve**

Create `backend/tests/test_async_pipeline.py`:
```python
"""Tests for async RAG pipeline."""
import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock


class TestAsyncPipeline:
    """Test async RAG pipeline functions."""

    @pytest.mark.asyncio
    async def test_hybrid_retrieve_async_returns_results(self):
        """Test async hybrid retrieve returns merged results."""
        from app.rag.qa_chain import hybrid_retrieve_async

        with patch("app.rag.qa_chain.retrieve_keyword", return_value=[
            {"text": "bm25 result", "metadata": {"slug": "test"}, "score": 0.9}
        ]), patch("app.rag.qa_chain.retrieve", return_value=[
            {"text": "vector result", "metadata": {"slug": "test2"}, "score": 0.8}
        ]):
            results = await hybrid_retrieve_async("test query", top_k=3)
            assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_hybrid_retrieve_async_empty(self):
        """Test async hybrid retrieve with no results."""
        from app.rag.qa_chain import hybrid_retrieve_async

        with patch("app.rag.qa_chain.retrieve_keyword", return_value=[]), \
             patch("app.rag.qa_chain.retrieve", return_value=[]):
            results = await hybrid_retrieve_async("nonexistent", top_k=3)
            assert results == []

    @pytest.mark.asyncio
    async def test_rag_query_async_returns_response(self):
        """Test async RAG query returns proper response."""
        from app.rag.qa_chain import rag_query_async

        mock_llm = AsyncMock(return_value="Test answer")

        with patch("app.rag.qa_chain.hybrid_retrieve_async", return_value=[
            {"text": "context", "metadata": {"slug": "test", "title": "Test"}, "score": 0.9}
        ]), patch("app.rag.qa_chain.compress_context", return_value=[
            {"text": "context", "metadata": {"slug": "test", "title": "Test"}, "score": 0.9}
        ]):
            result = await rag_query_async("test query", mock_llm, top_k=3)
            assert result.answer is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_async_pipeline.py -v`
Expected: FAIL with "cannot import name 'hybrid_retrieve_async'"

- [ ] **Step 3: Implement async hybrid_retrieve_async**

Add to `backend/app/rag/qa_chain.py`:
```python
async def hybrid_retrieve_async(
    query: str,
    top_k: int = 3,
    lang_filter: str = None,
) -> List[Dict[str, Any]]:
    """Async hybrid retrieval: BM25 + Vector in parallel via asyncio.gather.

    Runs BM25 keyword search and vector search concurrently,
    then fuses results with RRF.

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

    # Same fusion logic as synchronous version
    if not bm25_results and not vector_results:
        return []
    if not vector_results:
        return bm25_results[:top_k]
    if not bm25_results:
        return vector_results[:top_k]

    # RRF fusion
    rrf_scores: Dict[str, float] = {}
    doc_map: Dict[str, Dict] = {}

    def _doc_key(doc: Dict) -> str:
        return doc.get("metadata", {}).get("slug", "") or doc.get("text", "")[:50]

    for rank, doc in enumerate(bm25_results, 1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        doc_map[key] = doc

    for rank, doc in enumerate(vector_results, 1):
        key = _doc_key(doc)
        rrf_scores[key] = rrf_scores.get(key, 0) + 1.0 / (_RRF_K + rank)
        if key not in doc_map:
            doc_map[key] = doc

    ranked = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    selected = []
    for key, score in ranked[:top_k]:
        doc = doc_map[key].copy()
        doc["score"] = score
        selected.append(doc)

    return selected
```

- [ ] **Step 4: Implement async rag_query_async**

Add to `backend/app/rag/qa_chain.py`:
```python
async def rag_query_async(
    query: str,
    llm_call_fn,
    top_k: int = 3,
    lang: str | None = None,
    filter_lang: str | None = None,
) -> RAGQueryResponse:
    """Async RAG pipeline: retrieve (parallel) → compress → generate.

    Uses asyncio.gather for parallel BM25 + vector retrieval.

    Args:
        query: Query text
        llm_call_fn: LLM call function (can be sync or async)
        top_k: Number of results
        lang: Response language
        filter_lang: Document language filter
    """
    if lang is None:
        lang = detect_language(query)

    # 1. Parallel retrieval
    chunks = await hybrid_retrieve_async(query, top_k=top_k, lang_filter=filter_lang)

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 2. Context compression
    if chunks:
        chunks = compress_context(query, chunks)

    if not chunks:
        no_result_msg = (
            "No relevant content found in the knowledge base."
            if lang == "en"
            else "知识库中暂无相关内容，请尝试其他问题。"
        )
        return RAGQueryResponse(answer=no_result_msg, sources=[])

    # 3. Format context
    context = format_context(chunks)

    # 4. Generate (support both sync and async LLM)
    if asyncio.iscoroutinefunction(llm_call_fn):
        answer = await generate_answer_async(query, context, llm_call_fn, lang=lang)
    else:
        answer = generate_answer(query, context, llm_call_fn, lang=lang)

    # 5. Build response
    sources = [
        SourceItem(
            title=c["metadata"].get("title", c["metadata"].get("source", "Unknown")),
            slug=c["metadata"].get("slug", ""),
            chunk=c["text"][:200] + "..." if len(c["text"]) > 200 else c["text"],
            score=c.get("score"),
        )
        for c in chunks
    ]

    return RAGQueryResponse(answer=answer, sources=sources)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_async_pipeline.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/rag/qa_chain.py backend/tests/test_async_pipeline.py
git commit -m "feat: add async hybrid_retrieve and rag_query with parallel retrieval"
```

---

### Task 7: Update RAG Router for Async

**Files:**
- Modify: `backend/app/routers/rag.py`

- [ ] **Step 1: Add async RAG query endpoint**

Add to `backend/app/routers/rag.py` (find the existing `/query` endpoint and add async variant):
```python
@router.post("/query/async")
async def rag_query_async_endpoint(request: RAGQueryRequest):
    """Async RAG query with parallel retrieval."""
    from app.rag.qa_chain import rag_query_async
    from app.agent.llm import create_llm

    llm = create_llm(streaming=False)

    def llm_call(messages):
        return llm.invoke(messages).content

    result = await rag_query_async(
        query=request.query,
        llm_call_fn=llm_call,
        top_k=request.top_k or 3,
        lang=request.lang,
        filter_lang=request.filter_lang,
    )
    return result
```

- [ ] **Step 2: Verify server starts without errors**

Run: `cd backend && python -c "from app.routers.rag import router; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/rag.py
git commit -m "feat: add async RAG query endpoint with parallel retrieval"
```

---

## Phase 3: Test Infrastructure

### Task 8: Concurrent Benchmark Framework

**Files:**
- Create: `backend/tests/benchmark_concurrent.py`

- [ ] **Step 1: Implement concurrent benchmark**

Create `backend/tests/benchmark_concurrent.py`:
```python
"""Concurrent RAG Benchmark — asyncio-based parallel evaluation.

Measures throughput, latency distribution, and quality under concurrent load.
Supports configurable concurrency levels and document scale testing.

Run: cd backend && python -m tests.benchmark_concurrent
"""
import asyncio
import time
import statistics
import json
from pathlib import Path
from typing import List, Dict, Any
import sys
import os

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


async def evaluate_qa_async(qa: Dict, semaphore: asyncio.Semaphore) -> Dict:
    """Evaluate single QA pair with concurrency control."""
    async with semaphore:
        from app.rag.qa_chain import hybrid_retrieve_async

        query = qa["question"]
        expected_source = qa["source_article"]
        is_negative = expected_source == "none"

        start = time.perf_counter()
        chunks = await hybrid_retrieve_async(query, top_k=3)
        latency_ms = (time.perf_counter() - start) * 1000

        retrieved_sources = [c.get("metadata", {}).get("slug", "") for c in chunks]

        if is_negative:
            hit = len(chunks) == 0
        else:
            hit = expected_source in retrieved_sources

        return {
            "id": qa["id"],
            "query": query[:50],
            "hit": hit,
            "latency_ms": latency_ms,
            "is_negative": is_negative,
            "retrieved": retrieved_sources[:3],
        }


async def run_concurrent_evaluation(
    qa_pairs: List[Dict],
    concurrency: int = 10,
) -> Dict:
    """Run evaluation with specified concurrency level."""
    semaphore = asyncio.Semaphore(concurrency)

    start = time.perf_counter()
    tasks = [evaluate_qa_async(qa, semaphore) for qa in qa_pairs]
    results = await asyncio.gather(*tasks)
    total_time = (time.perf_counter() - start) * 1000

    # Aggregate results
    hits = sum(1 for r in results if r["hit"])
    latencies = [r["latency_ms"] for r in results]
    sorted_lats = sorted(latencies)
    n = len(sorted_lats)

    positive_results = [r for r in results if not r["is_negative"]]
    positive_hits = sum(1 for r in positive_results if r["hit"])

    return {
        "concurrency": concurrency,
        "total_queries": len(results),
        "total_time_ms": round(total_time, 1),
        "qps": round(len(results) / (total_time / 1000), 1),
        "recall": round(positive_hits / len(positive_results) * 100, 1) if positive_results else 0,
        "hit_rate": round(hits / len(results) * 100, 1),
        "latency": {
            "mean_ms": round(statistics.mean(latencies), 1),
            "p50_ms": round(sorted_lats[n // 2], 1),
            "p90_ms": round(sorted_lats[int(n * 0.9) - 1], 1),
            "p99_ms": round(sorted_lats[min(int(n * 0.99), n - 1)], 1),
            "min_ms": round(sorted_lats[0], 1),
            "max_ms": round(sorted_lats[-1], 1),
        },
    }


async def run_full_concurrent_benchmark():
    """Run complete concurrent benchmark across multiple concurrency levels."""
    from app.rag.test_data import TEST_QA_PAIRS

    print("=" * 70)
    print("  AUREON RAG — Concurrent Benchmark")
    print("=" * 70)

    qa_pairs = TEST_QA_PAIRS
    print(f"\n  QA pairs: {len(qa_pairs)}")

    # Warm up
    print("\n  Warming up index...")
    from app.rag.vector_store import _build_kw_index
    _build_kw_index(force=True)

    concurrency_levels = [1, 5, 10, 20]
    all_results = []

    for conc in concurrency_levels:
        print(f"\n> Concurrency: {conc}")
        result = await run_concurrent_evaluation(qa_pairs, concurrency=conc)
        all_results.append(result)

        print(f"  Total time:   {result['total_time_ms']:.0f}ms")
        print(f"  QPS:          {result['qps']}")
        print(f"  Recall:       {result['recall']}%")
        print(f"  Hit rate:     {result['hit_rate']}%")
        print(f"  Latency P50:  {result['latency']['p50_ms']:.1f}ms")
        print(f"  Latency P99:  {result['latency']['p99_ms']:.1f}ms")

    # Save results
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "qa_pairs": len(qa_pairs),
        "results": all_results,
    }

    out_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_concurrent.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: {out_path}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    asyncio.run(run_full_concurrent_benchmark())
```

- [ ] **Step 2: Test that the benchmark script runs**

Run: `cd backend && python -c "from tests.benchmark_concurrent import run_concurrent_evaluation; print('Import OK')"`
Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add backend/tests/benchmark_concurrent.py
git commit -m "feat: add concurrent RAG benchmark framework"
```

---

### Task 9: pytest-xdist Configuration

**Files:**
- Create/Modify: `backend/pyproject.toml` (or `pytest.ini`)
- Modify: `backend/tests/conftest.py`

- [ ] **Step 1: Add pytest-xdist configuration**

Create or modify `backend/pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "-v --tb=short"
# Parallel execution: use -n auto flag
# Example: pytest -n auto tests/

[tool.pytest-xdist]
# Worker isolation settings
```

- [ ] **Step 2: Add conftest.py fixtures for test isolation**

Add to `backend/tests/conftest.py`:
```python
"""Test configuration and fixtures for parallel execution."""
import pytest
import os


@pytest.fixture(autouse=True)
def isolate_test_environment(tmp_path):
    """Isolate test environment for parallel execution.

    Each test worker gets:
    - Separate ChromaDB/Qdrant collection
    - Separate temporary directory
    - Isolated environment variables
    """
    # Use temporary directory for vector store in tests
    os.environ.setdefault("VECTOR_DIR", str(tmp_path / "vectors"))
    yield
    # Cleanup is handled by tmp_path fixture


@pytest.fixture(scope="session")
def worker_id():
    """Get pytest-xdist worker ID for isolation."""
    return os.environ.get("PYTEST_XDIST_WORKER", "master")
```

- [ ] **Step 3: Verify tests pass with xdist**

Run: `cd backend && python -m pytest tests/test_vector_store.py -v -n 2`
Expected: Tests pass in parallel (2 workers)

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/tests/conftest.py
git commit -m "feat: add pytest-xdist configuration for parallel test execution"
```

---

## Phase 4: Large-Scale Validation

### Task 10: Document Scale Testing

**Files:**
- Modify: `backend/tests/benchmark_concurrent.py` (add scale test)

- [ ] **Step 1: Add scale testing function**

Add to `backend/tests/benchmark_concurrent.py`:
```python
async def run_scale_test():
    """Test performance across different document scales."""
    from app.rag.vector_store import get_collection_stats

    doc_count, chunk_count = get_collection_stats()

    print("\n" + "=" * 70)
    print("  Document Scale Test")
    print("=" * 70)
    print(f"\n  Current: {doc_count} docs, {chunk_count} chunks")

    # Run benchmark at current scale
    from app.rag.test_data import TEST_QA_PAIRS
    result = await run_concurrent_evaluation(TEST_QA_PAIRS, concurrency=10)

    print(f"\n  Results at {doc_count} docs:")
    print(f"    QPS:          {result['qps']}")
    print(f"    Recall:       {result['recall']}%")
    print(f"    P50 latency:  {result['latency']['p50_ms']:.1f}ms")
    print(f"    P99 latency:  {result['latency']['p99_ms']:.1f}ms")

    # Check against thresholds
    thresholds = {
        "recall": 90,
        "p99_latency_ms": 500,
        "min_qps": 5,
    }

    passed = True
    if result["recall"] < thresholds["recall"]:
        print(f"\n  [FAIL] Recall {result['recall']}% < {thresholds['recall']}%")
        passed = False
    if result["latency"]["p99_ms"] > thresholds["p99_latency_ms"]:
        print(f"\n  [FAIL] P99 {result['latency']['p99_ms']}ms > {thresholds['p99_latency_ms']}ms")
        passed = False
    if result["qps"] < thresholds["min_qps"]:
        print(f"\n  [FAIL] QPS {result['qps']} < {thresholds['min_qps']}")
        passed = False

    if passed:
        print(f"\n  [PASS] All thresholds met at {doc_count} docs")

    return passed
```

- [ ] **Step 2: Add CLI entrypoint for scale test**

Add to `backend/tests/benchmark_concurrent.py` main block:
```python
if __name__ == "__main__":
    import sys
    if "--scale" in sys.argv:
        asyncio.run(run_scale_test())
    else:
        asyncio.run(run_full_concurrent_benchmark())
```

- [ ] **Step 3: Commit**

```bash
git add backend/tests/benchmark_concurrent.py
git commit -m "feat: add document scale testing with threshold validation"
```

---

### Task 11: Final Integration Verification

**Files:**
- None (verification only)

- [ ] **Step 1: Run full benchmark suite**

Run: `cd backend && python -m tests.run_benchmark`
Expected: All metrics pass, especially Recall@3 and Negative Detection

- [ ] **Step 2: Run concurrent benchmark**

Run: `cd backend && python -m tests.benchmark_concurrent`
Expected: QPS > 5, P99 < 500ms at current document scale

- [ ] **Step 3: Run pytest with xdist**

Run: `cd backend && python -m pytest tests/ -v -n auto --timeout=300`
Expected: All tests pass in parallel

- [ ] **Step 4: Run DeepEval quality gate**

Run: `cd backend && python -m pytest tests/test_rag_quality.py -v --timeout=300`
Expected: All quality gates pass

- [ ] **Step 5: Final commit with all changes**

```bash
git add -A
git commit -m "feat: complete RAG performance optimization - Qdrant, GPU, async, concurrent tests"
```

---

## Verification Checklist

After completing all tasks, verify:

- [ ] Qdrant service running: `curl http://localhost:6333/healthz`
- [ ] GPU embedding works: `python -c "from app.rag.embed_gpu import GPUEmbedder; e = GPUEmbedder(device='cuda'); print(e.encode(['test']).shape)"`
- [ ] Async pipeline works: `python -c "import asyncio; from app.rag.qa_chain import hybrid_retrieve_async; print(asyncio.run(hybrid_retrieve_async('test', top_k=3)))"`
- [ ] Benchmark passes: `python -m tests.run_benchmark`
- [ ] Concurrent benchmark works: `python -m tests.benchmark_concurrent`
- [ ] Tests pass in parallel: `pytest tests/ -n auto`
- [ ] DeepEval quality gate: `pytest tests/test_rag_quality.py -v`
