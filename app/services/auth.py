from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta

from pwdlib import PasswordHash
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import UserRole
from app.models.user import User, UserSession

_password_hash = PasswordHash.recommended()  # argon2id


class EmailTakenError(Exception):
    """Registration attempted with an email that is already registered."""


class InvalidCredentialsError(Exception):
    """Login attempted with an unknown email or a wrong password."""


def hash_password(password: str) -> str:
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _password_hash.verify(password, password_hash)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def register(db: AsyncSession, email: str, password: str) -> User:
    existing = await db.scalar(select(User).where(User.email == email))
    if existing is not None:
        raise EmailTakenError
    user = User(
        email=email,
        password_hash=hash_password(password),
        role=UserRole.BUYER.value,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise EmailTakenError from None
    return user


async def ensure_user(
    db: AsyncSession,
    email: str,
    password: str,
    role: str,
) -> None:
    """Create or reconcile a user by email (atomic, idempotent, lowercases).

    Used by the seed: an existing row's role and password_hash are updated, so a
    buyer who registered the shop email first is upgraded, and a capitalized or
    whitespace-padded email is normalized to satisfy ``CHECK (email = lower(email))``.
    """
    normalized = email.strip().lower()
    statement = pg_insert(User).values(
        email=normalized,
        password_hash=hash_password(password),
        role=role,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[User.email],
        set_={
            "password_hash": statement.excluded.password_hash,
            "role": statement.excluded.role,
        },
    )
    await db.execute(statement)
    await db.commit()


async def login(
    db: AsyncSession,
    email: str,
    password: str,
    now: datetime,
    ttl: timedelta,
) -> tuple[str, User]:
    user = await db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError
    token = new_session_token()
    db.add(
        UserSession(
            token_hash=_token_hash(token),
            user_id=user.id,
            expires_at=now + ttl,
        )
    )
    await db.commit()
    return token, user


async def user_for_token(db: AsyncSession, token: str, now: datetime) -> User | None:
    result = await db.execute(
        select(User)
        .join(UserSession, UserSession.user_id == User.id)
        .where(
            UserSession.token_hash == _token_hash(token),
            UserSession.expires_at > now,
        )
    )
    return result.scalar_one_or_none()


async def logout(db: AsyncSession, token: str) -> None:
    session = await db.scalar(
        select(UserSession).where(UserSession.token_hash == _token_hash(token))
    )
    if session is not None:
        await db.delete(session)
        await db.commit()
