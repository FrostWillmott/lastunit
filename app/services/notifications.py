from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import email_stub
from app.models.notification import Notification

ORDER_PAID = "order_paid"
CART_CLEARED = "cart_cleared"


async def enqueue_order_paid(
    db: AsyncSession,
    order_id: int,
    recipient: str,
    amount_minor: int,
) -> None:
    """Add the order-paid email to the outbox (call inside the payment's transaction)."""
    db.add(
        Notification(
            kind=ORDER_PAID,
            entity_id=order_id,
            recipient=recipient,
            payload={"amount_minor": amount_minor},
        )
    )


async def enqueue_cart_cleared(
    db: AsyncSession,
    reservation_id: int,
    recipient: str,
) -> None:
    """Add the cart-cleared notice to the outbox (call inside the cleanup transaction)."""
    db.add(
        Notification(
            kind=CART_CLEARED,
            entity_id=reservation_id,
            recipient=recipient,
            payload={},
        )
    )


async def send_pending(db: AsyncSession, now: datetime) -> int:
    """Send every unsent notification via the stub and mark it sent."""
    result = await db.execute(
        select(Notification)
        .where(Notification.sent_at.is_(None))
        .with_for_update(skip_locked=True)
    )
    pending = list(result.scalars().all())
    for notification in pending:
        email_stub.send_email(
            notification.recipient,
            notification.kind,
            json.dumps(notification.payload),
        )
        notification.sent_at = now
    await db.commit()
    return len(pending)
