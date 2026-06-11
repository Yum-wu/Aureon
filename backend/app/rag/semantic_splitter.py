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
import structlog
from typing import List, Callable, Dict, Any

import numpy as np

logger = structlog.get_logger()


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

class ParentChildSplitter:
    """Parent-Child hierarchical chunking strategy.

    Parent chunks: large context blocks (512-1024 tokens)
    Child chunks: small searchable units (128-256 tokens)

    During retrieval:
    - Search uses child chunks for precise matching
    - Return parent chunks for rich context

    Args:
        parent_size: Target size for parent chunks in characters (default 800)
        child_size: Target size for child chunks in characters (default 200)
        overlap: Overlap between adjacent child chunks in characters (default 50)
    """

    def __init__(
        self,
        parent_size: int = 800,
        child_size: int = 200,
        overlap: int = 50,
    ):
        self.parent_size = parent_size
        self.child_size = child_size
        self.overlap = overlap

    def split_documents(
        self,
        documents: List[Dict[str, Any]],
        parent_size: int = 800,
        child_size: int = 200,
        overlap: int = 50,
    ) -> List[Dict[str, Any]]:
        """Split documents into parent-child hierarchical chunks.

        Args:
            documents: List of document dicts with 'content' and 'metadata' fields.
            parent_size: Target size for parent chunks in characters.
            child_size: Target size for child chunks in characters.
            overlap: Overlap between adjacent child chunks in characters.

        Returns:
            List of chunk dicts, each containing:
            - text: The child chunk text
            - metadata: Dict with parent_text, parent_idx, and original metadata
        """
        parent_size = parent_size or self.parent_size
        child_size = child_size or self.child_size
        overlap = overlap or self.overlap

        all_chunks: List[Dict[str, Any]] = []

        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})

            if not content or not content.strip():
                continue

            # Step 1: Split document into parent chunks
            parent_chunks = self._split_parents(content, parent_size)

            # Step 2: For each parent chunk, split into child chunks
            for parent_idx, parent_text in enumerate(parent_chunks):
                child_texts = self._split_children(parent_text, child_size, overlap)
                for child_text in child_texts:
                    all_chunks.append({
                        "text": child_text,
                        "metadata": {
                            **metadata,
                            "parent_text": parent_text,
                            "parent_idx": parent_idx,
                        },
                    })

        logger.info(
            "ParentChildSplitter: %d docs -> %d parent-child chunks",
            len(documents), len(all_chunks),
        )
        return all_chunks

    def _split_parents(self, text: str, parent_size: int) -> List[str]:
        """Split text into parent chunks at paragraph/heading boundaries.

        Tries to respect document structure by splitting on:
        1. Markdown headers (## )
        2. Double newlines (paragraph breaks)
        3. Single newlines (line breaks)
        """
        # First, split on markdown headers to preserve structure
        sections = re.split(r'(?=\n## )', text)

        parent_chunks: List[str] = []
        current = ""

        for section in sections:
            section = section.strip()
            if not section:
                continue

            if len(current) + len(section) + 2 <= parent_size:
                current = current + "\n\n" + section if current else section
            else:
                if current:
                    parent_chunks.append(current.strip())
                # If single section exceeds parent_size, split by paragraphs
                if len(section) > parent_size:
                    sub_chunks = self._split_large_section(section, parent_size)
                    parent_chunks.extend(sub_chunks)
                else:
                    current = section
                    continue
                current = ""

        if current.strip():
            parent_chunks.append(current.strip())

        return parent_chunks if parent_chunks else [text]

    def _split_large_section(self, section: str, parent_size: int) -> List[str]:
        """Split a section that exceeds parent_size at paragraph boundaries."""
        paragraphs = section.split("\n\n")
        result: List[str] = []
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 > parent_size and current:
                result.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para

            # If single paragraph exceeds size, split by lines
            if len(current) > parent_size:
                lines = current.split("\n")
                buffer = ""
                for line in lines:
                    if len(buffer) + len(line) + 1 > parent_size and buffer:
                        result.append(buffer.strip())
                        buffer = line
                    else:
                        buffer = buffer + "\n" + line if buffer else line
                current = buffer

        if current.strip():
            result.append(current.strip())

        return result if result else [section]

    def _split_children(self, parent_text: str, child_size: int, overlap: int) -> List[str]:
        """Split a parent chunk into child chunks with overlap.

        Uses sentence boundaries where possible to keep semantic units intact.
        Falls back to character-level splitting when sentences are too long.
        """
        if len(parent_text) <= child_size:
            return [parent_text]

        # Split on sentence boundaries first
        sentences = _chinese_sentence_split(parent_text)
        if len(sentences) <= 1:
            # No sentence splits possible, use character-level
            return self._split_by_chars(parent_text, child_size, overlap)

        # Merge sentences into child-sized chunks
        children: List[str] = []
        current = ""

        for sentence in sentences:
            if len(current) + len(sentence) + 1 <= child_size:
                current = current + "\n" + sentence if current else sentence
            else:
                if current:
                    children.append(current.strip())
                # If single sentence exceeds child_size, force split
                if len(sentence) > child_size:
                    sub_children = self._split_by_chars(sentence, child_size, overlap)
                    children.extend(sub_children)
                    current = ""
                else:
                    current = sentence

        if current.strip():
            children.append(current.strip())

        # Apply overlap: prepend tail of previous child to current child
        if overlap > 0 and len(children) > 1:
            children = self._apply_overlap(children, overlap)

        return children if children else [parent_text]

    def _split_by_chars(self, text: str, chunk_size: int, overlap: int) -> List[str]:
        """Character-level splitting with overlap."""
        chunks: List[str] = []
        start = 0
        while start < len(text):
            end = min(start + chunk_size, len(text))
            chunks.append(text[start:end].strip())
            if end >= len(text):
                break
            start = end - overlap
            if start <= (len(chunks[-1]) if chunks else 0):
                start = end  # prevent infinite loop
        return chunks

    def _apply_overlap(self, children: List[str], overlap: int) -> List[str]:
        """Prepend tail of previous child to each child for context continuity."""
        result: List[str] = [children[0]]
        for i in range(1, len(children)):
            prev = children[i - 1]
            if len(prev) > overlap:
                overlap_text = prev[-overlap:]
                # Try to break at a sentence boundary
                for sep in ["。", "！", "？", ".", "!", "?"]:
                    idx = overlap_text.find(sep)
                    if idx >= 0:
                        overlap_text = overlap_text[idx + 1:]
                        break
                overlap_text = overlap_text.strip()
                if overlap_text:
                    result.append(overlap_text + "\n" + children[i])
                else:
                    result.append(children[i])
            else:
                result.append(children[i])
        return result
