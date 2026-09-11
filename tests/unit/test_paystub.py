from __future__ import annotations

from collections.abc import Callable

import httpx
from fastapi.testclient import TestClient

from paystub.main import create_app, deliver_with_retries, outcome_for_card


def _stub_client(handler: Callable[[httpx.Request], httpx.Response]) -> TestClient:
    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return TestClient(create_app(http_client=http_client))


def _ok(_: httpx.Request) -> httpx.Response:
    return httpx.Response(200)


def test_outcome_for_card_table() -> None:
    assert outcome_for_card("4111111111110000") == "approved"
    assert outcome_for_card("4111111111110002") == "declined"
    assert outcome_for_card("4111111111119995") == "pending"
    assert outcome_for_card("4111111111111234") == "declined"


def test_create_approved_payment_delivers_webhook() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    with _stub_client(handler) as client:
        response = client.post(
            "/payments",
            json={
                "reference": "r1",
                "amount_minor": 1000,
                "card_number": "4111111111110000",
                "callback_url": "http://backend/api/payments/webhook",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "approved"

    assert len(calls) == 1
    assert calls[0].headers["X-Webhook-Signature"]


def test_create_pending_payment_sends_no_webhook() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    with _stub_client(handler) as client:
        response = client.post(
            "/payments",
            json={
                "reference": "r2",
                "amount_minor": 1000,
                "card_number": "4111111111119995",
                "callback_url": "http://backend/api/payments/webhook",
            },
        )
        assert response.json()["status"] == "pending"

    assert calls == []


def test_resolve_pending_payment_delivers_webhook() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    with _stub_client(handler) as client:
        client.post(
            "/payments",
            json={
                "reference": "r3",
                "amount_minor": 1000,
                "card_number": "4111111111119995",
                "callback_url": "http://backend/api/payments/webhook",
            },
        )
        response = client.post("/payments/r3/resolve", json={"outcome": "approved"})
        assert response.json()["status"] == "approved"

        status = client.get("/payments/r3")
        assert status.json()["status"] == "approved"

    assert len(calls) == 1  # only the resolve delivered a webhook


async def test_webhook_retries_on_failure() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(500)
        return httpx.Response(200)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    await deliver_with_retries(
        client,
        "http://x",
        {"reference": "r", "status": "approved"},
        "secret",
        backoff=0,
    )
    assert attempts == 3
