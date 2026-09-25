"""Shared FastAPI dependencies: authentication, CSRF, symbol resolution."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api import security

_bearer = HTTPBearer(auto_error=False, description="Optional: for non-browser clients")

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """
    Resolve the signed-in user from a cookie or a bearer header.

    Cookie sessions additionally require a CSRF token on state-changing
    requests, because the browser attaches cookies automatically. Bearer
    headers cannot be set cross-origin by an attacker, so they need no
    CSRF check.
    """
    # Header first: explicit beats ambient, and it lets a cookie-bearing
    # browser act on behalf of a different client during testing.
    if creds is not None:
        user = security.decode_access_token(creds.credentials)
        if user is None:
            raise _unauthorized("Invalid or expired token")
        return user

    token = request.cookies.get(security.ACCESS_COOKIE)
    if not token:
        raise _unauthorized("Not authenticated")

    user = security.decode_access_token(token)
    if user is None:
        # Expired access token: the client should call /auth/refresh. A
        # distinct code stops it retrying the original request forever.
        raise _unauthorized("Session expired", code="token_expired")

    if request.method in UNSAFE_METHODS:
        if not security.csrf_ok(
            request.cookies.get(security.CSRF_COOKIE),
            request.headers.get(security.CSRF_HEADER),
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(f"Missing or invalid {security.CSRF_HEADER}. Echo the "
                        f"{security.CSRF_COOKIE} cookie in that header."),
            )
    return user


def _unauthorized(detail: str, code: str | None = None) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"}
    if code:
        headers["X-Auth-Error"] = code
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                         detail=detail, headers=headers)


CurrentUser = Annotated[dict, Depends(current_user)]


def resolve_ticker(symbol: str) -> str:
    """
    Normalise a path parameter into a ticker, so /stocks/apple works the
    same as /stocks/AAPL. 404 rather than silently analysing the wrong
    company.
    """
    from symbols import resolve_symbol

    ticker = resolve_symbol(symbol)
    if not ticker:
        raise HTTPException(status.HTTP_404_NOT_FOUND,
                            f"No symbol matches {symbol!r}")
    return ticker


Ticker = Annotated[str, Depends(resolve_ticker)]
