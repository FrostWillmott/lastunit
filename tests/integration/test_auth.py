from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx

from app.clock import Clock, FrozenClock
from app.deps import SESSION_COOKIE
from app.main import create_app

_EMAIL = "buyer@example.com"
_PASSWORD = "secret password"


def _client(clock: Clock | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(clock=clock)),
        base_url="http://test",
    )


async def _register(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/auth/register", json={"email": _EMAIL, "password": _PASSWORD}
    )
    assert response.status_code == 201, response.text


async def test_register_returns_user_and_duplicate_is_409() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/auth/register", json={"email": _EMAIL, "password": _PASSWORD}
        )
        assert response.status_code == 201
        assert response.json()["email"] == _EMAIL
        assert response.json()["role"] == "buyer"

        # A case-variant of the same email is normalized to lowercase and
        # rejected as a duplicate.
        duplicate = await client.post(
            "/api/auth/register",
            json={"email": "Buyer@Example.com", "password": "another"},
        )
        assert duplicate.status_code == 409


async def test_login_sets_cookie_and_me_returns_user() -> None:
    async with _client() as client:
        await _register(client)
        login = await client.post(
            "/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
        )
        assert login.status_code == 200

        me = await client.get("/api/auth/me")
        assert me.status_code == 200
        assert me.json()["email"] == _EMAIL


async def test_login_rejects_wrong_password() -> None:
    async with _client() as client:
        await _register(client)
        login = await client.post(
            "/api/auth/login", json={"email": _EMAIL, "password": "wrong"}
        )
        assert login.status_code == 401


async def test_expired_session_is_rejected() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    ttl = timedelta(days=30)
    async with _client(clock=FrozenClock(start)) as client:
        await _register(client)
        login = await client.post(
            "/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
        )
        token = login.cookies.get(SESSION_COOKIE)
        assert token is not None

    # A new app whose clock is past the session's expiry rejects the token.
    async with _client(clock=FrozenClock(start + ttl + timedelta(days=1))) as client:
        me = await client.get("/api/auth/me", cookies={SESSION_COOKIE: token})
        assert me.status_code == 401


async def test_logout_clears_session() -> None:
    async with _client() as client:
        await _register(client)
        await client.post(
            "/api/auth/login", json={"email": _EMAIL, "password": _PASSWORD}
        )
        assert (await client.get("/api/auth/me")).status_code == 200

        logout = await client.post("/api/auth/logout")
        assert logout.status_code == 204
        assert (await client.get("/api/auth/me")).status_code == 401
