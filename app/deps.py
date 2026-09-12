from __future__ import annotations

from typing import cast

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.config import Settings
from app.db import get_db
from app.models.enums import UserRole
from app.models.user import User
from app.paystub_client import PaystubClient
from app.realtime import Broadcaster
from app.services import auth

SESSION_COOKIE = "session"


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_clock(request: Request) -> Clock:
    return cast(Clock, request.app.state.clock)


def get_broadcaster(request: Request) -> Broadcaster:
    return cast(Broadcaster, request.app.state.broadcaster)


def get_paystub(request: Request) -> PaystubClient:
    return cast(PaystubClient, request.app.state.paystub)


async def current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if token is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    user = await auth.user_for_token(db, token, await clock.now(db))
    if user is None:
        raise HTTPException(status_code=401, detail="session expired")
    return user


async def require_shop(user: User = Depends(current_user)) -> User:
    if user.role != UserRole.SHOP.value:
        raise HTTPException(status_code=403, detail="shop role required")
    return user
