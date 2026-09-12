from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.db import get_db
from app.deps import get_broadcaster, get_clock, get_paystub, require_shop
from app.paystub_client import PaystubClient
from app.realtime import Broadcaster
from app.services import payments as payments_service, shop as shop_service

router = APIRouter(prefix="/shop", tags=["shop"])


class PendingPaymentResponse(BaseModel):
    provider_ref: str
    order_id: int
    requested_at: datetime


class SaleStatsResponse(BaseModel):
    available: int
    sold: int
    in_cart: int
    revenue_minor: int
    pending_payments: list[PendingPaymentResponse]


@router.get(
    "/sales/{sale_id}/stats",
    response_model=SaleStatsResponse,
    dependencies=[Depends(require_shop)],
)
async def sale_stats(
    sale_id: int,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SaleStatsResponse:
    try:
        stats = await shop_service.sale_stats(db, sale_id, await clock.now(db))
    except shop_service.SaleNotFoundError:
        raise HTTPException(status_code=404, detail="sale not found") from None
    return SaleStatsResponse(
        available=stats.available,
        sold=stats.sold,
        in_cart=stats.in_cart,
        revenue_minor=stats.revenue_minor,
        pending_payments=[
            PendingPaymentResponse(
                provider_ref=payment.provider_ref,
                order_id=payment.order_id,
                requested_at=payment.requested_at,
            )
            for payment in stats.pending_payments
        ],
    )


@router.post(
    "/payments/{reference}/check",
    response_model=dict[str, str],
    dependencies=[Depends(require_shop)],
)
async def check_payment(
    reference: str,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    paystub: PaystubClient = Depends(get_paystub),
    broadcaster: Broadcaster = Depends(get_broadcaster),
) -> dict[str, str]:
    try:
        status = await paystub.get_status(reference)
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502, detail="payment stub unavailable"
        ) from None
    if status in ("approved", "declined"):
        await payments_service.apply_payment_result(
            db, reference, status, await clock.now(db), broadcaster
        )
    return {"status": status}
