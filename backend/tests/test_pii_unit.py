# -*- coding: utf-8 -*-
"""Direct unit tests for app.security.pii.PIIDetector.

The existing test_security.py only exercises the PII endpoints through the
HTTP layer. This file tests the detector class directly so we can pin the
regex behavior, mask format, and edge cases (overlapping matches, type
filtering, multi-PII documents) without going through the router.
"""

import pytest

from app.security.pii import PIIDetector


@pytest.fixture
def detector():
    return PIIDetector()


# ── detect() — single PII types ───────────────────────────────────────────


class TestDetectSingleTypes:
    def test_email_detected(self, detector):
        results = detector.detect("Contact me at alice@example.com please")
        assert len(results) == 1
        assert results[0]["type"] == "email"
        assert results[0]["value"] == "alice@example.com"
        assert results[0]["start"] == 14
        assert results[0]["end"] == 14 + len("alice@example.com")

    def test_chinese_phone_detected(self, detector):
        results = detector.detect("我的手机号是 13812345678")
        assert any(r["type"] == "phone_cn" and r["value"] == "13812345678" for r in results)

    def test_us_phone_detected(self, detector):
        results = detector.detect("Call +14155552671 for support")
        assert any(r["type"] == "phone_us" for r in results)

    def test_chinese_id_card_detected(self, detector):
        # 18-digit Chinese national ID
        id_num = "11010519491231002X"
        results = detector.detect(f"ID: {id_num}")
        assert any(r["type"] == "id_card_cn" and r["value"] == id_num for r in results)

    def test_ip_address_detected(self, detector):
        results = detector.detect("Server at 192.168.1.1 was down")
        assert any(r["type"] == "ip_address" and r["value"] == "192.168.1.1" for r in results)


# ── detect() — multi-PII documents ───────────────────────────────────────


class TestDetectMultiplePIIs:
    def test_multiple_emails_in_one_text(self, detector):
        text = "Email alice@a.com or bob@b.com for help"
        results = detector.detect(text)
        emails = [r for r in results if r["type"] == "email"]
        assert len(emails) == 2
        values = {r["value"] for r in emails}
        assert values == {"alice@a.com", "bob@b.com"}

    def test_mixed_pii_types(self, detector):
        text = "alice@example.com, phone 13812345678, IP 10.0.0.1"
        results = detector.detect(text)
        types = {r["type"] for r in results}
        assert "email" in types
        assert "phone_cn" in types
        assert "ip_address" in types

    def test_overlapping_positions(self, detector):
        """Each match must have correct start/end even when patterns overlap
        in the input (e.g. phone number inside a longer string).
        """
        text = "tel:13812345678,alt:13987654321"
        results = detector.detect(text)
        phones = [r for r in results if r["type"] == "phone_cn"]
        # Both phone numbers must be detected with non-overlapping spans
        assert len(phones) == 2
        for p in phones:
            assert text[p["start"]:p["end"]] == p["value"]


# ── detect() — negative cases ─────────────────────────────────────────────


class TestDetectNegative:
    def test_no_pii_returns_empty(self, detector):
        assert detector.detect("The quick brown fox jumps over the lazy dog") == []

    def test_empty_text(self, detector):
        assert detector.detect("") == []

    def test_looks_like_email_but_invalid(self, detector):
        """The current regex accepts `@` followed by any 2+ char TLD.
        The crucial property is that it does NOT return false positives
        for plain prose that contains '@' as English usage.
        """
        # PII detector's regex is permissive; assert it does at least NOT
        # match a non-email string without a TLD.
        results = detector.detect("user@server")  # no TLD, no dot
        emails = [r for r in results if r["type"] == "email"]
        assert emails == []


# ── mask() — masking behavior ────────────────────────────────────────────


class TestMaskAll:
    def test_mask_all_pii_in_text(self, detector):
        result = detector.mask("Email: alice@example.com, phone 13812345678")
        assert "alice@example.com" not in result
        assert "13812345678" not in result
        # The original prose must survive
        assert "Email:" in result
        assert "phone" in result

    def test_mask_no_pii_unchanged(self, detector):
        text = "Plain text with no sensitive data"
        assert detector.mask(text) == text

    def test_mask_empty_string(self, detector):
        assert detector.mask("") == ""

    def test_mask_ip_address_replaced(self, detector):
        result = detector.mask("server 192.168.1.1")
        assert "192.168.1.1" not in result
        assert "*.*.*.*" in result


class TestMaskSingleType:
    """When pii_type is given, only that pattern is replaced; other PII
    types survive intact. This is used by the document scanner to apply
    the organization's masking policy per type.
    """

    def test_mask_email_only_preserves_phone(self, detector):
        text = "Email alice@a.com phone 13812345678"
        result = detector.mask(text, pii_type="email")
        assert "alice@a.com" not in result
        # Phone must survive when only email is masked
        assert "13812345678" in result

    def test_mask_phone_only_preserves_email(self, detector):
        text = "Email alice@a.com phone 13812345678"
        result = detector.mask(text, pii_type="phone_cn")
        assert "13812345678" not in result
        assert "alice@a.com" in result

    def test_mask_unknown_type_is_no_op(self, detector):
        """An unknown pii_type must not raise and must not corrupt the text."""
        text = "alice@example.com"
        result = detector.mask(text, pii_type="biometric_fingerprint")
        assert result == text


# ── pattern stability ─────────────────────────────────────────────────────
# The PATTERNS dict is the contract for downstream consumers. Adding or
# removing a key is a breaking change for any client filtering on type.


class TestPatternsContract:
    def test_required_patterns_present(self, detector):
        for required in ("email", "phone_cn", "phone_us", "id_card_cn",
                         "bank_card", "ip_address"):
            assert required in detector.PATTERNS, f"missing pattern: {required}"

    def test_patterns_are_nonempty_strings(self, detector):
        for name, pat in detector.PATTERNS.items():
            assert isinstance(pat, str)
            assert len(pat) > 0
