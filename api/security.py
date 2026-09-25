"""
Tokens, cookies and CSRF.

Replaces the Phase 2 placeholder (an in-process dict that lost every
session on restart and could not be shared between workers).

Design:

  Access token   Short-lived JWT (15 min), stateless, HS256. Carries the
                 user id so ordinary requests need no database read.

  Refresh token  Long-lived (30 days) opaque random string. Only its
                 SHA-256 hash is stored, so a database leak does not hand
                 out live sessions. Rotated on every use.

  Reuse detection
                 Each refresh token belongs to a `family`. Presenting a
                 token that was already used means someone replayed a
                 stolen copy, so the entire family is revoked — the
                 legitimate user is logged out and has to sign in again,
                 which is the correct outcome when a token has leaked.

  Transport      httpOnly cookies, so page JavaScript cannot read them and
                 an XSS bug cannot exfiltrate a session. Because cookies
                 are sent automatically, state-changing requests also need
                 a CSRF token (double-submit). Clients that authenticate
                 with an `Authorization: Bearer` header instead are immune
                 to CSRF by construction and skip that check.
"""

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import jwt

import db

ALGORITHM = "HS256"
ACCESS_TTL_SECONDS = 15 * 60
REFRESH_TTL_SECONDS = 30 * 24 * 3600

ACCESS_COOKIE = "apex_access"
REFRESH_COOKIE = "apex_refresh"
CSRF_COOKIE = "apex_csrf"
CSRF_HEADER = "X-CSRF-Token"

APEX_ENV = os.environ.get("APEX_ENV", "development").strip().lower()
IS_PRODUCTION = APEX_ENV in {"production", "prod"}

# Cross-site cookies require SameSite=None *and* Secure, which requires
# HTTPS. Same-origin deployments (Next.js rewrites proxying /api) should
# keep Lax, which is both simpler and stricter.
COOKIE_SAMESITE = os.environ.get("APEX_COOKIE_SAMESITE", "lax").strip().lower()
COOKIE_SECURE = os.environ.get(
    "APEX_COOKIE_SECURE", "true" if IS_PRODUCTION else "false"
).strip().lower() == "true"
COOKIE_DOMAIN = os.environ.get("APEX_COOKIE_DOMAIN", "").strip() or None


class InsecureConfiguration(RuntimeError):
    pass


def _load_secret_key() -> str:
    """
    Resolve the signing key.

    In production an explicit APEX_SECRET_KEY is mandatory: a generated key
    would differ per process, so tokens would fail validation across
    workers and after every deploy.

    In development a key is generated once and persisted to a gitignored
    file, so that sessions survive a restart — which is the whole point of
    this phase — without asking anyone to configure anything to run locally.
    """
    key = os.environ.get("APEX_SECRET_KEY", "").strip()
    if key:
        if len(key) < 32:
            raise InsecureConfiguration(
                "APEX_SECRET_KEY must be at least 32 characters."
            )
        return key

    if IS_PRODUCTION:
        raise InsecureConfiguration(
            "APEX_SECRET_KEY is required when APEX_ENV=production. "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
        )

    dev_key_file = Path(__file__).resolve().parent.parent / ".apex_dev_secret"
    if dev_key_file.exists():
        return dev_key_file.read_text().strip()

    generated = secrets.token_urlsafe(48)
    dev_key_file.write_text(generated)
    try:
        dev_key_file.chmod(0o600)
    except OSError:
        pass
    print("APEX: generated a development signing key at .apex_dev_secret "
          "(gitignored). Set APEX_SECRET_KEY in production.")
    return generated


SECRET_KEY = _load_secret_key()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _hash(token: str) -> str:
    """SHA-256 is right here: the input is already 256 bits of entropy, so
    there is nothing for a slow KDF to protect against."""
    return hashlib.sha256(token.encode()).hexdigest()


# ── Access tokens ─────────────────────────────────────────────────────────────

def create_access_token(user_id: int, username: str) -> str:
    now = _utcnow()
    payload = {
        "sub": str(user_id),
        "username": username,
        "iat": now,
        "exp": now + timedelta(seconds=ACCESS_TTL_SECONDS),
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Returns {'user_id', 'username'} for a valid token, else None."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("typ") != "access":
        return None          # a refresh token must not be usable as access
    try:
        return {"user_id": int(payload["sub"]), "username": payload.get("username", "")}
    except (KeyError, TypeError, ValueError):
        return None


# ── Refresh tokens ────────────────────────────────────────────────────────────

def issue_refresh_token(user_id: int, family_id: str | None = None) -> tuple[str, str]:
    """Returns (token, family_id). The token is returned only here."""
    family_id = family_id or uuid.uuid4().hex
    token = secrets.token_urlsafe(32)
    db.store_refresh_token(user_id, _hash(token), family_id, REFRESH_TTL_SECONDS)
    return token, family_id


class RefreshResult:
    def __init__(self, user_id=None, username=None, token=None, reused=False):
        self.user_id = user_id
        self.username = username
        self.token = token
        self.reused = reused

    @property
    def ok(self) -> bool:
        return self.user_id is not None


def rotate_refresh_token(token: str) -> RefreshResult:
    """
    Exchange a refresh token for a new one.

    A replayed token (already used, or revoked) revokes its whole family:
    the attacker and the legitimate user are both logged out, which is
    correct — at that point we cannot tell which is which.
    """
    record = db.get_refresh_token(_hash(token or ""))
    if record is None:
        return RefreshResult()

    if record["revoked"] or record["used"]:
        db.revoke_token_family(record["family_id"])
        return RefreshResult(reused=True)

    if record["expires_at"] < _utcnow():
        return RefreshResult()

    user = db.get_user_by_id(record["user_id"])
    if user is None:
        return RefreshResult()

    db.mark_refresh_token_used(_hash(token))
    new_token, _ = issue_refresh_token(record["user_id"], record["family_id"])
    return RefreshResult(user_id=record["user_id"], username=user["username"],
                         token=new_token)


def revoke_refresh_token(token: str) -> None:
    record = db.get_refresh_token(_hash(token or ""))
    if record:
        db.revoke_token_family(record["family_id"])


def revoke_all_for_user(user_id: int) -> int:
    return db.revoke_all_user_tokens(user_id)


# ── CSRF ──────────────────────────────────────────────────────────────────────

def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(cookie_value: str | None, header_value: str | None) -> bool:
    """
    Double-submit check. The CSRF cookie is deliberately readable by JS so
    the client can echo it in a header; a cross-origin attacker can send
    the cookie automatically but cannot read it to set the header.
    """
    if not cookie_value or not header_value:
        return False
    return secrets.compare_digest(cookie_value, header_value)


# ── Cookie helpers ────────────────────────────────────────────────────────────

def set_auth_cookies(response, access_token: str, refresh_token: str,
                     csrf_token: str) -> None:
    common = {
        "secure": COOKIE_SECURE,
        "samesite": COOKIE_SAMESITE,
        "domain": COOKIE_DOMAIN,
        "path": "/",
    }
    response.set_cookie(ACCESS_COOKIE, access_token, httponly=True,
                        max_age=ACCESS_TTL_SECONDS, **common)
    response.set_cookie(REFRESH_COOKIE, refresh_token, httponly=True,
                        max_age=REFRESH_TTL_SECONDS, **common)
    # Not httpOnly on purpose: the client must read this to echo it back.
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False,
                        max_age=REFRESH_TTL_SECONDS, **common)


def clear_auth_cookies(response) -> None:
    for name in (ACCESS_COOKIE, REFRESH_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", domain=COOKIE_DOMAIN)


def config_report() -> dict:
    """Surfaced at /health so a misconfigured deployment is visible."""
    return {
        "env": APEX_ENV,
        "cookie_secure": COOKIE_SECURE,
        "cookie_samesite": COOKIE_SAMESITE,
        "secret_key_from_env": bool(os.environ.get("APEX_SECRET_KEY", "").strip()),
        "access_ttl_seconds": ACCESS_TTL_SECONDS,
        "refresh_ttl_seconds": REFRESH_TTL_SECONDS,
    }
