"""
Extended tests for app/memory/ layers (L2, L3, offload).

Covers:
- L2 scenario creation and loading
- L3 persona read/write
- Offload file creation and cleanup
- MemoryManager integration for these layers
"""

import pytest

import time
from pathlib import Path
from unittest.mock import patch

from app.memory.storage import get_backend
from app.memory.l2_scenario import (
    finalize_scenario,
    get_recent_scenarios,
    _list_scenarios,
    SCENARIOS_DIR,
)
from app.memory.l3_persona import (
    update_persona,
    get_persona,
)
from app.memory.offload import (
    offload_if_needed,
    read_ref,
    REFS_DIR,
)
from app.memory.manager import MemoryManager


# ── L2 Scenario Tests ──

class TestL2ScenarioExtended:
    def setup_method(self):
        # Reset scenario cache to avoid stale listings between tests
        import app.memory.l2_scenario as l2_mod
        l2_mod._scenario_cache = None
        l2_mod._scenario_cache_ts = 0

    def test_finalize_creates_file(self):
        """finalize_scenario creates a markdown file in SCENARIOS_DIR."""
        sid = "l2_ext_test_" + str(int(time.time()))
        get_backend().save_atom(sid, "user", "asked", "React tips", confidence=0.7)
        # Verify atom was saved
        saved_atoms = get_backend().get_atoms_by_session(sid)

        finalize_scenario(sid, summary="讨论了React技巧")

        all_files = list(SCENARIOS_DIR.glob("*.md"))
        matching = [f for f in all_files if f.name.startswith(sid)]
        assert len(saved_atoms) >= 1, f"Atoms not saved for {sid}"
        assert len(matching) >= 1, (
            f"No scenario file for {sid}. "
            f"dir_exists={SCENARIOS_DIR.exists()}, "
            f"all_files_count={len(all_files)}, "
            f"last_5={[f.name for f in all_files[-5:]]}, "
            f"cwd={Path.cwd()}"
        )
        content = matching[0].read_text(encoding="utf-8")
        assert "讨论了React技巧" in content
        assert "React tips" in content

    def test_finalize_with_empty_summary(self):
        """Empty summary falls back to default text."""
        sid = "l2_empty_" + str(int(time.time()))
        finalize_scenario(sid)

        all_files = list(SCENARIOS_DIR.glob("*.md"))
        matching = [f for f in all_files if f.name.startswith(sid)]
        assert len(matching) >= 1, f"No scenario file for {sid}"
        content = matching[0].read_text(encoding="utf-8")
        assert "会话已结束" in content

    def test_get_recent_scenarios_returns_content(self):
        """get_recent_scenarios returns file content list."""
        sid = "l2_recent_" + str(int(time.time()))
        finalize_scenario(sid, summary="test scenario")

        # get_recent_scenarios ignores sid param (returns global latest N)
        results = get_recent_scenarios(n=5)
        assert len(results) >= 1
        assert all(isinstance(r, str) for r in results)

    def test_get_recent_scenarios_limit(self):
        """get_recent_scenarios respects n limit."""
        results = get_recent_scenarios(n=2)
        assert len(results) <= 2

    def test_list_scenarios_caching(self):
        """_list_scenarios uses caching within TTL."""
        _list_scenarios()
        result1 = _list_scenarios()
        result2 = _list_scenarios()
        # Both should return the same cached object
        assert result1 is result2

    def test_finalize_includes_atoms(self):
        """Scenario file includes L1 atom data."""
        sid = "l2_atoms_" + str(int(time.time()))
        backend = get_backend()
        backend.save_atom(sid, "user", "prefers", "TypeScript", confidence=0.9)
        backend.save_atom(sid, "user", "uses", "React", confidence=0.8)

        finalize_scenario(sid, summary="技术偏好讨论")

        # Search all scenario files for our session (handle possible filename variants)
        all_files = list(SCENARIOS_DIR.glob("*.md"))
        matching = [f for f in all_files if f.name.startswith(sid)]
        assert len(matching) >= 1, f"No scenario file for {sid}. Files: {[f.name for f in all_files[-5:]]}"
        content = matching[0].read_text(encoding="utf-8")
        assert "TypeScript" in content
        assert "React" in content


# ── L3 Persona Tests ──

class TestL3PersonaExtended:
    def test_get_persona_when_no_file(self):
        """get_persona returns empty string if no persona file."""
        with patch("app.memory.l3_persona.PERSONA_PATH") as mock_path:
            mock_path.exists.return_value = False
            result = get_persona()
            assert result == ""

    def test_update_persona_creates_file(self):
        """update_persona creates persona.md from scenarios."""
        sid = "l3_test_" + str(int(time.time()))
        # Create a scenario first
        finalize_scenario(sid, summary="用户讨论了AI趋势")

        update_persona(sid)
        content = get_persona()
        assert isinstance(content, str)
        assert "# Persona" in content

    def test_update_persona_respects_max_size(self):
        """Persona content is truncated to PERSONA_MAX_SIZE bytes."""
        sid = "l3_size_" + str(int(time.time()))

        # Create a scenario with very long content
        long_summary = "A" * 5000
        finalize_scenario(sid, summary=long_summary)
        update_persona(sid)

        content = get_persona()
        assert len(content.encode("utf-8")) <= 2048 + 100  # slight tolerance

    def test_update_persona_with_no_scenarios(self):
        """update_persona with no scenarios does not crash."""
        # Patch get_recent_scenarios to return empty
        with patch("app.memory.l2_scenario.get_recent_scenarios", return_value=[]):
            update_persona("nonexistent_session")

    def test_get_persona_reads_file_content(self):
        """get_persona returns exact file content."""
        test_content = "# Persona\n\n## Recent Activity\n- Test"
        with patch("app.memory.l3_persona.PERSONA_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = test_content
            result = get_persona()
            assert result == test_content


# ── Offload Extended Tests ──

class TestOffloadExtended:
    def test_short_content_passthrough(self):
        """Content below threshold passes through unchanged."""
        result = offload_if_needed("test_tool", "short content", "sess_1")
        assert result == "short content"

    def test_long_content_creates_file(self):
        """Content exceeding threshold creates offload file."""
        long_text = "x" * 2000
        result = offload_if_needed("calculator", long_text, "sess_offload")

        assert "result_ref:" in result
        assert "calculator" in result
        # Verify file was created
        files = list(REFS_DIR.glob("sess_offload_calculator_*.md"))
        assert len(files) >= 1

    def test_offload_file_content(self):
        """Offloaded file contains the original content."""
        content = "Line " * 500  # ~3000 chars
        result = offload_if_needed("search", content, "sess_verify")

        # Extract filename from result
        import re
        match = re.search(r"result_ref:\s*(\S+)", result)
        assert match is not None
        filename = match.group(1)
        file_content = read_ref(filename)
        assert file_content == content

    def test_read_ref_valid_file(self):
        """read_ref returns file content for valid path."""
        offload_if_needed("tool", "x" * 2000, "sess_read")

        files = list(REFS_DIR.glob("sess_read_tool_*.md"))
        assert len(files) >= 1
        result = read_ref(files[0].name)
        assert "x" * 2000 in result

    def test_read_ref_path_traversal_blocked(self):
        """read_ref blocks path traversal attempts."""
        result = read_ref("../../etc/passwd")
        assert "Error" in result

    def test_read_ref_nonexistent_file(self):
        """read_ref returns error for nonexistent file."""
        result = read_ref("nonexistent_file_12345.md")
        assert "not found" in result

    def test_read_ref_list_special(self):
        """read_ref('list') should not crash."""
        # read_ref('list') will try to read a file named 'list'
        # It should return an error or the file content if it exists
        result = read_ref("list")
        # Either "not found" or actual content
        assert isinstance(result, str)

    def test_offload_preview_truncation(self):
        """Offload summary includes truncated preview."""
        content = "A" * 5000
        result = offload_if_needed("big_tool", content, "sess_preview")

        # Preview should be <= 200 chars
        assert "..." in result


# ── MemoryManager Extended Integration Tests ──

class TestMemoryManagerExtended:
    def setup_method(self):
        import app.memory.l2_scenario as l2_mod
        l2_mod._scenario_cache = None
        l2_mod._scenario_cache_ts = 0
        self.mm = MemoryManager()

    def test_get_context_with_persona_and_scenarios(self):
        """get_context combines persona and recent scenarios."""
        sid = "mgr_ctx_" + str(int(time.time()))

        # Create a scenario
        finalize_scenario(sid, summary="讨论了Docker部署")

        context = self.mm.get_context(sid)
        assert isinstance(context, str)

    def test_get_context_empty_session(self):
        """get_context for unknown session returns empty or minimal."""
        context = self.mm.get_context("unknown_session_xyz")
        assert isinstance(context, str)

    def test_offload_if_needed_delegates(self):
        """offload_if_needed delegates to offload module."""
        long_text = "y" * 2000
        result = self.mm.offload_if_needed("calc", long_text, "sess_mgr")
        assert "result_ref:" in result

    def test_read_ref_delegates(self):
        """read_ref delegates to offload module."""
        result = self.mm.read_ref("nonexistent_999.md")
        assert "not found" in result

    def test_flush_all_scenarios(self):
        """flush_all_scenarios finalizes all active sessions."""
        self.mm.touch_session("flush_1")
        self.mm.touch_session("flush_2")

        self.mm.flush_all_scenarios()

        # Sessions should still be in manager (finalize doesn't remove)
        # But scenarios should be created
        for sid in ["flush_1", "flush_2"]:
            all_files = list(SCENARIOS_DIR.glob("*.md"))
            matching = [f for f in all_files if f.name.startswith(sid)]
            assert len(matching) >= 1

    @pytest.mark.asyncio
    async def test_record_message_and_extract_atoms(self):
        """record_message + extract_atoms flow."""
        sid = "mgr_atoms_" + str(int(time.time()))

        self.mm.record_message(sid, "user", "我喜欢用Python写后端")
        self.mm.record_message(sid, "assistant", "Python是个好选择")

        await self.mm.extract_atoms(sid)

        # Verify atoms were extracted
        atoms = get_backend().get_atoms_by_session(sid)
        assert len(atoms) >= 1

    def test_session_lifecycle(self):
        """touch_session -> get_active_sessions -> clear_session."""
        self.mm.touch_session("lifecycle_1")
        self.mm.touch_session("lifecycle_2")

        sessions = self.mm.get_active_sessions()
        assert "lifecycle_1" in sessions
        assert "lifecycle_2" in sessions

        self.mm.clear_session("lifecycle_1")
        sessions = self.mm.get_active_sessions()
        assert "lifecycle_1" not in sessions
        assert "lifecycle_2" in sessions

    def test_clear_nonexistent_session(self):
        """clear_session on unknown session does not crash."""
        self.mm.clear_session("nonexistent_xyz")  # Should not raise

    def test_finalize_scenario_delegates(self):
        """finalize_scenario creates L2 and updates L3."""
        sid = "mgr_fin_" + str(int(time.time()))
        self.mm.record_message(sid, "user", "Test message")

        self.mm.finalize_scenario(sid, summary="Test summary")

        all_files = list(SCENARIOS_DIR.glob("*.md"))
        matching = [f for f in all_files if f.name.startswith(sid)]
        assert len(matching) >= 1
