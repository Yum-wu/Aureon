"""HTTP client for Railway benchmark API calls."""

import time
from typing import List, Dict, Optional
import httpx
import structlog

logger = structlog.get_logger()


class RailwayBenchmarkClient:
    """Async HTTP client for Railway-deployed RAG services."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        pool_limit: int = 100,
        timeout: float = 30.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {"Authorization": f"Bearer {api_key}"}
        self._request_count = 0
        self._total_latency_ms = 0.0

        # Connection pool for concurrent requests
        self._client = httpx.AsyncClient(
            timeout=timeout,
            limits=httpx.Limits(
                max_connections=pool_limit,
                max_keepalive_connections=pool_limit // 2,
                keepalive_expiry=30,
            ),
        )

    async def close(self):
        """Close connection pool."""
        await self._client.aclose()

    async def retrieve(self, query: str, top_k: int = 5) -> List[Dict]:
        """Call RAG query API endpoint.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of retrieved chunks with text and metadata

        Raises:
            httpx.HTTPStatusError: If API returns error
            httpx.ConnectError: If connection fails
        """
        start = time.perf_counter()
        try:
            resp = await self._client.post(
                f"{self.base_url}/api/rag/query",
                json={"query": query, "top_k": top_k},
                headers=self.headers,
            )
            resp.raise_for_status()
            latency = (time.perf_counter() - start) * 1000

            self._request_count += 1
            self._total_latency_ms += latency

            return resp.json().get("results", [])
        except Exception as e:
            logger.warning("retrieve_failed", query=query[:50], error=str(e))
            raise

    async def health_check(self) -> bool:
        """Verify API is reachable.

        Returns:
            True if API responds with 200, False otherwise
        """
        try:
            resp = await self._client.get(
                f"{self.base_url}/api/health",
                headers=self.headers,
                timeout=10.0,
            )
            return resp.status_code == 200
        except Exception as e:
            logger.warning("health_check_failed", error=str(e))
            return False

    def get_stats(self) -> Dict:
        """Return client statistics."""
        avg_latency = (
            self._total_latency_ms / self._request_count
            if self._request_count > 0
            else 0.0
        )
        return {
            "request_count": self._request_count,
            "total_latency_ms": round(self._total_latency_ms, 1),
            "avg_latency_ms": round(avg_latency, 1),
        }
