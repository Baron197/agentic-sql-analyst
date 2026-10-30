"""POST /api/auth/login, POST /api/auth/logout, GET /api/me."""

from fastapi import APIRouter, Request, Response

from sql_analyst.api.auth import (
    CurrentUser,
    Res,
    clear_session_cookie,
    issue_token,
    set_session_cookie,
    verify_password,
)
from sql_analyst.api.deps import api_error
from sql_analyst.api.models import LoginRequest, Me

router = APIRouter(prefix="/api", tags=["auth"])


def _me(user) -> Me:
    return Me(
        user_id=user.user_id,
        display_name=user.display_name,
        role=user.role,
        region_ids=user.region_ids,
    )


@router.post("/auth/login", response_model=Me)
def login(body: LoginRequest, request: Request, response: Response, res: Res) -> Me:
    """Check the password and set the session cookie. 5 failures per minute per email."""
    email = body.email.strip().lower()
    if res.login_limiter.blocked(email):
        raise api_error(
            429,
            "too_many_attempts",
            "Too many failed sign-in attempts. Wait a minute and try again.",
            {"Retry-After": str(res.login_limiter.retry_after_s(email))},
        )
    user = res.store.user(email)
    if not verify_password(user, body.password):
        res.login_limiter.hit(email)
        raise api_error(401, "bad_credentials", "Wrong email or password.")
    assert user is not None
    request.state.user_id = user.user_id
    set_session_cookie(response, issue_token(user.user_id, res), res)
    return _me(user)


@router.post("/auth/logout", status_code=204)
def logout(response: Response, res: Res) -> Response:
    clear_session_cookie(response, res)
    response.status_code = 204
    return response


@router.get("/me", response_model=Me)
def me(user: CurrentUser) -> Me:
    return _me(user)
