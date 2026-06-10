"""HTTP client for Railway benchmark API calls."""

import asyncio
import time
from typing import List, Dict, Optional
import httpx
import structlog

logger = structlog.get_logger()

# Retry configuration for rate limiting
MAX_RETRIES = 3
BASE_BACKOFF_SECONDS = 2.0


class RailwayBenchmarkClient:
    """Async HTTP client for Railway-deployed RAG services."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        pool_limit: int = 100,
        timeout: float = 120.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.headers = {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"
        self._request_count = 0
        self._total_latency_ms = 0.0
        self._retry_count = 0

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
        """Call RAG query API endpoint with retry on 429.

        Args:
            query: Search query
            top_k: Number of results to return

        Returns:
            List of retrieved chunks with text and metadata

        Raises:
            httpx.HTTPStatusError: If API returns non-retriable error
            httpx.ConnectError: If connection fails
        """
        start = time.perf_counter()

        for attempt in range(MAX_RETRIES + 1):
            try:
                resp = await self._client.post(
                    f"{self.base_url}/api/rag/query",
                    json={"query": query, "top_k": top_k},
                    headers=self.headers,
                )

                # Handle rate limiting (429) and server overload (502/503) with retry
                if resp.status_code in (429, 502, 503):
                    if attempt < MAX_RETRIES:
                        retry_after = float(resp.headers.get("Retry-After", BASE_BACKOFF_SECONDS))
                        backoff = retry_after * (2 ** attempt)
                        self._retry_count += 1
                        logger.info(
                            "retry_on_error",
                            status=resp.status_code,
                            attempt=attempt + 1,
                            backoff_seconds=round(backoff, 1),
                        )
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        resp.raise_for_status()

                resp.raise_for_status()
                latency = (time.perf_counter() - start) * 1000

                self._request_count += 1
                self._total_latency_ms += latency

                data = resp.json()
                # API returns {"answer": ..., "sources": [...]}
                # Extract sources list for benchmark analysis
                return data.get("sources", data.get("results", []))

            except httpx.HTTPStatusError as e:
                logger.warning(
                    "retrieve_http_error",
                    query=query[:50],
                    status=e.response.status_code,
                    error=str(e),
                )
                raise
            except httpx.TimeoutException as e:
                logger.warning(
                    "retrieve_timeout",
                    query=query[:50],
                    error=f"Timeout: {e}",
                )
                raise
            except httpx.ConnectError as e:
                logger.warning(
                    "retrieve_connect_error",
                    query=query[:50],
                    error=f"ConnectError: {e}",
                )
                raise
            except Exception as e:
                logger.warning(
                    "retrieve_failed",
                    query=query[:50],
                    error=f"{type(e).__name__}: {e}",
                )
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
            "retry_count": self._retry_count,
        }
