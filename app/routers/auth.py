from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.clock import Clock
from app.config import Settings
from app.db import get_db
from app.deps import SESSION_COOKIE, current_user, get_clock, get_settings
from app.models.user import User
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class CredentialsRequest(BaseModel):
    email: EmailStr
    password: str

    @field_validator("email", mode="before")
    @classmethod
    def _normalize_email(cls, value: str) -> str:
        return value.strip().lower()


class RegisterRequest(CredentialsRequest):
    # Minimum length applies only at registration: a too-short password on
    # login must 401 like any wrong credential, not fail schema validation.
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    id: int
    email: str
    role: str


@router.post("/register", status_code=201, response_model=UserResponse)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    try:
        user = await auth.register(db, body.email, body.password)
    except auth.EmailTakenError:
        raise HTTPException(
            status_code=409, detail="email already registered"
        ) from None
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/login", response_model=UserResponse)
async def login(
    body: CredentialsRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    clock: Clock = Depends(get_clock),
    settings: Settings = Depends(get_settings),
) -> UserResponse:
    ttl = timedelta(days=settings.session_ttl_days)
    try:
        token, user = await auth.login(
            db, body.email, body.password, await clock.now(db), ttl
        )
    except auth.InvalidCredentialsError:
        raise HTTPException(
            status_code=401, detail="invalid email or password"
        ) from None
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(ttl.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=settings.app_env != "dev",
    )
    return UserResponse(id=user.id, email=user.email, role=user.role)


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    token = request.cookies.get(SESSION_COOKIE)
    if token is not None:
        await auth.logout(db, token)
    response = Response(status_code=204)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(current_user)) -> UserResponse:
    return UserResponse(id=user.id, email=user.email, role=user.role)
