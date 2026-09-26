"""
Session security: JWT access tokens, refresh rotation, CSRF, persistence.

These cover the properties that the Phase 2 placeholder did not have —
sessions surviving a restart, revocable tokens, and protection against a
stolen refresh token being replayed.
"""

import time
from datetime import timedelta

import jwt
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db, offline):
    from api.main import app

    with TestClient(app) as c:
        yield c


def register(client, username="sessionuser", password="session-pass-1"):
    r = client.post("/auth/register", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    from api import security
    client.headers[security.CSRF_HEADER] = r.json()["csrf_token"]
    return r.json()


# ── Access tokens ─────────────────────────────────────────────────────────────

def test_access_token_is_a_signed_jwt(temp_db):
    from api import security

    token = security.create_access_token(7, "alice")
    payload = jwt.decode(token, security.SECRET_KEY, algorithms=[security.ALGORITHM])
    assert payload["sub"] == "7"
    assert payload["username"] == "alice"
    assert payload["typ"] == "access"
    assert "exp" in payload and "jti" in payload


def test_token_signed_with_another_key_is_rejected(temp_db):
    from api import security

    forged = jwt.encode({"sub": "1", "typ": "access"}, "an-attackers-key",
                        algorithm="HS256")
    assert security.decode_access_token(forged) is None


def test_expired_access_token_is_rejected(temp_db):
    from api import security

    expired = jwt.encode(
        {"sub": "1", "username": "x", "typ": "access",
         "exp": security._utcnow() - timedelta(seconds=10)},
        security.SECRET_KEY, algorithm=security.ALGORITHM)
    assert security.decode_access_token(expired) is None


def test_refresh_token_cannot_be_used_as_access_token(temp_db):
    """A token of the wrong type must not authenticate a request."""
    from api import security

    wrong_type = jwt.encode(
        {"sub": "1", "username": "x", "typ": "refresh",
         "exp": security._utcnow() + timedelta(hours=1)},
        security.SECRET_KEY, algorithm=security.ALGORITHM)
    assert security.decode_access_token(wrong_type) is None


def test_none_algorithm_is_rejected(temp_db):
    """Classic JWT attack: re-sign with alg=none and hope it is trusted."""
    from api import security

    unsigned = jwt.encode({"sub": "1", "typ": "access"}, key="", algorithm="none")
    assert security.decode_access_token(unsigned) is None


# ── Refresh rotation ──────────────────────────────────────────────────────────

def test_refresh_issues_a_new_token(client):
    register(client)
    first = client.cookies.get("apex_refresh")
    r = client.post("/auth/refresh")
    assert r.status_code == 200
    assert client.cookies.get("apex_refresh") != first, "refresh token was not rotated"


def test_refresh_keeps_the_session_alive(client):
    body = register(client)
    assert client.post("/auth/refresh").status_code == 200
    assert client.get("/auth/me").json()["username"] == body["username"]


def test_replaying_a_used_refresh_token_revokes_the_family(client):
    """
    The stolen-token case. An old refresh token presented after rotation
    means someone kept a copy, so every descendant session is revoked.
    """
    register(client)
    stolen = client.cookies.get("apex_refresh")

    assert client.post("/auth/refresh").status_code == 200   # legitimate rotation

    client.cookies.set("apex_refresh", stolen)               # attacker replays
    replay = client.post("/auth/refresh")
    assert replay.status_code == 401
    assert "reuse" in replay.json()["detail"].lower()

    # And the legitimate session is dead too — we cannot tell which party
    # is which, so both are logged out.
    from api import security
    assert security.rotate_refresh_token(stolen).ok is False


def test_refresh_without_a_cookie_is_401(client):
    assert client.post("/auth/refresh").status_code == 401


def test_logout_revokes_the_refresh_token(client):
    register(client)
    token = client.cookies.get("apex_refresh")
    client.post("/auth/logout")

    from api import security
    assert security.rotate_refresh_token(token).ok is False


def test_logout_all_revokes_every_session(temp_db, client):
    """Two independent sessions; signing out everywhere kills both."""
    from api import security

    body = register(client)
    other_token, _ = security.issue_refresh_token(body["user_id"])

    assert client.post("/auth/logout-all").status_code == 204
    assert security.rotate_refresh_token(other_token).ok is False


def test_refresh_tokens_are_stored_hashed(temp_db):
    """A database leak must not hand out live sessions."""
    import auth
    import db
    from api import security

    # A real user: refresh_tokens.user_id is a foreign key, and issuing one
    # for a non-existent account is exactly what the constraint forbids.
    uid = auth.register("hashcheck", "h@example.com", "hashcheck-pass-1")
    token, _ = security.issue_refresh_token(uid)
    with db.session() as s:
        rows = s.query(db.RefreshToken).all()
    stored = [r.token_hash for r in rows]
    assert token not in stored, "raw refresh token found in the database"
    assert any(len(h) == 64 for h in stored), "expected a sha256 hex digest"


# ── Persistence across restart ────────────────────────────────────────────────

def test_sessions_survive_a_restart(temp_db, offline):
    """
    The headline fix for this phase. The Phase 2 placeholder kept tokens in
    a process dict, so every restart logged everyone out.
    """
    from api.main import app
    from api import security

    with TestClient(app) as first:
        body = register(first)
        refresh_cookie = first.cookies.get("apex_refresh")

    # A brand new client stands in for a restarted process: no shared
    # in-memory state, only the database and the signing key.
    with TestClient(app) as second:
        second.cookies.set("apex_refresh", refresh_cookie)
        r = second.post("/auth/refresh")
        assert r.status_code == 200, "session did not survive a restart"
        assert r.json()["username"] == body["username"]


# ── CSRF ──────────────────────────────────────────────────────────────────────

def test_cookie_auth_requires_csrf_on_writes(client):
    """Cookies ride along automatically, so writes need a second factor."""
    from api import security

    register(client)
    del client.headers[security.CSRF_HEADER]

    r = client.put("/portfolio/positions",
                   json={"symbol": "AAPL", "shares": 1, "avg_cost": 1.0})
    assert r.status_code == 403
    assert "csrf" in r.json()["detail"].lower()


def test_wrong_csrf_token_is_rejected(client):
    from api import security

    register(client)
    client.headers[security.CSRF_HEADER] = "not-the-right-token"
    r = client.put("/portfolio/positions",
                   json={"symbol": "AAPL", "shares": 1, "avg_cost": 1.0})
    assert r.status_code == 403


def test_reads_do_not_require_csrf(client):
    from api import security

    register(client)
    del client.headers[security.CSRF_HEADER]
    assert client.get("/portfolio").status_code == 200


def test_bearer_clients_skip_csrf(client):
    """
    Header auth cannot be forged cross-origin, so it needs no CSRF token.
    This is what lets non-browser clients work without cookie handling.
    """
    from api import security

    body = register(client)
    fresh = TestClient(client.app)
    r = fresh.put("/portfolio/positions",
                  json={"symbol": "AAPL", "shares": 1, "avg_cost": 1.0},
                  headers={"Authorization": f"Bearer {body['access_token']}"})
    assert r.status_code == 204


# ── Configuration safety ──────────────────────────────────────────────────────

def test_production_requires_an_explicit_secret_key(monkeypatch):
    """
    Tested by calling the loader directly. Reloading the module would leave
    every importer holding a stale reference and corrupt the rest of the
    session.
    """
    import api.security as sec

    monkeypatch.delenv("APEX_SECRET_KEY", raising=False)
    monkeypatch.setattr(sec, "IS_PRODUCTION", True)
    with pytest.raises(sec.InsecureConfiguration, match="APEX_SECRET_KEY"):
        sec._load_secret_key()


def test_short_secret_key_is_rejected(monkeypatch):
    import api.security as sec

    monkeypatch.setenv("APEX_SECRET_KEY", "too-short")
    with pytest.raises(sec.InsecureConfiguration, match="at least 32"):
        sec._load_secret_key()


def test_valid_secret_key_from_env_is_used(monkeypatch):
    import api.security as sec

    key = "k" * 48
    monkeypatch.setenv("APEX_SECRET_KEY", key)
    assert sec._load_secret_key() == key


def test_health_flags_insecure_production_config(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert "auth" in body and "warnings" in body
