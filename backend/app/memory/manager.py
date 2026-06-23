import asyncio
import re
import threading
import time
import structlog

from app.memory import l2_scenario
from app.memory import l3_persona
from app.memory import offload
from app.memory.storage import get_backend

logger = structlog.get_logger()

# ── Constants ──
_INACTIVE_TIMEOUT = 30 * 60        # 30 minutes → auto-finalize
_CLEANUP_INTERVAL = 5 * 60         # check every 5 minutes


def _extract_json_from_llm(text: str) -> str:
    """Extract JSON from LLM output that may include markdown code blocks."""
    # Try ```json ... ``` blocks first
    m = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if m:
        return m.group(1).strip()
    # Try to find JSON array or object directly
    m = re.search(r'[\[\{].*[\]\}]', text, re.DOTALL)
    if m:
        return m.group(0).strip()
    return text.strip()


class MemoryManager:
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._sessions_lock = threading.Lock()
        self._scenario_task: asyncio.Task | None = None

    # ── Session lifecycle ──

    def touch_session(self, session_id: str):
        """Mark a session as recently active (called on each message)."""
        with self._sessions_lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = {"created_at": time.time()}
            self._sessions[session_id]["last_active"] = time.time()

    def get_active_sessions(self) -> list[str]:
        with self._sessions_lock:
            return list(self._sessions.keys())

    def clear_session(self, session_id: str):
        with self._sessions_lock:
            self._sessions.pop(session_id, None)
        logger.info(f"Session cleared: {session_id}")

    # ── Context ──

    def get_context(self, session_id: str) -> str:
        parts = []
        persona = l3_persona.get_persona()
        if persona:
            parts.append(persona)
        scenarios = l2_scenario.get_recent_scenarios(session_id, n=3)
        if scenarios:
            parts.extend(scenarios)
        return "\n".join(parts)

    # ── Message recording ──

    def record_message(self, session_id: str, role: str, content: str, tokens: int = 0,
                       tool_name: str | None = None, tool_args: str | None = None):
        backend = get_backend()
        backend.record_message(session_id, role, content, tokens, tool_name, tool_args)
        backend.cleanup_oldest(session_id)
        self.touch_session(session_id)

    async def extract_atoms(self, session_id: str):
        """Extract atomic facts from conversation using LLM.

        Uses a lightweight LLM call to extract structured facts
        (subject-predicate-object) with confidence scores.
        Falls back to raw message storage on failure.
        """
        backend = get_backend()
        messages = await asyncio.to_thread(backend.get_conversation, session_id, 10)
        if not messages:
            return

        user_msgs = [m for m in messages if m["role"] == "user"]
        if not user_msgs:
            return

        last = user_msgs[-1]
        content = last["content"]

        # Try LLM-based extraction for better quality atoms
        try:
            from app.agent.llm import create_llm
            llm = create_llm(temperature=0.0, streaming=False, max_tokens=200)

            extraction_prompt = f"""Extract 1-3 atomic facts from this user message as JSON array.
Each fact: {{"subject": "...", "predicate": "...", "object": "...", "confidence": 0.0-1.0}}
Only extract clear, factual statements. If no facts, return [].

User message: {content[:500]}"""

            response = await asyncio.to_thread(llm.invoke, extraction_prompt)
            response_text = response.content if hasattr(response, 'content') else str(response)

            # Parse JSON response — robust extraction handles markdown code blocks
            import json
            clean_text = _extract_json_from_llm(response_text)

            atoms = json.loads(clean_text)
            if isinstance(atoms, list):
                for atom in atoms[:3]:  # Max 3 atoms per extraction
                    if all(k in atom for k in ["subject", "predicate", "object"]):
                        confidence = min(max(float(atom.get("confidence", 0.7)), 0.0), 1.0)
                        await asyncio.to_thread(
                            backend.save_atom,
                            session_id,
                            atom["subject"][:50],
                            atom["predicate"][:50],
                            atom["object"][:100],
                            last["id"],
                            confidence,
                        )
                return
        except Exception as e:
            # Fallback to raw message storage on any failure
            logger.debug("atom_extraction_fallback", error=str(e))

        # Fallback: save raw user message as atom
        await asyncio.to_thread(
            backend.save_atom,
            session_id, "user", "said",
            content[:100], last["id"], 0.3,
        )

    # ── Scenario / Persona ──

    def finalize_scenario(self, session_id: str, summary: str = ""):
        l2_scenario.finalize_scenario(session_id, summary=summary)
        l3_persona.update_persona(session_id)

    # ── Offload ──

    def offload_if_needed(self, tool_name: str, content: str, session_id: str) -> str:
        return offload.offload_if_needed(tool_name, content, session_id)

    def read_ref(self, ref_path: str) -> str:
        return offload.read_ref(ref_path)

    # ── Background tasks ──

    def init_background_tasks(self):
        """Start the periodic inactivity-checker task."""
        if self._scenario_task is not None:
            return
        self._scenario_task = asyncio.create_task(self._periodic_cleanup())
        logger.info("Background scenario cleanup task started")

    def flush_all_scenarios(self):
        """Finalize scenarios for all active sessions (called on shutdown)."""
        with self._sessions_lock:
            session_ids = list(self._sessions.keys())
        for sid in session_ids:
            try:
                self.finalize_scenario(sid, summary="会话因服务关闭而结束")
                logger.info(f"Flushed scenario for session {sid}")
            except Exception as e:
                logger.error(f"Failed to flush scenario for session {sid}: {e}")

    async def _periodic_cleanup(self):
        """Periodically check for inactive sessions and auto-finalize."""
        while True:
            try:
                await asyncio.sleep(_CLEANUP_INTERVAL)
                now = time.time()
                with self._sessions_lock:
                    expired_sids = [
                        sid for sid in list(self._sessions.keys())
                        if now - self._sessions[sid].get("last_active", 0) > _INACTIVE_TIMEOUT
                    ]
                for sid in expired_sids:
                    idle_seconds = now - self._sessions[sid].get("last_active", now) if sid in self._sessions else _INACTIVE_TIMEOUT
                    logger.info(f"Auto-finalizing inactive session {sid} (idle={idle_seconds:.0f}s)")
                    try:
                        await asyncio.to_thread(self.finalize_scenario, sid, "会话因超时而结束")
                    except Exception as e:
                        logger.error(f"Auto-finalize failed for {sid}: {e}")
                    with self._sessions_lock:
                        self._sessions.pop(sid, None)
            except asyncio.CancelledError:
                logger.info("Background cleanup task cancelled — allowing graceful shutdown")
                # Let CancelledError propagate for clean shutdown
                raise
            except Exception as e:
                logger.error(f"Periodic cleanup error: {e}")


manager = MemoryManager()
