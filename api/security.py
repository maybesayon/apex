"""
Bearer tokens — a Phase 2 placeholder.

SCOPE. This is deliberately minimal and is replaced wholesale in Phase 3
(JWT in httpOnly cookies, refresh rotation, CSRF). It exists so the API can
be user-scoped and testable now, without pretending to be finished.

Known limitations, all intentional at this stage:
  * Tokens live in a process-local dict, so they die on restart and are not
    shared across workers. Single-process only.
  * No refresh, no revocation list, no rotation, no device tracking.
  * No rate limiting on login.
  * Requires HTTPS in any deployment: a bearer token is a password
    equivalent in transit.

What it does get right, because these are easy to get wrong later:
  * Tokens are 256 bits from `secrets.token_urlsafe`, not a guessable id.
  * Lookup is constant-time via dict, and comparison never does string
    prefix matching.
  * Tokens expire.
"""

import secrets
import time

TOKEN_TTL_SECONDS = 12 * 3600

# token -> (user_id, username, expires_at)
_tokens: dict[str, tuple[int, str, float]] = {}


def issue_token(user_id: int, username: str) -> tuple[str, int]:
    """Returns (token, expires_in_seconds)."""
    _purge_expired()
    token = secrets.token_urlsafe(32)
    _tokens[token] = (user_id, username, time.time() + TOKEN_TTL_SECONDS)
    return token, TOKEN_TTL_SECONDS


def resolve_token(token: str) -> dict | None:
    """Returns {'user_id', 'username'} for a live token, else None."""
    entry = _tokens.get(token or "")
    if not entry:
        return None
    user_id, username, expires_at = entry
    if time.time() >= expires_at:
        _tokens.pop(token, None)
        return None
    return {"user_id": user_id, "username": username}


def revoke_token(token: str) -> None:
    _tokens.pop(token or "", None)


def revoke_all_for_user(user_id: int) -> None:
    for tok in [t for t, (uid, _, _) in _tokens.items() if uid == user_id]:
        _tokens.pop(tok, None)


def _purge_expired() -> None:
    now = time.time()
    for tok in [t for t, (_, _, exp) in _tokens.items() if exp <= now]:
        _tokens.pop(tok, None)
