"""Regression tests for MemoryManager._periodic_cleanup.

Covers Phase 1 Task 1.7 (graceful shutdown): when the background cleanup
loop receives ``asyncio.CancelledError`` it MUST re-raise so the asyncio
task terminates. If a regression swallows the cancellation, the process
hangs on shutdown and the scenario task keeps the event loop alive.
"""

import asyncio

import pytest


# Real sleep reference, captured before any monkey-patching of asyncio.sleep.
_REAL_SLEEP = asyncio.sleep


class TestPeriodicCleanupShutdown:
    async def test_cancelled_error_propagates(self, monkeypatch):
        """CancelledError must propagate so the task ends gracefully."""
        from app.memory import manager as mgr_mod
        from app.memory.manager import MemoryManager

        # Replace the production sleep with one that returns immediately,
        # but is itself backed by the REAL sleep (so it cannot recurse).
        async def fast_sleep(_):
            await _REAL_SLEEP(0)
        monkeypatch.setattr(mgr_mod.asyncio, "sleep", fast_sleep)

        mgr = MemoryManager()
        task = asyncio.create_task(mgr._periodic_cleanup())
        # Yield once so the loop starts.
        await _REAL_SLEEP(0)
        task.cancel()

        # The bug being guarded: if CancelledError is swallowed, the task
        # would loop forever; the await below would never return.
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)
        assert task.done()

    async def test_cleanup_iteration_uses_configured_interval(self, monkeypatch):
        """The fix must still call asyncio.sleep with the configured
        interval constant — assert this by recording the sleep argument.
        """
        from app.memory import manager as mgr_mod
        from app.memory.manager import MemoryManager

        sleeps = []

        async def recording_sleep(seconds):
            sleeps.append(seconds)
            await _REAL_SLEEP(0)

        monkeypatch.setattr(mgr_mod.asyncio, "sleep", recording_sleep)

        mgr = MemoryManager()
        task = asyncio.create_task(mgr._periodic_cleanup())
        # Let the loop tick a couple of times.
        for _ in range(3):
            await _REAL_SLEEP(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)

        # The loop must have slept with the documented interval constant.
        assert sleeps, "expected at least one sleep call"
        assert all(s == mgr_mod._CLEANUP_INTERVAL for s in sleeps)

    async def test_non_cancellation_exception_does_not_kill_loop(self, monkeypatch):
        """A non-cancellation exception in the cleanup body must be logged
        and the loop must continue — only CancelledError should terminate
        the task.
        """
        from app.memory import manager as mgr_mod
        from app.memory.manager import MemoryManager

        iteration = {"n": 0}

        async def fake_sleep(_):
            iteration["n"] += 1
            if iteration["n"] >= 4:
                raise asyncio.CancelledError()
            await _REAL_SLEEP(0)

        monkeypatch.setattr(mgr_mod.asyncio, "sleep", fake_sleep)

        mgr = MemoryManager()

        # Force the body to raise a non-cancellation error every iteration.
        def boom(*args, **kwargs):
            raise RuntimeError("simulated cleanup failure")

        monkeypatch.setattr(mgr_mod.l2_scenario, "finalize_scenario", boom)
        monkeypatch.setattr(mgr_mod.l3_persona, "update_persona", boom)

        # Pre-seed a session and backdate it so the cleanup branch runs.
        mgr.touch_session("sess_x")
        mgr._sessions["sess_x"]["last_active"] = 0

        task = asyncio.create_task(mgr._periodic_cleanup())
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=2.0)

        # Loop survived multiple iterations despite repeated errors.
        assert iteration["n"] >= 2
