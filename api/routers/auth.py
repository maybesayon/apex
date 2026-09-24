"""Account creation and sign-in."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

import auth as auth_engine
import db
from api import security
from api.deps import CurrentUser
from api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["auth"])
_bearer = HTTPBearer(auto_error=False)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest):
    error = auth_engine.validate_signup(
        body.username, body.email or "", body.password, body.password
    )
    if error:
        # A taken username is a conflict, not malformed input — the client
        # should prompt for a different name, not report a validation bug.
        taken = "already taken" in error.lower()
        raise HTTPException(
            status.HTTP_409_CONFLICT if taken else status.HTTP_400_BAD_REQUEST,
            error,
        )
    try:
        user_id = auth_engine.register(body.username, body.email or "", body.password)
    except Exception:
        # Most likely a race on the unique constraint. Do not echo the
        # database error back to the client.
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is already taken.")

    token, ttl = security.issue_token(user_id, body.username)
    return TokenResponse(access_token=token, expires_in=ttl, username=body.username)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest):
    user = auth_engine.authenticate(body.username, body.password)
    if not user:
        # Deliberately identical for unknown user and wrong password, so the
        # response cannot be used to enumerate accounts.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect username or password.")
    token, ttl = security.issue_token(user["id"], user["username"])
    return TokenResponse(access_token=token, expires_in=ttl, username=user["username"])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)):
    if creds:
        security.revoke_token(creds.credentials)


@router.get("/me", response_model=UserResponse)
def me(user: CurrentUser):
    return UserResponse(user_id=user["user_id"], username=user["username"])
