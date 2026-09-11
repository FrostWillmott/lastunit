from __future__ import annotations

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.enums import USER_ROLE_VALUES, UserRole, sql_in_list


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Emails are stored lowercase so the plain UNIQUE is case-insensitive;
        # the auth boundary lowercases on the way in.
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint(
            f"role IN ({sql_in_list(USER_ROLE_VALUES)})", name="role_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), server_default=UserRole.BUYER.value)


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
