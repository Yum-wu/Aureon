"""Input validation tests for RAG and Chat API models."""

import pytest
from pydantic import ValidationError

from app.rag.models import RAGQueryRequest
from app.api.models import ChatRequest


# ── RAGQueryRequest ──


class TestRAGQueryValidation:
    """Validate RAG query input constraints."""

    def test_rag_query_too_long(self):
        """超长输入应被拒绝（max_length=1000）"""
        long_query = "a" * 1001
        with pytest.raises(ValidationError) as exc_info:
            RAGQueryRequest(query=long_query)
        assert "1000" in str(exc_info.value)

    def test_rag_query_empty(self):
        """空输入应被拒绝"""
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="")

    def test_rag_query_whitespace_only(self):
        """纯空白输入应被拒绝"""
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="   \n\t  ")

    def test_rag_query_with_whitespace_stripped(self):
        """输入前后空白应被自动去除"""
        req = RAGQueryRequest(query="  hello world  ")
        assert req.query == "hello world"

    def test_rag_query_at_max_length(self):
        """恰好 1000 字符应通过"""
        req = RAGQueryRequest(query="a" * 1000)
        assert len(req.query) == 1000

    def test_rag_query_valid(self):
        """正常输入应通过"""
        req = RAGQueryRequest(query="What is RAG?")
        assert req.query == "What is RAG?"

    def test_top_k_out_of_range(self):
        """top_k 超出范围应被拒绝"""
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="test", top_k=0)
        with pytest.raises(ValidationError):
            RAGQueryRequest(query="test", top_k=21)

    def test_top_k_valid_range(self):
        """top_k 边界值应通过"""
        req1 = RAGQueryRequest(query="test", top_k=1)
        assert req1.top_k == 1
        req2 = RAGQueryRequest(query="test", top_k=20)
        assert req2.top_k == 20


# ── ChatRequest ──


class TestChatRequestValidation:
    """Validate Chat message input constraints."""

    def test_chat_message_too_long(self):
        """超长消息应被拒绝（max_length=2000）"""
        long_msg = "a" * 2001
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(message=long_msg)
        assert "2000" in str(exc_info.value)

    def test_chat_message_empty(self):
        """空消息应被拒绝"""
        with pytest.raises(ValidationError):
            ChatRequest(message="")

    def test_chat_message_whitespace_only(self):
        """纯空白消息应被拒绝"""
        with pytest.raises(ValidationError):
            ChatRequest(message="   \n\t  ")

    def test_chat_message_whitespace_stripped(self):
        """消息前后空白应被自动去除"""
        req = ChatRequest(message="  hello  ")
        assert req.message == "hello"

    def test_chat_message_at_max_length(self):
        """恰好 2000 字符应通过"""
        req = ChatRequest(message="a" * 2000)
        assert len(req.message) == 2000

    def test_chat_message_valid(self):
        """正常消息应通过"""
        req = ChatRequest(message="Hello!")
        assert req.message == "Hello!"

    def test_chat_session_id_optional(self):
        """session_id 可选"""
        req = ChatRequest(message="hi")
        assert req.session_id is None
