from __future__ import annotations

from enum import StrEnum


class UserRole(StrEnum):
    BUYER = "buyer"
    SHOP = "shop"


class SaleStatus(StrEnum):
    ACTIVE = "active"
    ENDED = "ended"


class ReservationStatus(StrEnum):
    HELD = "held"
    PAYING = "paying"
    SOLD = "sold"
    EXPIRED = "expired"
    RELEASED = "released"
    CLEARED = "cleared"


class OrderStatus(StrEnum):
    PENDING = "pending"
    PAID = "paid"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"


# State machine — the single source of truth for which transitions are valid.
# Services enforce these as guarded ``UPDATE ... WHERE status = <from>`` (zero
# rows → 409 or no-op), never by a Python check; see docs/plan.md "Машины
# состояний".
RESERVATION_TRANSITIONS: dict[ReservationStatus, frozenset[ReservationStatus]] = {
    ReservationStatus.HELD: frozenset(
        {
            ReservationStatus.PAYING,
            ReservationStatus.EXPIRED,
            ReservationStatus.RELEASED,
            ReservationStatus.CLEARED,
        }
    ),
    ReservationStatus.PAYING: frozenset(
        {
            ReservationStatus.SOLD,
            ReservationStatus.HELD,
            ReservationStatus.CLEARED,
        }
    ),
}

ORDER_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset({OrderStatus.PAID, OrderStatus.CANCELLED}),
}

PAYMENT_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.APPROVED, PaymentStatus.DECLINED}),
}

SALE_TRANSITIONS: dict[SaleStatus, frozenset[SaleStatus]] = {
    SaleStatus.ACTIVE: frozenset({SaleStatus.ENDED}),
}
