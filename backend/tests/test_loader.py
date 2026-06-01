"""Tests for app.rag.loader — parse_frontmatter, load_single_document, load_markdown_files."""

import os
import pytest
import tempfile
from pathlib import Path

from app.rag.loader import parse_frontmatter, load_single_document, load_markdown_files


# ── parse_frontmatter ──


class TestParseFrontmatter:
    def test_with_frontmatter(self):
        content = "---\ntitle: Test Post\nslug: test-post\ntags: [AI, RAG]\n---\n\nBody content here."
        metadata, body = parse_frontmatter(content)
        assert metadata["title"] == "Test Post"
        assert metadata["slug"] == "test-post"
        assert metadata["tags"] == ["AI", "RAG"]
        assert "Body content here" in body

    def test_without_frontmatter(self):
        content = "Just plain text without frontmatter."
        metadata, body = parse_frontmatter(content)
        assert metadata == {}
        assert body == content

    def test_empty_content(self):
        metadata, body = parse_frontmatter("")
        assert metadata == {}
        assert body == ""

    def test_frontmatter_no_tags(self):
        content = "---\ntitle: Simple\n---\nBody."
        metadata, body = parse_frontmatter(content)
        assert metadata["title"] == "Simple"
        assert "Body" in body

    def test_quoted_values(self):
        content = '---\ntitle: "Quoted Title"\n---\nBody.'
        metadata, body = parse_frontmatter(content)
        assert metadata["title"] == "Quoted Title"


# ── load_single_document ──


class TestLoadSingleDocument:
    def test_load_md_file(self, tmp_path):
        md_file = tmp_path / "test.md"
        md_file.write_text("---\ntitle: My Doc\ncategory: tech\n---\n\nHello world.", encoding="utf-8")

        result = load_single_document(str(md_file))
        assert result["metadata"]["title"] == "My Doc"
        assert result["metadata"]["category"] == "tech"
        assert result["metadata"]["source"] == "test.md"
        assert result["metadata"]["uploaded"] is True
        assert "Hello world" in result["content"]

    def test_load_txt_file(self, tmp_path):
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("Plain text content.", encoding="utf-8")

        result = load_single_document(str(txt_file))
        assert result["metadata"]["title"] == "notes"
        assert result["metadata"]["category"] == "upload"
        assert result["content"] == "Plain text content."

    def test_unsupported_extension_raises(self, tmp_path):
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b,c\n1,2,3", encoding="utf-8")

        with pytest.raises(ValueError, match="Unsupported file type"):
            load_single_document(str(csv_file))

    def test_md_without_frontmatter_uses_stem_as_title(self, tmp_path):
        md_file = tmp_path / "no-fm.md"
        md_file.write_text("Just content.", encoding="utf-8")

        result = load_single_document(str(md_file))
        assert result["metadata"]["title"] == "no-fm"


# ── load_markdown_files ──


class TestLoadMarkdownFiles:
    def test_loads_all_md_files(self, tmp_path):
        (tmp_path / "a.md").write_text("---\ntitle: A\n---\nContent A", encoding="utf-8")
        (tmp_path / "b.md").write_text("---\ntitle: B\n---\nContent B", encoding="utf-8")
        (tmp_path / "c.txt").write_text("Not markdown", encoding="utf-8")

        docs = load_markdown_files(str(tmp_path))
        assert len(docs) == 2
        titles = {d["metadata"]["title"] for d in docs}
        assert titles == {"A", "B"}

    def test_nonexistent_dir_returns_empty(self):
        docs = load_markdown_files("/nonexistent/path/that/does/not/exist")
        assert docs == []

    def test_empty_dir_returns_empty(self, tmp_path):
        docs = load_markdown_files(str(tmp_path))
        assert docs == []

    def test_nested_dirs(self, tmp_path):
        sub = tmp_path / "sub"
        sub.mkdir()
        (sub / "nested.md").write_text("Content", encoding="utf-8")

        docs = load_markdown_files(str(tmp_path))
        assert len(docs) == 1
