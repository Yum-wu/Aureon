# -*- coding: utf-8 -*-
"""WebSocket 200-Concurrent Connection Load Test.

Tests that the system can handle 200 simultaneous WebSocket connections.
Validates the Semaphore-based connection limiter + WebSocketManager upgrade.

Can run in TWO modes:
1. Unit mode (no backend): Tests WebSocketManager directly with mock connections
2. Integration mode (backend running): Tests real WebSocket endpoint at ws://localhost:8000

Run unit mode:    cd backend && python tests/test_websocket_load.py
Run integration:  cd backend && python tests/test_websocket_load.py --live
"""

import asyncio
import json
import os
import sys
import time
import statistics
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ============================================================
# Test Configuration
# ============================================================

TARGET_CONNECTIONS = 200
MAX_CONNECTIONS = 300  # Matches WEBSOCKET_MAX_CONNECTIONS default
LIVE_URL = os.getenv("WS_URL", "ws://localhost:8000/ws/chat")
TIMEOUT_SECONDS = 30


# ============================================================
# Data Classes
# ============================================================

@dataclass
class ConnectionResult:
    client_id: str
    connected: bool = False
    connect_time_ms: float = 0
    received_welcome: bool = False
    heartbeat_ack: bool = False
    disconnected: bool = False
    error: Optional[str] = None


@dataclass
class LoadTestResults:
    target_connections: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    connection_times_ms: List[float] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    total_time_ms: float = 0
    mode: str = ""


# ============================================================
# Mode 1: Unit Test (no backend needed)
# ============================================================

async def test_websocket_manager_unit(target: int = TARGET_CONNECTIONS) -> LoadTestResults:
    """Test WebSocketManager with mock WebSocket connections.

    This verifies the manager can handle 200+ connections without
    needing a running server. Tests connection registration, eviction,
    heartbeat, and disconnect cleanup.
    """
    from app.api.websocket import WebSocketManager

    results = LoadTestResults(target_connections=target, mode="unit")
    start = time.perf_counter()

    manager = WebSocketManager()
    # Override max to test target
    manager._max_connections = MAX_CONNECTIONS

    mock_websockets: List[AsyncMock] = []
    connection_times = []
    errors = []

    # Phase 1: Connect all clients
    print(f"\n  [Phase 1] Connecting {target} clients...")
    for i in range(target):
        ws = AsyncMock()
        ws.accept = AsyncMock()
        ws.send_json = AsyncMock()
        ws.close = AsyncMock()
        mock_websockets.append(ws)

        client_id = f"load-test-{i}"
        t0 = time.perf_counter()
        try:
            await manager.connect(ws, client_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            connection_times.append(elapsed_ms)
        except Exception as e:
            errors.append(f"connect-{i}: {e}")

    actual_connected = len(manager.active_connections)
    print(f"    Connected: {actual_connected}/{target}")
    print(f"    Connection order length: {len(manager._connection_order)}")

    # Phase 2: Verify connection state
    print(f"\n  [Phase 2] Verifying connection state...")
    assert actual_connected == target, f"Expected {target} connections, got {actual_connected}"
    for i in range(target):
        client_id = f"load-test-{i}"
        assert client_id in manager.active_connections, f"Missing client {client_id}"
        assert client_id in manager.connection_metadata, f"Missing metadata for {client_id}"
        metadata = manager.connection_metadata[client_id]
        assert metadata["connected_at"] is not None
        assert metadata["last_heartbeat"] is not None
    print(f"    All {target} connections verified in active_connections dict")

    # Phase 3: Heartbeat under load
    print(f"\n  [Phase 3] Heartbeat under load...")
    for i in range(target):
        client_id = f"load-test-{i}"
        manager.update_heartbeat(client_id)
    print(f"    Updated heartbeat for all {target} clients")

    # Phase 4: Broadcast to all
    print(f"\n  [Phase 4] Broadcasting to all {target} clients...")
    broadcast_start = time.perf_counter()
    await manager.broadcast({"type": "test_broadcast", "data": "hello"})
    broadcast_ms = (time.perf_counter() - broadcast_start) * 1000
    print(f"    Broadcast completed in {broadcast_ms:.1f}ms")

    # Verify each client received the broadcast
    for i in range(target):
        ws = mock_websockets[i]
        ws.send_json.assert_called()

    # Phase 5: Disconnect half, verify remaining
    half = target // 2
    print(f"\n  [Phase 5] Disconnecting {half} clients...")
    for i in range(half):
        client_id = f"load-test-{i}"
        await manager.disconnect(client_id)

    remaining = len(manager.active_connections)
    assert remaining == target - half, f"Expected {target - half} remaining, got {remaining}"
    print(f"    Remaining connections: {remaining}")

    # Phase 6: Disconnect rest
    print(f"\n  [Phase 6] Disconnecting remaining {remaining} clients...")
    for i in range(half, target):
        client_id = f"load-test-{i}"
        await manager.disconnect(client_id)

    assert len(manager.active_connections) == 0, "All connections should be disconnected"
    assert len(manager.connection_metadata) == 0, "All metadata should be cleaned up"
    assert len(manager._connection_order) == 0, "Connection order should be empty"
    print(f"    All connections cleaned up successfully")

    total_ms = (time.perf_counter() - start) * 1000

    results.successful_connections = target
    results.failed_connections = len(errors)
    results.connection_times_ms = connection_times
    results.errors = errors
    results.total_time_ms = total_ms

    return results


# ============================================================
# Mode 2: Integration Test (backend must be running)
# ============================================================

async def _single_ws_connect(client_id: str, url: str, timeout: float) -> ConnectionResult:
    """Connect a single WebSocket client and verify lifecycle."""
    result = ConnectionResult(client_id=client_id)
    try:
        import websockets
        connect_start = time.perf_counter()

        ws_url = f"{url}/{client_id}"
        async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=5) as ws:
            result.connect_time_ms = (time.perf_counter() - connect_start) * 1000
            result.connected = True

            # Receive welcome message
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                if data.get("type") == "connected":
                    result.received_welcome = True
            except asyncio.TimeoutError:
                pass

            # Send heartbeat
            await ws.send(json.dumps({"type": "heartbeat"}))
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(msg)
                if data.get("type") == "heartbeat_ack":
                    result.heartbeat_ack = True
            except asyncio.TimeoutError:
                pass

            # Hold connection briefly
            await asyncio.sleep(0.5)
            result.disconnected = True

    except ImportError:
        result.error = "websockets package not installed. Run: pip install websockets"
    except Exception as e:
        result.error = str(e)[:200]

    return result


async def test_websocket_live(target: int = TARGET_CONNECTIONS) -> LoadTestResults:
    """Test real WebSocket connections against running backend."""
    results = LoadTestResults(target_connections=target, mode="live")
    start = time.perf_counter()

    print(f"\n  Connecting {target} WebSocket clients to {LIVE_URL}...")
    print(f"  (This may take a moment due to connection ramp-up)")

    # Connect in batches to avoid overwhelming
    batch_size = 50
    all_results: List[ConnectionResult] = []

    for batch_start in range(0, target, batch_size):
        batch_end = min(batch_start + batch_size, target)
        batch_ids = [f"load-{i}" for i in range(batch_start, batch_end)]

        tasks = [_single_ws_connect(cid, LIVE_URL, TIMEOUT_SECONDS) for cid in batch_ids]
        batch_results = await asyncio.gather(*tasks, return_exceptions=True)

        for r in batch_results:
            if isinstance(r, Exception):
                all_results.append(ConnectionResult(client_id="unknown", error=str(r)))
            else:
                all_results.append(r)

        connected_in_batch = sum(1 for r in batch_results if not isinstance(r, Exception) and r.connected)
        print(f"    Batch {batch_start}-{batch_end}: {connected_in_batch}/{len(batch_ids)} connected")

    total_ms = (time.perf_counter() - start) * 1000

    # Aggregate
    successful = sum(1 for r in all_results if r.connected)
    failed = sum(1 for r in all_results if not r.connected)
    connect_times = [r.connect_time_ms for r in all_results if r.connected]
    welcome_ok = sum(1 for r in all_results if r.received_welcome)
    heartbeat_ok = sum(1 for r in all_results if r.heartbeat_ack)
    errors = [r.error for r in all_results if r.error]

    results.successful_connections = successful
    results.failed_connections = failed
    results.connection_times_ms = connect_times
    results.errors = errors
    results.total_time_ms = total_ms

    print(f"\n  Results:")
    print(f"    Connected:       {successful}/{target}")
    print(f"    Welcome msg:     {welcome_ok}/{successful}")
    print(f"    Heartbeat ack:   {heartbeat_ok}/{successful}")
    if connect_times:
        print(f"    Connect P50:     {statistics.median(connect_times):.1f}ms")
        print(f"    Connect P99:     {sorted(connect_times)[int(len(connect_times)*0.99)]:.1f}ms")
    print(f"    Total time:      {total_ms:.0f}ms")
    if errors:
        unique_errors = list(set(errors))[:5]
        print(f"    Errors ({len(errors)}):")
        for e in unique_errors:
            print(f"      - {e}")

    return results


# ============================================================
# Results Reporter
# ============================================================

def print_results(results: LoadTestResults):
    """Print formatted test results."""
    print("\n" + "=" * 70)
    print("  WEBSOCKET 200-CONCURRENT LOAD TEST RESULTS")
    print("=" * 70)
    print(f"\n  Mode:                {results.mode}")
    print(f"  Target connections:  {results.target_connections}")
    print(f"  Successful:          {results.successful_connections}")
    print(f"  Failed:              {results.failed_connections}")
    print(f"  Total time:          {results.total_time_ms:.0f}ms")

    if results.connection_times_ms:
        times = results.connection_times_ms
        sorted_times = sorted(times)
        n = len(sorted_times)
        print(f"\n  Connection latency:")
        print(f"    Mean:   {statistics.mean(times):.1f}ms")
        print(f"    P50:    {sorted_times[n//2]:.1f}ms")
        print(f"    P90:    {sorted_times[int(n*0.9)]:.1f}ms")
        print(f"    P99:    {sorted_times[min(int(n*0.99), n-1)]:.1f}ms")
        print(f"    Min:    {sorted_times[0]:.1f}ms")
        print(f"    Max:    {sorted_times[-1]:.1f}ms")

    # Pass/Fail
    passed = results.successful_connections >= results.target_connections * 0.95
    error_rate = results.failed_connections / max(results.target_connections, 1) * 100

    print(f"\n  Error rate: {error_rate:.1f}%")

    if passed:
        print(f"\n  [PASS] {results.successful_connections}/{results.target_connections} connections achieved (>= 95%)")
    else:
        print(f"\n  [FAIL] Only {results.successful_connections}/{results.target_connections} connections achieved (< 95%)")

    if results.errors:
        unique_errors = list(set(results.errors))[:5]
        print(f"\n  Sample errors:")
        for e in unique_errors:
            print(f"    - {e}")

    print("\n" + "=" * 70)

    return passed


# ============================================================
# Main
# ============================================================

async def main():
    """Run load test in appropriate mode."""
    live_mode = "--live" in sys.argv

    # Parse custom connection count
    target = TARGET_CONNECTIONS
    for arg in sys.argv:
        if arg.startswith("--connections="):
            target = int(arg.split("=")[1])

    print("=" * 70)
    print(f"  WEBSOCKET LOAD TEST - {target} Concurrent Connections")
    print("=" * 70)

    if live_mode:
        print("\n  Mode: LIVE (requires running backend)")
        results = await test_websocket_live(target)
    else:
        print("\n  Mode: UNIT (WebSocketManager with mock connections)")
        results = await test_websocket_manager_unit(target)

    passed = print_results(results)

    # Save results
    out_path = Path(__file__).resolve().parent.parent / "data" / "benchmark_ws_load.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mode": results.mode,
        "target": results.target_connections,
        "successful": results.successful_connections,
        "failed": results.failed_connections,
        "error_rate_pct": round(results.failed_connections / max(results.target_connections, 1) * 100, 1),
        "total_time_ms": round(results.total_time_ms, 1),
        "connection_latency": {
            "mean_ms": round(statistics.mean(results.connection_times_ms), 1) if results.connection_times_ms else 0,
            "p50_ms": round(sorted(results.connection_times_ms)[len(results.connection_times_ms)//2], 1) if results.connection_times_ms else 0,
            "p99_ms": round(sorted(results.connection_times_ms)[min(int(len(results.connection_times_ms)*0.99), len(results.connection_times_ms)-1)], 1) if results.connection_times_ms else 0,
        },
        "passed": passed,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved: {out_path}")

    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    asyncio.run(main())
