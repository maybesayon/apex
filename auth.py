# ─────────────────────────────────────────────
#  auth.py — Account creation and sign-in
#
#  Passwords are hashed with scrypt (stdlib) using a per-user random
#  salt. Plaintext passwords are never stored or logged.
#
#  SCOPE — read before deploying this publicly:
#    * No email verification, no password reset, no rate limiting or
#      lockout, and no CSRF/session-token model beyond Streamlit's
#      per-session state.
#    * Sessions live in server memory and end when the server restarts.
#    * SQLite suits a single instance, not a horizontally scaled one.
#    * Serve over HTTPS or credentials cross the wire in the clear.
#  It is a sound foundation for a private beta, not a finished
#  production identity system.
# ─────────────────────────────────────────────

import hashlib
import hmac
import os
import re

import db

# scrypt parameters. n=2**14 keeps sign-in near-instant while making
# offline brute force expensive.
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1
_DKLEN = 64

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD_LEN = 8


def _hash_password(password: str, salt: bytes) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"), salt=salt,
        n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=_DKLEN,
    ).hex()


def validate_signup(username: str, email: str, password: str, confirm: str) -> str | None:
    """Returns an error message, or None when the input is acceptable."""
    if not USERNAME_RE.match(username or ""):
        return "Username must be 3–32 characters: letters, numbers, dot, dash or underscore."
    if email and not EMAIL_RE.match(email):
        return "That email address does not look valid."
    if len(password or "") < MIN_PASSWORD_LEN:
        return f"Password must be at least {MIN_PASSWORD_LEN} characters."
    if password != confirm:
        return "The two passwords do not match."
    if db.get_user(username):
        return "That username is already taken."
    return None


def register(username: str, email: str, password: str) -> int:
    salt = os.urandom(16)
    return db.create_user(username, email, _hash_password(password, salt), salt.hex())


def authenticate(username: str, password: str) -> dict | None:
    """Returns the user record on success, None otherwise."""
    user = db.get_user(username)
    if not user:
        # Hash anyway so a missing user and a wrong password take a
        # similar amount of time, which avoids leaking who exists.
        _hash_password(password or "", os.urandom(16))
        return None

    candidate = _hash_password(password or "", bytes.fromhex(user["salt"]))
    if hmac.compare_digest(candidate, user["password_hash"]):
        return user
    return None
