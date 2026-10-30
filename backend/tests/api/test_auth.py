"""Sign-in is required, wrong passwords are rejected, and sessions can't be forged."""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from argon2 import PasswordHasher

from backend.tests.api.conftest import ANALYST, MANAGER, password, sign_in
from sql_analyst.api.auth import COOKIE
from sql_analyst.config import get_settings

pytestmark = pytest.mark.db

PROTECTED = [
    ("GET", "/api/me"),
    ("POST", "/api/ask"),
    ("POST", "/api/ask/stream"),
    ("GET", "/api/runs"),
    ("GET", "/api/runs/abc"),
    ("GET", "/api/schema"),
    ("GET", "/api/examples"),
    ("GET", "/api/metrics"),
]


@pytest.mark.parametrize(("method", "path"), PROTECTED)
def test_every_route_but_health_and_login_needs_a_session(client, method, path):
    r = client.request(method, path, json={"question": "How many orders?"})
    assert r.status_code == 401 and r.json()["detail"]["code"] == "not_signed_in"


def test_health_and_docs_are_public(client):
    assert client.get("/api/health").json()["status"] == "ok"
    assert client.get("/api/openapi.json").status_code == 200


def test_wrong_password_and_unknown_email_get_the_same_answer(client):
    wrong = client.post("/api/auth/login", json={"email": ANALYST, "password": "not-it"})
    unknown = client.post("/api/auth/login", json={"email": "nobody@demo", "password": "not-it"})
    assert wrong.status_code == unknown.status_code == 401
    assert (
        wrong.json()
        == unknown.json()
        == {"detail": {"code": "bad_credentials", "message": "Wrong email or password."}}
    )
    assert COOKIE not in client.cookies


def test_login_sets_an_httponly_samesite_cookie_and_me_returns_the_scope(client):
    r = client.post(
        "/api/auth/login", json={"email": MANAGER.upper(), "password": password(MANAGER)}
    )
    cookie = r.headers["set-cookie"].lower()
    assert r.status_code == 200 and "httponly" in cookie and "samesite=lax" in cookie
    assert "max-age=28800" in cookie
    me = client.get("/api/me").json()
    assert me == {
        "user_id": MANAGER,
        "display_name": "Demo manager (Jakarta)",
        "role": "manager",
        "region_ids": [1, 2, 3, 4, 5],
    }


def test_logout_clears_the_cookie(client):
    sign_in(client)
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/me").status_code == 401


def test_repeated_failures_lock_the_email_for_a_minute(client):
    for _ in range(5):
        assert (
            client.post("/api/auth/login", json={"email": ANALYST, "password": "x"}).status_code
            == 401
        )
    r = client.post("/api/auth/login", json={"email": ANALYST, "password": password(ANALYST)})
    assert r.status_code == 429 and r.json()["detail"]["code"] == "too_many_attempts"
    assert int(r.headers["Retry-After"]) > 0
    sign_in(client, MANAGER)  # other accounts are not affected


def _token(sub: str, key: str, hours: float = 1) -> str:
    now = datetime.now(UTC)
    return jwt.encode({"sub": sub, "iat": now, "exp": now + timedelta(hours=hours)}, key, "HS256")


@pytest.mark.parametrize(
    "token",
    [
        _token(MANAGER, "a-different-secret-that-is-long-enough-123"),  # forged signature
        _token(MANAGER, get_settings().jwt_key(), hours=-1),  # expired
        _token("intruder@demo", get_settings().jwt_key()),  # validly signed, unknown user
        jwt.encode({"sub": MANAGER}, get_settings().jwt_key(), "HS256"),  # no expiry
        "not-a-token",
    ],
    ids=["forged", "expired", "unknown-user", "no-exp", "garbage"],
)
def test_forged_expired_or_foreign_tokens_are_rejected(client, token):
    client.cookies.set(COOKIE, token)
    assert client.get("/api/me").status_code == 401


def test_passwords_are_stored_as_argon2id_hashes(resources):
    user = resources.store.user(ANALYST)
    assert user.password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(user.password_hash, password(ANALYST))
