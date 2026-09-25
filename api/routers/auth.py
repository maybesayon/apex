"""Account creation, sign-in, token refresh."""

from fastapi import APIRouter, HTTPException, Request, Response, status

import auth as auth_engine
import db
from api import security
from api.deps import CurrentUser
from api.schemas import LoginRequest, RegisterRequest, SessionResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])


def _establish_session(response: Response, user_id: int, username: str) -> SessionResponse:
    access = security.create_access_token(user_id, username)
    refresh, _ = security.issue_refresh_token(user_id)
    csrf = security.new_csrf_token()
    security.set_auth_cookies(response, access, refresh, csrf)
    return SessionResponse(
        user_id=user_id,
        username=username,
        csrf_token=csrf,
        expires_in=security.ACCESS_TTL_SECONDS,
        # Returned for non-browser clients (tests, CLI, mobile). Browsers
        # should ignore it and rely on the httpOnly cookie, which page
        # JavaScript cannot read.
        access_token=access,
    )


@router.post("/register", response_model=SessionResponse,
             status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, response: Response):
    error = auth_engine.validate_signup(
        body.username, body.email or "", body.password, body.password
    )
    if error:
        taken = "already taken" in error.lower()
        raise HTTPException(
            status.HTTP_409_CONFLICT if taken else status.HTTP_400_BAD_REQUEST, error)
    try:
        user_id = auth_engine.register(body.username, body.email or "", body.password)
    except Exception:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken.")
    return _establish_session(response, user_id, body.username)


@router.post("/login", response_model=SessionResponse)
def login(body: LoginRequest, response: Response):
    user = auth_engine.authenticate(body.username, body.password)
    if not user:
        # Identical for unknown user and wrong password, so the response
        # cannot be used to enumerate accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Incorrect username or password.")
    return _establish_session(response, user["id"], user["username"])


@router.post("/refresh", response_model=SessionResponse)
def refresh(request: Request, response: Response):
    """
    Exchange the refresh cookie for a new access token, rotating the
    refresh token. Replaying an already-used token revokes the whole
    family and forces a fresh sign-in.
    """
    token = request.cookies.get(security.REFRESH_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No refresh token")

    result = security.rotate_refresh_token(token)
    if not result.ok:
        security.clear_auth_cookies(response)
        if result.reused:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Refresh token reuse detected — all sessions revoked. Sign in again.",
            )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED,
                            "Invalid or expired refresh token")

    access = security.create_access_token(result.user_id, result.username)
    csrf = security.new_csrf_token()
    security.set_auth_cookies(response, access, result.token, csrf)
    return SessionResponse(
        user_id=result.user_id, username=result.username, csrf_token=csrf,
        expires_in=security.ACCESS_TTL_SECONDS, access_token=access,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    token = request.cookies.get(security.REFRESH_COOKIE)
    if token:
        security.revoke_refresh_token(token)
    security.clear_auth_cookies(response)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(user: CurrentUser, response: Response):
    """Revoke every session for this account — the 'sign out everywhere' action."""
    security.revoke_all_for_user(user["user_id"])
    security.clear_auth_cookies(response)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return UserResponse(user_id=user["user_id"], username=user["username"])
