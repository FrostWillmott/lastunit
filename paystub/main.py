from __future__ import annotations

import asyncio
import hashlib
import hmac
import json

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings

# Card outcome table (last four digits): …0000 approved, …0002 declined,
# …9995 pending (hang). Anything else declines.
WEBHOOK_ATTEMPTS = 3
WEBHOOK_BACKOFF_SECONDS = 0.1


class Settings(BaseSettings):
    """The single place the paystub reads its environment (config-hygiene)."""

    # The empty string is a sentinel rejected below; `make env` generates the value.
    paystub_webhook_secret: str = ""

    @model_validator(mode="after")
    def _require_webhook_secret(self) -> Settings:
        if not self.paystub_webhook_secret:
            raise ValueError("PAYSTUB_WEBHOOK_SECRET must be set — run `make env`")
        return self


class PaymentCreateRequest(BaseModel):
    reference: str
    amount_minor: int
    card_number: str
    callback_url: str


class ResolveRequest(BaseModel):
    outcome: str  # "approved" | "declined"


class PaymentStatus(BaseModel):
    reference: str
    status: str


class _Payment:
    def __init__(
        self,
        reference: str,
        amount_minor: int,
        card_number: str,
        callback_url: str,
        status: str,
    ) -> None:
        self.reference = reference
        self.amount_minor = amount_minor
        self.card_number = card_number
        self.callback_url = callback_url
        self.status = status


def outcome_for_card(card_number: str) -> str:
    if card_number.endswith("0000"):
        return "approved"
    if card_number.endswith("0002"):
        return "declined"
    if card_number.endswith("9995"):
        return "pending"
    return "declined"


def _sign(payload: dict[str, str], secret: str) -> tuple[bytes, str]:
    body = json.dumps(payload).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return body, signature


async def deliver_webhook(
    http_client: httpx.AsyncClient,
    callback_url: str,
    payload: dict[str, str],
    secret: str,
) -> bool:
    """Deliver one webhook attempt; True if the callback answered 2xx/3xx."""
    body, signature = _sign(payload, secret)
    try:
        response = await http_client.post(
            callback_url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": signature,
            },
        )
        return response.status_code < 400
    except httpx.HTTPError:
        return False


async def deliver_with_retries(
    http_client: httpx.AsyncClient,
    callback_url: str,
    payload: dict[str, str],
    secret: str,
    backoff: float = WEBHOOK_BACKOFF_SECONDS,
) -> None:
    for attempt in range(WEBHOOK_ATTEMPTS):
        if await deliver_webhook(http_client, callback_url, payload, secret):
            return
        await asyncio.sleep(backoff * (attempt + 1))


def create_app(
    http_client: httpx.AsyncClient | None = None,
    webhook_secret: str | None = None,
) -> FastAPI:
    client = http_client or httpx.AsyncClient()
    secret = webhook_secret or Settings().paystub_webhook_secret
    store: dict[str, _Payment] = {}

    app = FastAPI(title="paystub")

    @app.post("/payments", response_model=PaymentStatus)
    async def create_payment(body: PaymentCreateRequest) -> PaymentStatus:
        outcome = outcome_for_card(body.card_number)
        store[body.reference] = _Payment(
            body.reference,
            body.amount_minor,
            body.card_number,
            body.callback_url,
            outcome,
        )
        if outcome != "pending":
            await deliver_with_retries(
                client,
                body.callback_url,
                {"reference": body.reference, "status": outcome},
                secret,
            )
        return PaymentStatus(reference=body.reference, status=outcome)

    @app.post("/payments/{reference}/resolve", response_model=PaymentStatus)
    async def resolve_payment(reference: str, body: ResolveRequest) -> PaymentStatus:
        payment = store.get(reference)
        if payment is None:
            raise HTTPException(status_code=404, detail="payment not found")
        payment.status = body.outcome
        await deliver_with_retries(
            client,
            payment.callback_url,
            {"reference": reference, "status": body.outcome},
            secret,
        )
        return PaymentStatus(reference=reference, status=body.outcome)

    @app.get("/payments/{reference}", response_model=PaymentStatus)
    async def get_payment(reference: str) -> PaymentStatus:
        payment = store.get(reference)
        if payment is None:
            raise HTTPException(status_code=404, detail="payment not found")
        return PaymentStatus(reference=payment.reference, status=payment.status)

    return app


# The ASGI entry point the paystub Dockerfile's uvicorn imports.
app = create_app()
