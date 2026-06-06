"""Chinese-aware semantic text splitter.

Splits text into chunks based on semantic similarity between sentences,
rather than fixed character counts. Uses embedding cosine similarity to
detect topic boundaries.

Inspired by LangChain's SemanticChunker but customized for Chinese text:
- Chinese-aware sentence splitting (。！？；\n)
- Markdown structure awareness (## headers as hard boundaries)
- Percentile-based breakpoint detection (robust to outliers)

Reference: https://www.anthropic.com/news/contextual-retrieval
"""

import re
import logging
from typing import List, Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


def _chinese_sentence_split(text: str) -> List[str]:
    """Split text into sentences using Chinese punctuation rules.

    Handles: 。！？；\n and Markdown headers as sentence boundaries.
    Filters out very short fragments (< 5 chars).
    """
    # Hard split on Markdown headers (preserve document structure)
    sections = re.split(r'(?=\n## )', text)

    sentences = []
    for section in sections:
        # Split on Chinese sentence-ending punctuation
        parts = re.split(r'(?<=[。！？；\n])', section)
        for part in parts:
            part = part.strip()
            if part and len(part) > 5:
                sentences.append(part)

    return sentences if sentences else [text]


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))


class SemanticTextSplitter:
    """Semantic text splitter for Chinese RAG systems.

    Uses embedding similarity between consecutive sentences to detect
    topic boundaries. Sentences within the same semantic unit are merged
    into chunks.

    Args:
        embed_fn: Embedding function (texts -> list of vectors)
        breakpoint_threshold: Percentile threshold for breakpoints (0-100).
            Lower = more chunks (more breakpoints). Default 80.
        max_chunk_size: Maximum chunk size in characters. Default 800.
        min_chunk_size: Minimum chunk size in characters. Default 100.
    """

    def __init__(
        self,
        embed_fn: Callable,
        breakpoint_threshold: float = 80.0,
        max_chunk_size: int = 800,
        min_chunk_size: int = 100,
    ):
        self.embed_fn = embed_fn
        self.breakpoint_threshold = breakpoint_threshold
        self.max_chunk_size = max_chunk_size
        self.min_chunk_size = min_chunk_size

    def split_text(self, text: str) -> List[str]:
        """Split text into semantically coherent chunks.

        Args:
            text: Input text to split

        Returns:
            List of text chunks, each a semantically coherent unit
        """
        if not text or not text.strip():
            return [text]

        # Step 1: Split into sentences
        sentences = _chinese_sentence_split(text)
        if len(sentences) <= 2:
            return [text]  # Too few sentences to split semantically

        # Step 2: Embed all sentences
        try:
            embeddings = self.embed_fn(sentences)
            embeddings = np.array(embeddings)
        except Exception as e:
            logger.warning("Semantic splitting failed (embedding error): %s, falling back to fixed split", e)
            return self._fallback_split(text)

        if len(embeddings) != len(sentences):
            logger.warning("Embedding count mismatch, falling back to fixed split")
            return self._fallback_split(text)

        # Step 3: Compute cosine similarities between consecutive sentences
        similarities = []
        for i in range(len(embeddings) - 1):
            sim = _cosine_similarity(embeddings[i], embeddings[i + 1])
            similarities.append(sim)

        if not similarities:
            return [text]

        # Step 4: Find breakpoints using percentile threshold
        # Breakpoint = where similarity drops below the threshold percentile
        similarities_arr = np.array(similarities)
        threshold = np.percentile(similarities_arr, self.breakpoint_threshold)

        # Breakpoints are positions where similarity < threshold
        breakpoints = [i for i, sim in enumerate(similarities) if sim < threshold]

        # Step 5: Merge sentences between breakpoints into chunks
        chunks = self._merge_sentences(sentences, breakpoints)

        # Step 6: Enforce max chunk size
        final_chunks = []
        for chunk in chunks:
            if len(chunk) > self.max_chunk_size:
                # Split large chunks at paragraph boundaries
                sub_chunks = self._split_large_chunk(chunk)
                final_chunks.extend(sub_chunks)
            else:
                final_chunks.append(chunk)

        # Step 7: Merge very small chunks with neighbors
        final_chunks = self._merge_small_chunks(final_chunks)

        return final_chunks if final_chunks else [text]

    def _merge_sentences(self, sentences: List[str], breakpoints: List[int]) -> List[str]:
        """Merge sentences between breakpoints into chunks."""
        if not breakpoints:
            return ["\n".join(sentences)]

        chunks = []
        start = 0
        for bp in breakpoints:
            chunk = "\n".join(sentences[start:bp + 1])
            if chunk.strip():
                chunks.append(chunk)
            start = bp + 1

        # Remaining sentences after last breakpoint
        if start < len(sentences):
            chunk = "\n".join(sentences[start:])
            if chunk.strip():
                chunks.append(chunk)

        return chunks

    def _split_large_chunk(self, chunk: str) -> List[str]:
        """Split a chunk that exceeds max_chunk_size at paragraph boundaries."""
        paragraphs = chunk.split("\n\n")
        result = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 > self.max_chunk_size and current:
                result.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            result.append(current.strip())
        return result if result else [chunk]

    def _merge_small_chunks(self, chunks: List[str]) -> List[str]:
        """Merge chunks smaller than min_chunk_size with neighbors."""
        if not chunks:
            return chunks

        result = []
        buffer = ""
        for chunk in chunks:
            if buffer and len(buffer) + len(chunk) + 2 <= self.max_chunk_size:
                buffer = buffer + "\n\n" + chunk
            elif buffer:
                result.append(buffer)
                buffer = chunk
            else:
                buffer = chunk

        if buffer:
            # If the last chunk is too small, merge with previous
            if result and len(buffer) < self.min_chunk_size:
                result[-1] = result[-1] + "\n\n" + buffer
            else:
                result.append(buffer)

        return result

    def _fallback_split(self, text: str) -> List[str]:
        """Fallback: split by paragraphs when semantic splitting fails."""
        paragraphs = text.split("\n\n")
        chunks = []
        current = ""
        for para in paragraphs:
            if len(current) + len(para) + 2 > self.max_chunk_size and current:
                chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para
        if current.strip():
            chunks.append(current.strip())
        return chunks if chunks else [text]
