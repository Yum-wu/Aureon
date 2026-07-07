"""Sparse 向量生成（通过 SiliconFlow BGE-M3 API）。"""

import structlog
from typing import Dict, List
from app.config import settings

logger = structlog.get_logger()


def embed_sparse(texts: List[str]) -> List[Dict[int, float]]:
    """通过 SiliconFlow BGE-M3 API 生成 sparse 向量。

    返回 sparse 向量列表，每个为 {token_id: weight} 字典。
    """
    if not settings.sparse_enabled:
        return [{} for _ in texts]

    if settings.sparse_provider == "siliconflow":
        return _embed_sparse_siliconflow(texts)
    else:
        logger.warning("Sparse provider %s not supported, returning empty", settings.sparse_provider)
        return [{} for _ in texts]


def _embed_sparse_siliconflow(texts: List[str]) -> List[Dict[int, float]]:
    """SiliconFlow BGE-M3 sparse embedding。"""
    import httpx

    url = f"{settings.siliconflow_base_url}/embeddings"
    headers = {
        "Authorization": f"Bearer {settings.siliconflow_api_key}",
        "Content-Type": "application/json",
    }

    sparse_vectors = []
    batch_size = 1
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            "model": settings.sparse_model,
            "input": batch,
            "encoding_format": "float",
        }
        try:
            resp = httpx.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("data", []):
                # SiliconFlow BGE-M3 返回的 sparse 向量格式
                sparse = item.get("sparse", {})
                if sparse:
                    sparse_vectors.append(sparse)
                else:
                    sparse_vectors.append({})
        except Exception as e:
            logger.warning("SiliconFlow sparse embedding failed: %s", e)
            sparse_vectors.extend([{} for _ in batch])

    return sparse_vectors
