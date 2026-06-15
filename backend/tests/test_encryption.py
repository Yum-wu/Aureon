# -*- coding: utf-8 -*-
"""Tests for app.security.encryption — Fernet round-trip and error paths.

Fernet encryption is the secret-at-rest backbone used by the SSO module
(client_secret columns). A regression here would silently break every
stored SSO provider, so the tests exercise both the happy path and the
real-world failure modes (missing cryptography, wrong key, None input).
"""

import importlib
import os
from unittest.mock import patch

import pytest


@pytest.fixture
def encryption_module():
    """Reload the encryption module to reset its lazy _fernet singleton."""
    import app.security.encryption as enc
    importlib.reload(enc)
    return enc


@pytest.fixture
def fernet_key():
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


class TestEncryptDecryptRoundTrip:
    """The core property: encrypt then decrypt yields the original plaintext."""

    def test_round_trip_preserves_value(self, encryption_module, fernet_key):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            ciphertext = encryption_module.encrypt_secret("hello-world")
            assert ciphertext is not None
            assert ciphertext != "hello-world"  # must not be plaintext
            assert encryption_module.decrypt_secret(ciphertext) == "hello-world"

    def test_round_trip_unicode(self, encryption_module, fernet_key):
        """Fernet must round-trip non-ASCII (Chinese secrets, emoji in keys)."""
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            secret = "中文密码 🔐"
            ciphertext = encryption_module.encrypt_secret(secret)
            assert encryption_module.decrypt_secret(ciphertext) == secret

    def test_round_trip_long_string(self, encryption_module, fernet_key):
        secret = "a" * 10_000  # 10KB
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            ciphertext = encryption_module.encrypt_secret(secret)
            assert encryption_module.decrypt_secret(ciphertext) == secret

    def test_two_encryptions_produce_different_ciphertexts(self, encryption_module, fernet_key):
        """Fernet uses a random IV; the same plaintext must never produce
        the same ciphertext twice. A regression that disables the IV would
        be a serious cryptographic flaw.
        """
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            a = encryption_module.encrypt_secret("same-secret")
            b = encryption_module.encrypt_secret("same-secret")
            assert a != b
            assert encryption_module.decrypt_secret(a) == "same-secret"
            assert encryption_module.decrypt_secret(b) == "same-secret"


class TestEdgeCases:
    """None / empty input handling — must never raise and must never encrypt."""

    def test_encrypt_none_returns_none(self, encryption_module, fernet_key):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            assert encryption_module.encrypt_secret(None) is None

    def test_encrypt_empty_returns_empty(self, encryption_module, fernet_key):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            assert encryption_module.encrypt_secret("") == ""

    def test_decrypt_none_returns_none(self, encryption_module, fernet_key):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            assert encryption_module.decrypt_secret(None) is None

    def test_decrypt_empty_returns_empty(self, encryption_module, fernet_key):
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            assert encryption_module.decrypt_secret("") == ""


class TestWrongKey:
    """Decryption with a different key must fail with a clear ValueError,
    not a stack trace or silent garbage. This protects the operator
    experience when rotating the ENCRYPTION_KEY.
    """

    def test_decrypt_with_wrong_key_raises_value_error(self, encryption_module, fernet_key):
        from cryptography.fernet import Fernet
        other_key = Fernet.generate_key().decode()

        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            ciphertext = encryption_module.encrypt_secret("top-secret")

        # The module caches the fernet for performance; reset it so the
        # second patch.dict env reinitializes the cipher with the new key.
        with patch.dict(os.environ, {"ENCRYPTION_KEY": other_key}):
            encryption_module._fernet = None
            with pytest.raises(ValueError) as exc_info:
                encryption_module.decrypt_secret(ciphertext)
            # Error message must mention decryption failure for operator clarity
            assert "decrypt" in str(exc_info.value).lower() or "Failed" in str(exc_info.value)

    def test_decrypt_garbage_input_raises_value_error(self, encryption_module, fernet_key):
        """Random base64 garbage must not be silently accepted."""
        with patch.dict(os.environ, {"ENCRYPTION_KEY": fernet_key}):
            with pytest.raises(ValueError):
                encryption_module.decrypt_secret("not-a-valid-fernet-token")


class TestProductionSafety:
    """The module must refuse to silently fall back to an ephemeral key in production."""

    def test_missing_key_in_production_raises(self, encryption_module):
        # Force the dev-mode flag off so the runtime check applies.
        fake_settings = type("S", (), {"auth": type("A", (), {"environment": "prod"})()})
        with patch.dict(os.environ, {"ENCRYPTION_KEY": ""}, clear=False):
            # Reset any cached _fernet and re-enter
            encryption_module._fernet = None
            with patch("app.config.settings", fake_settings):
                with pytest.raises(RuntimeError) as exc_info:
                    encryption_module.encrypt_secret("value")
            assert "ENCRYPTION_KEY" in str(exc_info.value)

    def test_dev_mode_allows_ephemeral_key(self, encryption_module):
        """In dev mode, the module may auto-generate an ephemeral key so
        local development doesn't require manual key setup.
        """
        fake_settings = type("S", (), {"auth": type("A", (), {"environment": "dev"})()})
        with patch.dict(os.environ, {"ENCRYPTION_KEY": ""}, clear=False):
            encryption_module._fernet = None
            with patch("app.config.settings", fake_settings):
                # Should not raise; the ephemeral key is used internally.
                ct = encryption_module.encrypt_secret("dev-secret")
                assert ct is not None
                assert encryption_module.decrypt_secret(ct) == "dev-secret"


class TestMissingCryptography:
    """If the cryptography package is missing, encryption must be hard-fail
    on use (raising RuntimeError) rather than returning plaintext silently.
    A silent plaintext fallback would be a catastrophic regression.
    """

    def test_encrypt_without_cryptography_raises(self, encryption_module):
        # Force _fernet to the "disabled" sentinel by simulating the import
        # failure branch.
        encryption_module._fernet = None
        with patch.dict("sys.modules", {"cryptography.fernet": None}):
            # We need to make Fernet itself raise ImportError when instantiated
            with patch("cryptography.fernet.Fernet", side_effect=ImportError("missing")):
                # Re-trigger lazy init; the import guard catches ImportError
                # and sets _fernet to False.
                encryption_module._get_fernet()
                with pytest.raises(RuntimeError) as exc_info:
                    encryption_module.encrypt_secret("value")
                assert "cryptography" in str(exc_info.value).lower() or "installed" in str(exc_info.value)
