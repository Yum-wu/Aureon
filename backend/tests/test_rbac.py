# -*- coding: utf-8 -*-
"""Tests for app.security.rbac — role/permission matrix and JWT round-trip.

RBAC gates every privileged endpoint (SSO admin, audit log query, etc.).
A regression in the role enum ordering or the JWT verify path could grant
ADMIN to any unauthenticated caller, so we exercise the matrix and the
JWT encode/decode boundary directly.
"""

import importlib
import os
import time
from unittest.mock import patch

import pytest


# JWT_SECRET must be set before the rbac module resolves the secret for
# the first time, otherwise _get_jwt_secret() raises RuntimeError.
# Use a 32+ byte secret so the HMAC-SHA256 key length warning doesn't
# clutter test output (RFC 7518 §3.2).
os.environ.setdefault("JWT_SECRET", "test-rbac-secret-only-for-unit-tests-must-be-32b+")


@pytest.fixture
def rbac_module():
    """Reload rbac to reset the lazy _JWT_SECRET singleton between tests."""
    import app.security.rbac as rbac
    importlib.reload(rbac)
    return rbac


# ── Role enum ordering ────────────────────────────────────────────────────
# The RBAC design relies on numeric comparison: ADMIN > EDITOR > VIEWER.
# Re-ordering the IntEnum values silently would either lock everyone out
# or grant every viewer ADMIN. This test pins the contract.


class TestUserRoleOrdering:
    def test_viewer_lt_editor(self, rbac_module):
        assert rbac_module.UserRole.VIEWER < rbac_module.UserRole.EDITOR

    def test_editor_lt_admin(self, rbac_module):
        assert rbac_module.UserRole.EDITOR < rbac_module.UserRole.ADMIN

    def test_full_ordering(self, rbac_module):
        roles = [
            rbac_module.UserRole.VIEWER,
            rbac_module.UserRole.EDITOR,
            rbac_module.UserRole.ADMIN,
        ]
        assert roles == sorted(roles)
        assert list(reversed(roles)) == sorted(roles, reverse=True)


# ── Permission matrix ─────────────────────────────────────────────────────
# The ROLE_PERMISSIONS table is the source of truth for "who can do what".
# Any drift here is a security regression.


class TestRolePermissions:
    def test_viewer_has_only_read(self, rbac_module):
        perms = rbac_module.ROLE_PERMISSIONS[rbac_module.UserRole.VIEWER]
        assert rbac_module.Permission.READ in perms
        # Explicitly assert what viewer must NOT have — these are the
        # privileges a viewer-only user must never accidentally gain.
        assert rbac_module.Permission.WRITE not in perms
        assert rbac_module.Permission.UPLOAD not in perms
        assert rbac_module.Permission.INDEX not in perms
        assert rbac_module.Permission.ADMIN not in perms

    def test_editor_inherits_viewer_plus_write(self, rbac_module):
        perms = rbac_module.ROLE_PERMISSIONS[rbac_module.UserRole.EDITOR]
        assert rbac_module.Permission.READ in perms
        assert rbac_module.Permission.WRITE in perms
        assert rbac_module.Permission.UPLOAD in perms
        # Editor must not be able to do admin-level ops
        assert rbac_module.Permission.INDEX not in perms
        assert rbac_module.Permission.ADMIN not in perms

    def test_admin_has_all_permissions(self, rbac_module):
        perms = rbac_module.ROLE_PERMISSIONS[rbac_module.UserRole.ADMIN]
        for p in rbac_module.Permission:
            assert p in perms, f"ADMIN missing {p}"


# ── has_permission ────────────────────────────────────────────────────────


class TestHasPermission:
    def test_viewer_can_read(self, rbac_module):
        assert rbac_module.has_permission(
            rbac_module.UserRole.VIEWER, rbac_module.Permission.READ
        ) is True

    def test_viewer_cannot_write(self, rbac_module):
        assert rbac_module.has_permission(
            rbac_module.UserRole.VIEWER, rbac_module.Permission.WRITE
        ) is False

    def test_admin_can_admin(self, rbac_module):
        assert rbac_module.has_permission(
            rbac_module.UserRole.ADMIN, rbac_module.Permission.ADMIN
        ) is True

    def test_unknown_role_returns_false(self, rbac_module):
        """Defensive: a malformed role value must never accidentally
        satisfy a permission check.
        """
        # Bypass the enum to construct an invalid role
        assert rbac_module.has_permission("SUPERUSER", rbac_module.Permission.READ) is False


# ── get_user_role ─────────────────────────────────────────────────────────
# The function accepts a dict payload (decoded JWT) and returns a UserRole.
# It must tolerate both string and enum inputs and must default to VIEWER
# for unknown roles (fail-closed, never fail-open).


class TestGetUserRole:
    def test_string_admin_returns_admin(self, rbac_module):
        assert rbac_module.get_user_role({"role": "ADMIN"}) == rbac_module.UserRole.ADMIN

    def test_string_viewer_returns_viewer(self, rbac_module):
        assert rbac_module.get_user_role({"role": "viewer"}) == rbac_module.UserRole.VIEWER

    def test_lowercase_string_is_normalized(self, rbac_module):
        """Case-insensitive lookup — tokens sometimes lowercase the role claim."""
        assert rbac_module.get_user_role({"role": "editor"}) == rbac_module.UserRole.EDITOR

    def test_missing_role_defaults_to_viewer(self, rbac_module):
        """Fail-closed: no role claim → minimal VIEWER access, never ADMIN."""
        assert rbac_module.get_user_role({}) == rbac_module.UserRole.VIEWER

    def test_unknown_role_defaults_to_viewer(self, rbac_module):
        assert rbac_module.get_user_role({"role": "GOD_MODE"}) == rbac_module.UserRole.VIEWER

    def test_passing_role_enum_passes_through(self, rbac_module):
        """Internally, callers may pass the enum directly; the function
        must not re-look it up via UserRole[...].
        """
        assert rbac_module.get_user_role(
            {"role": rbac_module.UserRole.ADMIN}
        ) == rbac_module.UserRole.ADMIN


# ── create_access_token / verify_token ────────────────────────────────────
# The JWT round-trip is the wire-level integrity check. A regression here
# would silently break SSO login (creating tokens that the server then
# rejects, or accepting tokens signed with the wrong algorithm).


class TestJWTRoundTrip:
    def test_create_then_verify_returns_payload(self, rbac_module):
        token = rbac_module.create_access_token({"sub": "alice", "role": "ADMIN"})
        payload = rbac_module.verify_token(token)
        assert payload["sub"] == "alice"
        assert payload["role"] == "ADMIN"

    def test_token_has_expiry_claim(self, rbac_module):
        token = rbac_module.create_access_token({"sub": "bob"})
        payload = rbac_module.verify_token(token)
        assert "exp" in payload
        assert "iat" in payload
        # exp must be in the future
        assert payload["exp"] > int(time.time())

    def test_default_expiry_is_24_hours(self, rbac_module):
        token = rbac_module.create_access_token({"sub": "x"})
        payload = rbac_module.verify_token(token)
        delta = payload["exp"] - payload["iat"]
        # Allow 1 second of slack for clock granularity
        assert 24 * 3600 - 1 <= delta <= 24 * 3600 + 1

    def test_preserves_extra_claims(self, rbac_module):
        token = rbac_module.create_access_token({
            "sub": "carol",
            "tenant_id": "tenant-7",
            "custom": "value",
        })
        payload = rbac_module.verify_token(token)
        assert payload["tenant_id"] == "tenant-7"
        assert payload["custom"] == "value"

    def test_garbage_token_raises_authentication_error(self, rbac_module):
        from app.exceptions import AuthenticationError
        with pytest.raises(AuthenticationError):
            rbac_module.verify_token("not.a.jwt")

    def test_wrong_secret_raises_authentication_error(self, rbac_module):
        """Token signed with a different secret must be rejected."""
        from app.exceptions import AuthenticationError

        # Sign with a different secret (32+ bytes to avoid PyJWT key-length warning)
        import jwt
        forged = jwt.encode(
            {"sub": "evil", "role": "ADMIN", "exp": int(time.time()) + 60},
            "completely-different-secret-of-32-bytes-or-more-xxxxxxxx",
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError):
            rbac_module.verify_token(forged)

    def test_expired_token_raises_authentication_error(self, rbac_module):
        """Expired tokens must be rejected (exp check is mandatory)."""
        from app.exceptions import AuthenticationError
        import jwt

        secret = os.environ["JWT_SECRET"]
        expired = jwt.encode(
            {"sub": "x", "exp": int(time.time()) - 60},
            secret,
            algorithm="HS256",
        )
        with pytest.raises(AuthenticationError) as exc_info:
            rbac_module.verify_token(expired)
        assert "expired" in str(exc_info.value).lower()


# ── _get_jwt_secret — fail-closed on missing secret ──────────────────────
# A misconfigured deployment that omits JWT_SECRET must NOT silently fall
# back to a default secret, or all tokens become forgeable.


class TestJWTSecretResolution:
    def test_missing_jwt_secret_raises_runtime_error(self):
        # Reload the module with no JWT_SECRET in the environment
        env = {k: v for k, v in os.environ.items() if k != "JWT_SECRET"}
        with patch.dict(os.environ, env, clear=True):
            import app.security.rbac as rbac
            rbac._JWT_SECRET = None  # force re-resolution
            with pytest.raises(RuntimeError) as exc_info:
                rbac._get_jwt_secret()
            assert "JWT_SECRET" in str(exc_info.value)

    def test_jwt_secret_is_cached_after_first_read(self, rbac_module):
        """The lazy resolver caches the secret in a module-level singleton
        to avoid re-reading the env on every request. Pin this behavior.
        """
        rbac_module._JWT_SECRET = None
        first = rbac_module._get_jwt_secret()
        # Mutate env; cached value must not change
        with patch.dict(os.environ, {"JWT_SECRET": "different-value"}):
            second = rbac_module._get_jwt_secret()
        assert first == second


# ── Permission boundary enforcement (EX4) ──────────────────────────────────
# The update_role_permissions endpoint enforces that:
# 1. You cannot modify permissions of a role higher than your own
# 2. You cannot grant permissions you don't have


class TestPermissionBoundaryEnforcement:
    """Tests for the role_permission_update permission boundary checks."""

    def test_editor_cannot_modify_admin_role(self, rbac_module):
        """An EDITOR should not be able to modify ADMIN permissions."""
        from fastapi.testclient import TestClient
        from app.main import app

        # Override all existing RBAC overrides to return EDITOR user
        editor_user = {"sub": "editor-user", "role": "EDITOR", "_role": rbac_module.UserRole.EDITOR}
        saved_overrides = dict(app.dependency_overrides)

        async def _mock_editor():
            return editor_user

        for key in list(app.dependency_overrides):
            app.dependency_overrides[key] = _mock_editor

        try:
            client = TestClient(app)
            response = client.put(
                "/api/security/roles/admin",
                json={"permissions": ["read"]},
            )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved_overrides)

    def test_viewer_cannot_grant_write_permission(self, rbac_module):
        """A VIEWER should not be able to grant WRITE permission."""
        from fastapi.testclient import TestClient
        from app.main import app

        # Override all existing RBAC overrides to return VIEWER user
        viewer_user = {"sub": "viewer-user", "role": "VIEWER", "_role": rbac_module.UserRole.VIEWER}
        saved_overrides = dict(app.dependency_overrides)

        async def _mock_viewer():
            return viewer_user

        for key in list(app.dependency_overrides):
            app.dependency_overrides[key] = _mock_viewer

        try:
            client = TestClient(app)
            response = client.put(
                "/api/security/roles/viewer",
                json={"permissions": ["read", "write"]},
            )
            assert response.status_code == 403
        finally:
            app.dependency_overrides.clear()
            app.dependency_overrides.update(saved_overrides)
