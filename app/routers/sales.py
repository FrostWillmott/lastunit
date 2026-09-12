from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.db import get_db
from app.deps import current_user, get_broadcaster, get_clock, require_shop
from app.models.sale import Sale
from app.models.user import User
from app.realtime import Broadcaster
from app.services import cart, sales as sales_service
from app.services.sales import InvalidSaleWindowError, SalePhase

router = APIRouter(prefix="/sales", tags=["sales"])


class SaleCreateRequest(BaseModel):
    title: str = Field(max_length=255)
    price_minor: int = Field(ge=0)
    quantity: int = Field(ge=1)
    timezone: str
    starts_at: datetime
    ends_at: datetime

    @field_validator("timezone")
    @classmethod
    def _validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise ValueError(f"unknown timezone: {value}") from None
        return value

    @field_validator("starts_at", "ends_at")
    @classmethod
    def _require_naive(cls, value: datetime) -> datetime:
        if value.tzinfo is not None:
            raise ValueError(
                "start/end times must be naive wall-clock; the timezone field carries the zone"
            )
        return value

    @model_validator(mode="after")
    def _check_window(self) -> SaleCreateRequest:
        if self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be after starts_at")
        return self


class SaleResponse(BaseModel):
    id: int
    title: str
    price_minor: int
    quantity: int
    available: int
    starts_at: datetime
    ends_at: datetime
    timezone: str
    phase: SalePhase
    server_now: datetime


def _to_response(sale: Sale, now: datetime) -> SaleResponse:
    return SaleResponse(
        id=sale.id,
        title=sale.title,
        price_minor=sale.price_minor,
        quantity=sale.quantity,
        available=sale.available,
        starts_at=sale.starts_at,
        ends_at=sale.ends_at,
        timezone=sale.timezone,
        phase=sales_service.phase(sale.starts_at, sale.ends_at, now),
        server_now=now,
    )


@router.get("", response_model=list[SaleResponse])
async def list_sales(
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> list[SaleResponse]:
    now = await clock.now(db)
    return [_to_response(sale, now) for sale in await sales_service.list_sales(db)]


@router.get("/{sale_id}", response_model=SaleResponse)
async def get_sale(
    sale_id: int,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> SaleResponse:
    sale = await sales_service.get_sale(db, sale_id)
    if sale is None:
        raise HTTPException(status_code=404, detail="sale not found")
    return _to_response(sale, await clock.now(db))


@router.post("", status_code=201, response_model=SaleResponse)
async def create_sale(
    body: SaleCreateRequest,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    _shop: object = Depends(require_shop),
) -> SaleResponse:
    try:
        sale = await sales_service.create_sale(
            db,
            title=body.title,
            price_minor=body.price_minor,
            quantity=body.quantity,
            tz_name=body.timezone,
            starts_at_local=body.starts_at,
            ends_at_local=body.ends_at,
        )
    except InvalidSaleWindowError:
        raise HTTPException(
            status_code=422,
            detail="ends_at must be after starts_at in the sale's timezone",
        ) from None
    return _to_response(sale, await clock.now(db))


class ReservationResponse(BaseModel):
    id: int
    sale_id: int
    status: str
    expires_at: datetime


@router.post("/{sale_id}/reserve", status_code=201, response_model=ReservationResponse)
async def reserve(
    sale_id: int,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    broadcaster: Broadcaster = Depends(get_broadcaster),
    user: User = Depends(current_user),
) -> ReservationResponse:
    try:
        reservation = await cart.reserve(
            db, sale_id, user.id, await clock.now(db), broadcaster
        )
    except cart.NotStartedError:
        raise HTTPException(
            status_code=409, detail="sale has not started yet"
        ) from None
    except cart.SaleEndedError:
        raise HTTPException(status_code=409, detail="sale has ended") from None
    except cart.SoldOutError:
        raise HTTPException(status_code=409, detail="sold out") from None
    except cart.AlreadyInCartError:
        raise HTTPException(status_code=409, detail="already in cart") from None
    except cart.SaleNotFoundError:
        raise HTTPException(status_code=404, detail="sale not found") from None
    return ReservationResponse(
        id=reservation.id,
        sale_id=reservation.sale_id,
        status=reservation.status,
        expires_at=reservation.expires_at,
    )
