# -*- coding: utf-8 -*-
"""Tests for app.common — secret masking, deterministic hashing, SSE format.

`mask_secret` is the de-facto API response sanitizer for every secret
returned to the UI (SSO client_secret, encryption keys, API tokens).
A regression that leaks the full secret would expose every enterprise
customer's credentials. The other helpers are smaller, but bugs there
cause cross-process feature-flag flicker and broken SSE streams.
"""

import json

from app.common import (
    deterministic_hash,
    mask_secret,
    rows_to_models,
    sse_event,
    utc_now_iso,
)


# ── mask_secret ───────────────────────────────────────────────────────────
# Used by sso.list_sso_providers and similar to return a redacted
# client_secret in API responses. The "show first 4 chars" contract is
# a UX feature: the operator can identify which secret it is.


class TestMaskSecret:
    def test_long_string_shows_prefix(self):
        """Long secret: show first 4 chars + 4-star mask."""
        assert mask_secret("sk-abcdefghijklmnop") == "sk-a****"

    def test_custom_show_chars(self):
        assert mask_secret("abcdefghij", show_chars=2) == "ab****"

    def test_show_chars_zero(self):
        """show_chars=0 means no prefix shown — used to fully redact."""
        assert mask_secret("secret-value", show_chars=0) == "****"

    def test_at_threshold_returns_full_mask(self):
        """Length equal to show_chars: still redact (not safe to show all)."""
        assert mask_secret("abcd", show_chars=4) == "****"

    def test_below_threshold_returns_full_mask(self):
        assert mask_secret("abc", show_chars=4) == "****"

    def test_empty_string_returns_empty(self):
        assert mask_secret("") == ""

    def test_none_returns_none(self):
        assert mask_secret(None) is None

    def test_default_show_chars_is_4(self):
        """Pin the default — callers that omit show_chars depend on this."""
        assert mask_secret("1234567890") == "1234****"

    def test_does_not_truncate_input(self):
        """The function must not modify the input list by aliasing."""
        original = "sk-supersecret"
        masked = mask_secret(original)
        assert original == "sk-supersecret"
        assert masked == "sk-s****"


# ── deterministic_hash ────────────────────────────────────────────────────
# Cross-process stable hash used to assign tenants/users to feature-flag
# buckets. Builtin hash() is randomized per-process; this function is the
# only way to get a stable bucket across worker processes.


class TestDeterministicHash:
    def test_same_input_same_output(self):
        assert deterministic_hash("tenant-7") == deterministic_hash("tenant-7")

    def test_different_inputs_different_outputs_usually(self):
        # The hash space is modulo 100; we test statistical uniqueness, not
        # absolute uniqueness.
        a = deterministic_hash("alpha")
        b = deterministic_hash("beta")
        assert a != b

    def test_respects_modulo(self):
        for mod in (1, 10, 100, 1000):
            result = deterministic_hash("test", modulo=mod)
            assert 0 <= result < mod

    def test_stable_across_invocations(self):
        """Critical: must not depend on PYTHONHASHSEED."""
        a = deterministic_hash("user-42")
        b = deterministic_hash("user-42")
        c = deterministic_hash("user-42")
        assert a == b == c

    def test_unicode_input_supported(self):
        """Tenant IDs may include non-ASCII characters (e.g. 租户_7)."""
        a = deterministic_hash("租户_7")
        b = deterministic_hash("租户_7")
        assert a == b
        assert 0 <= a < 100


# ── rows_to_models ────────────────────────────────────────────────────────
# Adapter from DB rows (dict-like) → pydantic BaseModel used by list
# endpoints. A bug here breaks the contract for all of them at once.


class TestRowsToModels:
    def test_converts_rows_to_pydantic_models(self):
        from pydantic import BaseModel

        class Item(BaseModel):
            id: int
            name: str

        rows = [{"id": 1, "name": "alpha"}, {"id": 2, "name": "beta"}]
        result = rows_to_models(rows, Item)
        assert len(result) == 2
        assert all(isinstance(r, Item) for r in result)
        assert result[0].id == 1
        assert result[0].name == "alpha"

    def test_empty_rows_returns_empty_list(self):
        from pydantic import BaseModel

        class Item(BaseModel):
            id: int

        assert rows_to_models([], Item) == []

    def test_accepts_row_dicts_with_extra_keys(self):
        """If a row has DB columns the model doesn't know about, the
        function must still produce a model (the pydantic model ignores
        extras by default; this is the project convention).
        """
        from pydantic import BaseModel

        class Item(BaseModel):
            id: int
            name: str

        rows = [{"id": 1, "name": "x", "created_at": "2026-01-01"}]
        result = rows_to_models(rows, Item)
        assert result[0].id == 1


# ── sse_event ─────────────────────────────────────────────────────────────
# SSE wire format used by chat, crew, and RAG streaming endpoints. A
# regression in the format would break every streaming response in
# production.


class TestSSEEvent:
    def test_basic_format(self):
        result = sse_event({"type": "text", "content": "hi"})
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

    def test_payload_is_valid_json(self):
        result = sse_event({"type": "done"})
        payload = result[len("data: "):].rstrip("\n")
        assert json.loads(payload) == {"type": "done"}

    def test_unicode_preserved(self):
        result = sse_event({"type": "text", "content": "你好世界"})
        # Chinese must not be escaped to \uXXXX — that wastes bytes and
        # makes logs unreadable.
        assert "你好世界" in result

    def test_serialization_uses_ensure_ascii_false(self):
        """ensure_ascii=False is critical for non-ASCII streaming tokens.
        This test pins that behavior at the call-site rather than relying
        on the global json.dumps default.
        """
        result = sse_event({"content": "中文"})
        # If ensure_ascii were True, the JSON would contain "\u4e2d\u6587"
        assert "\\u" not in result

    def test_done_event_has_no_extra_blank_lines(self):
        """An SSE message MUST be terminated by exactly two newlines; extra
        blank lines would desynchronize the client parser.
        """
        result = sse_event({"type": "done"})
        # Strip the data: prefix; the remaining is the JSON + \n\n
        trailing = result[len("data: "):]
        assert trailing.endswith("\n\n")
        assert not trailing.endswith("\n\n\n")


# ── utc_now_iso ───────────────────────────────────────────────────────────
# Replacement for deprecated datetime.utcnow(). Pin the format so any
# downstream consumer that parses the string (logs, audit, telemetry)
# continues to work.


class TestUtcNowIso:
    def test_returns_string(self):
        assert isinstance(utc_now_iso(), str)

    def test_format_is_iso8601(self):
        """Strict ISO-8601 with timezone offset (UTC)."""
        from datetime import datetime

        s = utc_now_iso()
        # Should round-trip via fromisoformat
        parsed = datetime.fromisoformat(s)
        assert parsed.tzinfo is not None  # timezone-aware

    def test_close_to_current_time(self):
        import time
        from datetime import datetime
        before = time.time()
        iso = utc_now_iso()
        after = time.time()
        parsed = datetime.fromisoformat(iso).timestamp()
        assert before - 1 <= parsed <= after + 1
