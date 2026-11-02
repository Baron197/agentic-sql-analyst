"""Sign-in: argon2 password hashes and a signed session token (JWT) in an httpOnly cookie.

The token carries the user id, and for a one-click demo sign-in a random session id, so
visitors who share a demo account each see only their own history (D048). Each request loads
the user's role and region scope from `app.users`, so the scope never comes from the browser.
The cookie is SameSite=Lax
and the API only accepts JSON bodies, so other sites cannot post questions as the user.
Sign-out clears the cookie; a copied token stays valid until it expires (SESSION_HOURS).
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request, Response

from sql_analyst.api.deps import Resources, api_error, resources
from sql_analyst.api.store import StoredUser

COOKIE = "sqla_session"
ALGORITHM = "HS256"
_HASHER = PasswordHasher()
# Verified when the email is unknown, so both failures take the same time.
_DUMMY_HASH = _HASHER.hash("not-a-real-password")


def verify_password(user: StoredUser | None, password: str) -> bool:
    try:
        return _HASHER.verify(user.password_hash if user else _DUMMY_HASH, password) and bool(user)
    except (VerificationError, InvalidHashError):
        return False


def issue_token(user_id: str, res: Resources, session_id: str | None = None) -> str:
    now = datetime.now(UTC)
    claims = {"sub": user_id, "iat": now, "exp": now + timedelta(hours=res.settings.session_hours)}
    if session_id:
        claims["sid"] = session_id
    return jwt.encode(claims, res.settings.jwt_key(), algorithm=ALGORITHM)


def set_session_cookie(response: Response, token: str, res: Resources) -> None:
    response.set_cookie(
        COOKIE,
        token,
        max_age=res.settings.session_hours * 3600,
        httponly=True,
        secure=res.settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response, res: Resources) -> None:
    response.delete_cookie(
        COOKIE, path="/", httponly=True, secure=res.settings.cookie_secure, samesite="lax"
    )


def current_user(request: Request, res: Annotated[Resources, Depends(resources)]) -> StoredUser:
    token = request.cookies.get(COOKIE)
    if not token:
        raise api_error(401, "not_signed_in", "Sign in first.")
    try:
        claims = jwt.decode(
            token,
            res.settings.jwt_key(),
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        raise api_error(
            401, "invalid_session", "Your session is invalid or expired. Sign in again."
        ) from None
    user = res.store.user(claims["sub"])
    if user is None:
        raise api_error(
            401, "invalid_session", "Your session is invalid or expired. Sign in again."
        )
    request.state.user_id = user.user_id
    sid = claims.get("sid")
    return user.model_copy(update={"session_id": sid}) if isinstance(sid, str) else user


CurrentUser = Annotated[StoredUser, Depends(current_user)]
Res = Annotated[Resources, Depends(resources)]
