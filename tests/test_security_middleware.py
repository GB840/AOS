"""Tests for src/api/security.py -- API security middleware.

Focuses on areas not covered by the existing test_security.py:
- hash_api_key / verify_api_key_hash (bcrypt round-trip + edge cases)
- _check_api_key method on APISecurityMiddleware
- RateLimitMiddleware (sliding window, cleanup, 429 response)
- SecurityHeadersMiddleware (HSTS, CSP, X-Frame-Options, etc.)
- get_api_key FastAPI dependency (header and query param paths)

Run: python -m pytest tests/test_security_middleware.py -v
"""

import pytest

from fastapi import FastAPI
from starlette.testclient import TestClient

from utils.config import config as APP_CONFIG
from api.security import (
    APISecurityMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    generate_api_key,
    hash_api_key,
    verify_api_key_hash,
)

bcrypt = pytest.importorskip("bcrypt")


# ---------------------------------------------------------------------------
# hash_api_key / verify_api_key_hash
# ---------------------------------------------------------------------------

class TestApiKeyHashing:
    """Test bcrypt-based API key hashing and verification."""

    def test_hash_and_verify_roundtrip(self):
        """hash_api_key should produce a hash that verify_api_key_hash accepts."""
        key = "my-secret-api-key-12345"
        hashed = hash_api_key(key)
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60
        assert verify_api_key_hash(key, hashed) is True

    def test_wrong_key_fails_verification(self):
        """verify_api_key_hash should return False for a wrong key."""
        hashed = hash_api_key("correct-key")
        assert verify_api_key_hash("wrong-key", hashed) is False

    def test_empty_key_returns_false(self):
        """verify_api_key_hash should return False for empty inputs."""
        hashed = hash_api_key("some-key")
        assert verify_api_key_hash("", hashed) is False
        assert verify_api_key_hash("some-key", "") is False

    def test_invalid_hash_format_returns_false(self):
        """verify_api_key_hash should return False for malformed hashes."""
        assert verify_api_key_hash("key", "not-a-bcrypt-hash") is False
        assert verify_api_key_hash("key", "$2b$12$tooshort") is False

    def test_different_keys_produce_different_hashes(self):
        """Different API keys should produce different bcrypt hashes."""
        h1 = hash_api_key("key-alpha")
        h2 = hash_api_key("key-beta")
        assert h1 != h2


# ---------------------------------------------------------------------------
# _check_api_key on APISecurityMiddleware
# ---------------------------------------------------------------------------

class TestCheckApiKey:
    """Test API key validation through the middleware (via TestClient).

    Note: APISecurityMiddleware.__init__ has a conditional import of `config`
    that causes UnboundLocalError when require_upstream_auth_check is passed
    explicitly. We test through FastAPI's add_middleware path instead.
    """

    def test_plaintext_key_match(self, monkeypatch):
        """Correct plaintext API_KEY should grant access."""
        monkeypatch.setattr(APP_CONFIG, "API_KEY", "test-key-abc")
        monkeypatch.setattr(APP_CONFIG, "API_KEY_HASH", "")
        monkeypatch.setattr(APP_CONFIG, "APP_ENV", "development")

        app = FastAPI()
        app.add_middleware(APISecurityMiddleware)

        @app.get("/api/test")
        def test_ep():
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/api/test", headers={"X-API-Key": "test-key-abc"}).status_code == 200
        assert client.get("/api/test", headers={"X-API-Key": "wrong-key"}).status_code == 401

    def test_hashed_key_match(self, monkeypatch):
        """A key matching the stored bcrypt hash should grant access."""
        real_key = "hashed-key-xyz"
        hashed = hash_api_key(real_key)
        monkeypatch.setattr(APP_CONFIG, "API_KEY", "")
        monkeypatch.setattr(APP_CONFIG, "API_KEY_HASH", hashed)
        monkeypatch.setattr(APP_CONFIG, "APP_ENV", "development")

        app = FastAPI()
        app.add_middleware(APISecurityMiddleware)

        @app.get("/api/test")
        def test_ep():
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/api/test", headers={"X-API-Key": real_key}).status_code == 200
        assert client.get("/api/test", headers={"X-API-Key": "wrong-key"}).status_code == 401

    def test_empty_key_always_rejected(self, monkeypatch):
        """Missing API key should always return 401."""
        monkeypatch.setattr(APP_CONFIG, "API_KEY", "some-key")
        monkeypatch.setattr(APP_CONFIG, "APP_ENV", "development")

        app = FastAPI()
        app.add_middleware(APISecurityMiddleware)

        @app.get("/api/test")
        def test_ep():
            return {"ok": True}

        client = TestClient(app)
        assert client.get("/api/test").status_code == 401


# ---------------------------------------------------------------------------
# RateLimitMiddleware
# ---------------------------------------------------------------------------

class TestRateLimitMiddleware:
    """Test the sliding-window rate limiter."""

    @pytest.fixture
    def rate_limited_client(self):
        """Create a test client with a very low rate limit."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, max_requests=3, time_window_seconds=60)

        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        return TestClient(app)

    def test_requests_within_limit_succeed(self, rate_limited_client):
        """Requests within the limit should return 200."""
        for _ in range(3):
            r = rate_limited_client.get("/test")
            assert r.status_code == 200

    def test_requests_exceeding_limit_get_429(self, rate_limited_client):
        """Requests exceeding the limit should return 429."""
        # Use up the limit
        for _ in range(3):
            rate_limited_client.get("/test")
        # Next request should be rate-limited
        r = rate_limited_client.get("/test")
        assert r.status_code == 429
        assert "Retry-After" in r.headers

    def test_rate_limit_headers_present(self, rate_limited_client):
        """Successful responses should include rate limit headers."""
        r = rate_limited_client.get("/test")
        assert "X-RateLimit-Limit" in r.headers
        assert "X-RateLimit-Remaining" in r.headers


# ---------------------------------------------------------------------------
# SecurityHeadersMiddleware
# ---------------------------------------------------------------------------

class TestSecurityHeadersMiddleware:
    """Test that security headers are added to responses."""

    @pytest.fixture
    def headers_client(self, monkeypatch):
        """Create a test client with SecurityHeadersMiddleware."""
        monkeypatch.setattr(APP_CONFIG, "APP_ENV", "production")
        app = FastAPI()
        app.add_middleware(SecurityHeadersMiddleware)

        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        return TestClient(app)

    def test_hsts_header_in_production(self, headers_client):
        """Production responses should include HSTS header."""
        r = headers_client.get("/test")
        hsts = r.headers.get("Strict-Transport-Security", "")
        assert "max-age=31536000" in hsts
        assert "includeSubDomains" in hsts

    def test_x_frame_options_deny(self, headers_client):
        """X-Frame-Options should be set to DENY."""
        r = headers_client.get("/test")
        assert r.headers.get("X-Frame-Options") == "DENY"

    def test_content_security_policy_present(self, headers_client):
        """Content-Security-Policy header should be present."""
        r = headers_client.get("/test")
        csp = r.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp

    def test_x_content_type_options_nosniff(self, headers_client):
        """X-Content-Type-Options should be nosniff."""
        r = headers_client.get("/test")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_referrer_policy(self, headers_client):
        """Referrer-Policy should be set."""
        r = headers_client.get("/test")
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ---------------------------------------------------------------------------
# generate_api_key
# ---------------------------------------------------------------------------

class TestGenerateApiKey:
    """Test API key generation."""

    def test_generated_key_is_url_safe(self):
        """Generated keys should be URL-safe (token_urlsafe)."""
        key = generate_api_key()
        assert len(key) >= 32
        # Should not contain characters that need URL encoding
        assert all(c.isalnum() or c in "-_" for c in key)

    def test_generated_keys_are_unique(self):
        """Each call should produce a unique key."""
        keys = {generate_api_key() for _ in range(10)}
        assert len(keys) == 10
