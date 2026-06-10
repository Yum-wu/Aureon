"""Tests for Railway HTTP client."""

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_response():
    """Create mock httpx response."""
    def _create(status_code=200, json_data=None):
        response = AsyncMock(spec=httpx.Response)
        response.status_code = status_code
        response.json = MagicMock(return_value=json_data or {"results": []})
        response.raise_for_status = MagicMock()
        return response
    return _create


@pytest.mark.asyncio
async def test_retrieve_calls_api():
    """Test that retrieve() calls the correct API endpoint."""
    from app.benchmark.http_client import RailwayBenchmarkClient

    client = RailwayBenchmarkClient(
        base_url="https://test.up.railway.app",
        api_key="test-key",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value={"results": [{"text": "test", "score": 0.9}]})
    mock_response.raise_for_status = MagicMock()

    with patch.object(client._client, "post", new_callable=AsyncMock, return_value=mock_response):
        results = await client.retrieve("test query", top_k=5)
        assert len(results) == 1
        assert results[0]["text"] == "test"

    await client.close()


@pytest.mark.asyncio
async def test_health_check_success():
    """Test health check returns True when API is reachable."""
    from app.benchmark.http_client import RailwayBenchmarkClient

    client = RailwayBenchmarkClient(
        base_url="https://test.up.railway.app",
        api_key="test-key",
    )

    mock_response = AsyncMock()
    mock_response.status_code = 200

    with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_response):
        is_healthy = await client.health_check()
        assert is_healthy is True

    await client.close()


@pytest.mark.asyncio
async def test_health_check_failure():
    """Test health check returns False when API is unreachable."""
    from app.benchmark.http_client import RailwayBenchmarkClient

    client = RailwayBenchmarkClient(
        base_url="https://test.up.railway.app",
        api_key="test-key",
    )

    with patch.object(client._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("Connection failed")):
        is_healthy = await client.health_check()
        assert is_healthy is False

    await client.close()
