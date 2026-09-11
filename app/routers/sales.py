from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.db import get_db
from app.deps import get_clock, require_shop
from app.models.sale import Sale
from app.services import sales as sales_service
from app.services.sales import SalePhase

router = APIRouter(prefix="/sales", tags=["sales"])


class SaleCreateRequest(BaseModel):
    title: str
    price_minor: int
    quantity: int
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
    now = await clock.now()
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
    return _to_response(sale, await clock.now())


@router.post("", status_code=201, response_model=SaleResponse)
async def create_sale(
    body: SaleCreateRequest,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    _shop: object = Depends(require_shop),
) -> SaleResponse:
    sale = await sales_service.create_sale(
        db,
        title=body.title,
        price_minor=body.price_minor,
        quantity=body.quantity,
        tz_name=body.timezone,
        starts_at_local=body.starts_at,
        ends_at_local=body.ends_at,
    )
    return _to_response(sale, await clock.now())
