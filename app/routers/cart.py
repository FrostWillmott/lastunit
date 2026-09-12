from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.db import get_db
from app.deps import current_user, get_broadcaster, get_clock
from app.models.order import Order
from app.models.user import User
from app.realtime import Broadcaster
from app.routers.orders import OrderResponse
from app.services import cart, orders as orders_service

router = APIRouter(tags=["cart"])


class CartItemResponse(BaseModel):
    reservation_id: int
    sale_id: int
    title: str
    price_minor: int
    expires_at: datetime


class CartResponse(BaseModel):
    server_now: datetime
    items: list[CartItemResponse]


@router.delete("/reservations/{reservation_id}", status_code=204)
async def release(
    reservation_id: int,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    broadcaster: Broadcaster = Depends(get_broadcaster),
    user: User = Depends(current_user),
) -> Response:
    try:
        await cart.release(
            db, reservation_id, user.id, await clock.now(db), broadcaster
        )
    except cart.ReservationNotFoundError:
        raise HTTPException(status_code=404, detail="reservation not found") from None
    except cart.NotHeldError:
        raise HTTPException(status_code=409, detail="reservation is not held") from None
    return Response(status_code=204)


@router.get("/me/cart", response_model=CartResponse)
async def view_cart(
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    user: User = Depends(current_user),
) -> CartResponse:
    now = await clock.now(db)
    items = await cart.list_cart(db, user.id, now)
    return CartResponse(
        server_now=now,
        items=[
            CartItemResponse(
                reservation_id=reservation.id,
                sale_id=sale.id,
                title=sale.title,
                price_minor=sale.price_minor,
                expires_at=reservation.expires_at,
            )
            for reservation, sale in items
        ],
    )


@router.get("/me/orders", response_model=list[OrderResponse])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(current_user),
) -> list[Order]:
    return await orders_service.list_user_orders(db, user.id)
