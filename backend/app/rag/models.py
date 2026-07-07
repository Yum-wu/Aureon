"""
Pydantic models for RAG API.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Any, List, Optional


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
    model: Optional[str] = Field(default=None, description="Model name from MODEL_REGISTRY (e.g. 'qwen3.6-flash', 'zhipu')")

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
    chunk: str = ""
    score: Optional[float] = None
    chunk_id: str = ""
    chunk_text_snippet: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


PUBLIC_SOURCE_METADATA_KEYS = {
    "file_type",
    "page_count",
    "page_number",
    "sheet_name",
    "row_start",
    "row_end",
    "slide_number",
    "slide_title",
    "table_index",
    "heading_path",
    "source",
}


def public_source_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if not metadata:
        return {}
    return {
        key: value
        for key, value in metadata.items()
        if key in PUBLIC_SOURCE_METADATA_KEYS and value not in (None, "")
    }


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
    warnings: list[str] = []
    job_id: Optional[str] = None
    queued: bool = False
    message: str = ""


class RAGUploadJobStatusResponse(BaseModel):
    job_id: str
    status: str
    filename: str
    documents_indexed: int = 0
    chunks_created: int = 0
    elapsed_seconds: float = 0.0
    warnings: list[str] = []
    error: Optional[str] = None
