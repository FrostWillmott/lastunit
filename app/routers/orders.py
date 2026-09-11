from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.db import get_db
from app.deps import current_user, get_clock
from app.models.user import User
from app.services import orders as orders_service

router = APIRouter(prefix="/orders", tags=["orders"])


class OrderCreateRequest(BaseModel):
    reservation_id: int


class OrderResponse(BaseModel):
    id: int
    reservation_id: int
    sale_id: int
    amount_minor: int
    status: str


@router.post("", status_code=201, response_model=OrderResponse)
async def create_order(
    body: OrderCreateRequest,
    idempotency_key: str = Header(alias="Idempotency-Key", max_length=64),
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(current_user),
) -> OrderResponse:
    try:
        order = await orders_service.create_order(
            db, body.reservation_id, user.id, idempotency_key, await clock.now()
        )
    except orders_service.ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="reservation not found") from None
    except orders_service.ReservationNotHeldError:
        raise HTTPException(status_code=409, detail="reservation is not held") from None
    except orders_service.ReservationAlreadyOrderedError:
        raise HTTPException(
            status_code=409, detail="reservation already has an order"
        ) from None
    return OrderResponse(
        id=order.id,
        reservation_id=order.reservation_id,
        sale_id=order.sale_id,
        amount_minor=order.amount_minor,
        status=order.status,
    )
