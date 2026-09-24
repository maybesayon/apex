"""Shared FastAPI dependencies."""

from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api import security

_bearer = HTTPBearer(auto_error=False, description="Token from POST /auth/login")


def current_user(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> dict:
    """
    Resolve the signed-in user, or 401.

    Every user-scoped route depends on this, so account data can only ever
    be reached through a resolved user_id — the property that replaced a
    hardcoded portfolio shown to everyone.
    """
    if creds is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = security.resolve_token(creds.credentials)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


CurrentUser = Annotated[dict, Depends(current_user)]


def resolve_ticker(symbol: str) -> str:
    """
    Normalise a path parameter into a ticker.

    Accepts a ticker or a company name, so /stocks/apple works the same as
    /stocks/AAPL. 404 rather than silently analysing the wrong company.
    """
    from symbols import resolve_symbol

    ticker = resolve_symbol(symbol)
    if not ticker:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No symbol matches {symbol!r}",
        )
    return ticker


Ticker = Annotated[str, Depends(resolve_ticker)]
