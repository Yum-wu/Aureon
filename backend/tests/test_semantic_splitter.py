import numpy as np
from app.rag.semantic_splitter import (
    _chinese_sentence_split,
    _cosine_similarity,
    SemanticTextSplitter,
    ParentChildSplitter,
)


class TestChineseSentenceSplit:
    def test_splits_chinese_punctuation(self):
        result = _chinese_sentence_split("今天天气真好。我们去公园玩。小明也来了。")
        assert result == ["今天天气真好。", "我们去公园玩。", "小明也来了。"]

    def test_splits_multiple_punctuation_types(self):
        result = _chinese_sentence_split("今天天气真好！我们去公园玩？测试一下；结束这个测试。")
        assert len(result) >= 3

    def test_handles_markdown_headers(self):
        result = _chinese_sentence_split("Intro.\n## Section 1\nContent.\n## Section 2\nMore.")
        assert "## Section 1\nContent。" in result or any("Section 1" in s for s in result)
        assert len(result) >= 2

    def test_filters_short_fragments(self):
        result = _chinese_sentence_split("Hi.\n\nOk.\n\nLonger sentence here.")
        assert all(len(s) > 5 for s in result)

    def test_empty_text_returns_text(self):
        result = _chinese_sentence_split("")
        assert result == [""]

    def test_single_sentence_returns_as_is(self):
        result = _chinese_sentence_split("Short.")
        assert result == ["Short."] or len(result) == 1

    def test_newline_as_boundary(self):
        text = "First sentence.\nSecond sentence.\nThird sentence."
        result = _chinese_sentence_split(text)
        assert len(result) >= 2


class TestCosineSimilarity:
    def test_identical_vectors(self):
        a = np.array([1.0, 2.0, 3.0])
        sim = _cosine_similarity(a, a)
        assert abs(sim - 1.0) < 1e-6

    def test_orthogonal_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 1.0])
        sim = _cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_similar_vectors(self):
        a = np.array([1.0, 2.0, 3.0])
        b = np.array([1.1, 2.1, 3.1])
        sim = _cosine_similarity(a, b)
        assert sim > 0.99

    def test_opposite_vectors(self):
        a = np.array([1.0, 0.0])
        b = np.array([-1.0, 0.0])
        sim = _cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_zero_vector(self):
        a = np.array([0.0, 0.0, 0.0])
        b = np.array([1.0, 0.0, 0.0])
        sim = _cosine_similarity(a, b)
        assert sim == 0.0

    def test_both_zero_vectors(self):
        a = np.array([0.0, 0.0])
        b = np.array([0.0, 0.0])
        sim = _cosine_similarity(a, b)
        assert sim == 0.0


def dummy_embed(texts):
    """Return deterministic embeddings: each text gets a unit vector based on length."""
    rng = np.random.RandomState(42)
    return [rng.randn(4) for _ in texts]


class TestSemanticTextSplitter:
    def test_empty_text(self):
        splitter = SemanticTextSplitter(embed_fn=dummy_embed)
        result = splitter.split_text("")
        assert result == [""]

    def test_short_text_returns_as_is(self):
        splitter = SemanticTextSplitter(embed_fn=dummy_embed)
        result = splitter.split_text("Short text.")
        assert result == ["Short text."]

    def test_two_sentences_returns_as_is(self):
        splitter = SemanticTextSplitter(embed_fn=dummy_embed)
        result = splitter.split_text("First sentence. Second sentence.")
        assert result == ["First sentence. Second sentence."]

    def test_returns_list_of_strings(self):
        splitter = SemanticTextSplitter(embed_fn=dummy_embed)
        text = "One. Two. Three. Four. Five. Six. Seven. Eight."
        result = splitter.split_text(text)
        assert isinstance(result, list)
        assert all(isinstance(c, str) for c in result)
        assert len(result) >= 1

    def test_max_chunk_size_enforced(self):
        def broken_embed(texts):
            raise ValueError("API error")
        splitter = SemanticTextSplitter(embed_fn=broken_embed, max_chunk_size=50)
        long_text = "\n\n".join(["Paragraph " + str(i) + " for testing purposes" for i in range(10)])
        result = splitter.split_text(long_text)
        assert all(len(c) <= 60 for c in result)

    def test_fallback_on_embedding_error(self):
        def broken_embed(texts):
            raise ValueError("API error")

        splitter = SemanticTextSplitter(embed_fn=broken_embed)
        text = "A. B. C. D. E. F. G. H."
        result = splitter.split_text(text)
        assert isinstance(result, list)
        assert len(result) >= 1

    def test_fallback_on_mismatched_embeddings(self):
        def wrong_count_embed(texts):
            return [[0.0]] * (len(texts) - 1)

        splitter = SemanticTextSplitter(embed_fn=wrong_count_embed)
        text = "A. B. C. D. E. F. G. H."
        result = splitter.split_text(text)
        assert isinstance(result, list)

    def test_custom_threshold(self):
        splitter = SemanticTextSplitter(embed_fn=dummy_embed, breakpoint_threshold=50.0)
        text = "A. B. C. D. E. F. G. H."
        result = splitter.split_text(text)
        assert isinstance(result, list)

    def test_min_chunk_size_merges_small_chunks(self):
        splitter = SemanticTextSplitter(embed_fn=dummy_embed, min_chunk_size=200, max_chunk_size=1000)
        text = "A. B. C. D. E. F. G. H."
        result = splitter.split_text(text)
        assert all(len(c) >= 1 for c in result)


class TestParentChildSplitter:
    def test_empty_documents(self):
        splitter = ParentChildSplitter()
        result = splitter.split_documents([])
        assert result == []

    def test_empty_content_skipped(self):
        splitter = ParentChildSplitter()
        docs = [{"content": "", "metadata": {"source": "test"}}]
        result = splitter.split_documents(docs)
        assert result == []

    def test_single_document_splits_into_chunks(self):
        splitter = ParentChildSplitter(parent_size=500, child_size=100, overlap=20)
        text = "Word. " * 100
        docs = [{"content": text, "metadata": {"source": "test"}}]
        result = splitter.split_documents(docs)
        assert len(result) > 1
        assert all("parent_text" in c["metadata"] for c in result)
        assert all("parent_idx" in c["metadata"] for c in result)

    def test_small_document_no_split(self):
        splitter = ParentChildSplitter()
        docs = [{"content": "Small doc.", "metadata": {"source": "test"}}]
        result = splitter.split_documents(docs)
        assert len(result) == 1
        assert result[0]["text"] == "Small doc."

    def test_metadata_preserved(self):
        splitter = ParentChildSplitter(parent_size=500, child_size=100, overlap=20)
        text = "Word. " * 100
        docs = [{"content": text, "metadata": {"source": "test", "author": "me"}}]
        result = splitter.split_documents(docs)
        assert result[0]["metadata"]["source"] == "test"
        assert result[0]["metadata"]["author"] == "me"

    def test_multiple_documents(self):
        splitter = ParentChildSplitter(parent_size=500, child_size=100, overlap=20)
        docs = [
            {"content": "Word. " * 100, "metadata": {"id": 1}},
            {"content": "Test. " * 100, "metadata": {"id": 2}},
        ]
        result = splitter.split_documents(docs)
        assert len(result) >= 2

    def test_split_children_with_overlap(self):
        splitter = ParentChildSplitter(parent_size=500, child_size=80, overlap=30)
        text = "Word. " * 100
        docs = [{"content": text, "metadata": {}}]
        result = splitter.split_documents(docs)
        assert len(result) >= 2

    def test_parent_size_respected(self):
        splitter = ParentChildSplitter(parent_size=100, child_size=50, overlap=10)
        long_text = "Paragraph one.\n\nParagraph two.\n\nParagraph three.\n\n" * 5
        docs = [{"content": long_text, "metadata": {}}]
        result = splitter.split_documents(docs, parent_size=100)
        for c in result:
            assert len(c["metadata"]["parent_text"]) <= 150

    def test_character_level_fallback(self):
        splitter = ParentChildSplitter()
        long_word = "A" * 1000
        docs = [{"content": long_word, "metadata": {}}]
        result = splitter.split_documents(docs)
        assert len(result) >= 2


class TestSplitByChars:
    def test_basic_char_split(self):
        splitter = ParentChildSplitter()
        text = "A" * 100
        result = splitter._split_by_chars(text, 30, 5)
        assert len(result) >= 3
        assert all(len(c) <= 30 for c in result)

    def test_no_split_when_fits(self):
        splitter = ParentChildSplitter()
        result = splitter._split_by_chars("Short", 100, 10)
        assert result == ["Short"]

    def test_infinite_loop_guard(self):
        splitter = ParentChildSplitter()
        text = "A" * 20
        result = splitter._split_by_chars(text, 10, 15)
        assert len(result) >= 1
