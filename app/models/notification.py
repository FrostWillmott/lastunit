from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # One letter per (kind, entity) — the outbox is the dedupe, not a flag.
        UniqueConstraint("kind", "entity_id", name="uq_notifications_kind_entity"),
        # The sender loop's only hot query is `WHERE sent_at IS NULL`.
        Index(
            "ix_notifications_unsent",
            "id",
            postgresql_where=text("sent_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(32))
    entity_id: Mapped[int] = mapped_column(Integer)
    recipient: Mapped[str] = mapped_column(String(255))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
