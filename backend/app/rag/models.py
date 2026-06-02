"""
Pydantic models for RAG API.
"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional


class RAGQueryRequest(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="RAG 查询内容",
    )
    top_k: int = Field(default=3, ge=1, le=20)
    use_mmr: bool = True
    language: Optional[str] = Field(default=None, description="Filter results by language: 'zh' or 'en'")
    model: Optional[str] = Field(default=None, description="Model name from MODEL_REGISTRY (e.g. 'deepseek', 'zhipu')")

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """Strip whitespace and reject whitespace-only input."""
        v = v.strip()
        if not v:
            raise ValueError("查询内容不能为空")
        return v


class SourceItem(BaseModel):
    title: str
    slug: str
    chunk: str
    score: Optional[float] = None


class RAGQueryResponse(BaseModel):
    answer: str
    sources: List[SourceItem]


class RAGIndexResponse(BaseModel):
    status: str
    documents_indexed: int
    chunks_created: int
    elapsed_seconds: float


class RAGUploadResponse(BaseModel):
    status: str
    filename: str
    documents_indexed: int = 1
    chunks_created: int
    elapsed_seconds: float
