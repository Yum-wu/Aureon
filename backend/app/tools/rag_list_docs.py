"""Read-only document listing tool for RAG collections."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain.tools import tool
from pydantic import BaseModel, Field
from qdrant_client import models as qmodels

from app.rag.qdrant_ops import _get_qdrant, _get_qdrant_collection_name


class RagListDocsInput(BaseModel):
    tenant_id: str | None = Field(default=None, description="Tenant id for filtering documents")
    limit: int = Field(default=200, ge=1, le=1000, description="Maximum unique documents to return")


def _tenant_filter(tenant_id: str | None) -> qmodels.Filter | None:
    if not tenant_id or tenant_id == "default":
        return None
    return qmodels.Filter(
        must=[
            qmodels.FieldCondition(
                key="metadata.tenant_id",
                match=qmodels.MatchValue(value=tenant_id),
            )
        ]
    )


def _doc_from_metadata(metadata: dict[str, Any]) -> dict[str, Any] | None:
    source = str(metadata.get("source") or "").strip()
    slug = str(metadata.get("slug") or "").strip()
    if not source and not slug:
        return None

    source_path = Path(source)
    fallback_name = source_path.stem if source else slug
    title = str(metadata.get("title") or fallback_name or slug).strip()
    file_type = str(metadata.get("file_type") or source_path.suffix.lstrip(".")).lower()

    return {
        "slug": slug or fallback_name,
        "title": title,
        "source": source,
        "file_type": file_type,
        "uploaded": bool(metadata.get("uploaded", False)),
    }


def list_rag_docs(tenant_id: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    client = _get_qdrant()
    collection_name = _get_qdrant_collection_name()
    docs: list[dict[str, Any]] = []
    seen: set[str] = set()
    offset = None

    while len(docs) < limit:
        points, offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=_tenant_filter(tenant_id),
            limit=128,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            metadata = payload.get("metadata", {}) or {}
            doc = _doc_from_metadata(metadata)
            if not doc:
                continue
            key = f"{doc['slug']}::{doc['source']}"
            if key in seen:
                continue
            seen.add(key)
            docs.append(doc)
            if len(docs) >= limit:
                break
        if offset is None:
            break

    return docs


@tool(args_schema=RagListDocsInput)
def rag_list_docs(tenant_id: str | None = None, limit: int = 200) -> str:
    """列出 RAG 知识库中的文档清单。只读，不执行问答，不改变普通查询路径。"""
    try:
        return json.dumps(list_rag_docs(tenant_id=tenant_id, limit=limit), ensure_ascii=False)
    except Exception as exc:
        return f"文档清单读取失败：{exc}"
