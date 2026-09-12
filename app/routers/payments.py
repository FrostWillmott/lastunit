from __future__ import annotations

import hashlib
import hmac
from typing import Literal

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.config import Settings
from app.db import get_db
from app.deps import current_user, get_broadcaster, get_clock, get_paystub, get_settings
from app.models.user import User
from app.paystub_client import PaystubClient
from app.realtime import Broadcaster
from app.services import payments as payments_service

router = APIRouter(tags=["payments"])


class PayRequest(BaseModel):
    card_number: str


class PayResponse(BaseModel):
    status: str  # "approved" | "declined" | "pending"


class WebhookPayload(BaseModel):
    reference: str
    status: Literal["approved", "declined"]


@router.post("/orders/{order_id}/pay", response_model=PayResponse)
async def pay(  # noqa: PLR0913  (FastAPI endpoint: path + body + 6 injected dependencies)
    order_id: int,
    body: PayRequest,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    user: User = Depends(current_user),
    paystub: PaystubClient = Depends(get_paystub),
    broadcaster: Broadcaster = Depends(get_broadcaster),
) -> PayResponse:
    now = await clock.now(db)
    try:
        provider_ref, amount_minor = await payments_service.start_payment(
            db, order_id, user.id, now
        )
    except payments_service.OrderNotFoundError:
        raise HTTPException(status_code=404, detail="order not found") from None
    except payments_service.HoldExpiredError:
        raise HTTPException(status_code=409, detail="hold has expired") from None
    except payments_service.PaymentAlreadyPendingError:
        raise HTTPException(
            status_code=409, detail="payment already in progress"
        ) from None
    except payments_service.ReservationNotHeldError:
        raise HTTPException(status_code=409, detail="reservation is not held") from None

    callback_url = f"{settings.public_base_url}/api/payments/webhook"
    try:
        outcome = await paystub.charge(
            provider_ref, amount_minor, body.card_number, callback_url
        )
    except httpx.HTTPError:
        # A timeout or connection failure leaves the attempt pending: the payment
        # row is already committed, so the stub may still settle it later.
        outcome = "pending"
    if outcome in ("approved", "declined"):
        await payments_service.apply_payment_result(
            db, provider_ref, outcome, await clock.now(db), broadcaster
        )
    return PayResponse(status=outcome)


@router.post("/payments/webhook")
async def webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
    broadcaster: Broadcaster = Depends(get_broadcaster),
) -> dict[str, bool]:
    body = await request.body()
    signature = request.headers.get("X-Webhook-Signature", "")
    expected = hmac.new(
        settings.paystub_webhook_secret.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=401, detail="invalid signature")
    try:
        payload = WebhookPayload.model_validate_json(body)
    except ValidationError:
        raise HTTPException(status_code=400, detail="invalid webhook payload") from None
    await payments_service.apply_payment_result(
        db, payload.reference, payload.status, await clock.now(db), broadcaster
    )
    return {"ok": True}
