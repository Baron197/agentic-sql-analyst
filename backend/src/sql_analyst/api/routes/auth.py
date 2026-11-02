"""Sign-in routes: login, logout, me, and the public demo's one-click sign-in.

`POST /api/auth/demo` signs in as a seeded demo user without a password. It exists only when
DEMO_LOGIN_ENABLED=true (the public demo, Phase 8), so the demo passwords never need to be
shown on the page or shipped in the JavaScript (docs/DECISIONS.md D036).
"""

import secrets

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
from sql_analyst.api.models import AuthOptions, DemoLoginRequest, LoginRequest, Me
from sql_analyst.users import DEMO_USERS

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


@router.get("/auth/options", response_model=AuthOptions)
def auth_options(res: Res) -> AuthOptions:
    """What the sign-in page can offer: the demo accounts and whether one-click sign-in is on."""
    return AuthOptions(
        demo_login_enabled=res.settings.demo_login_enabled,
        demo_users=[
            {"key": key, "email": scope.user_id, "role": scope.role}
            for key, scope in DEMO_USERS.items()
        ],
    )


@router.post("/auth/demo", response_model=Me)
def demo_login(body: DemoLoginRequest, request: Request, response: Response, res: Res) -> Me:
    if not res.settings.demo_login_enabled:
        raise api_error(404, "not_found", "Not found.")
    user = res.store.user(DEMO_USERS[body.user].user_id)
    if user is None:
        raise api_error(503, "demo_users_missing", "The demo users are not set up.")
    request.state.user_id = user.user_id
    # Visitors share the demo account, so each sign-in gets its own history session (D048).
    token = issue_token(user.user_id, res, session_id=secrets.token_hex(16))
    set_session_cookie(response, token, res)
    return _me(user)
