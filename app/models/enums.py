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


# Value tuples so the CHECK constraints and partial-index predicates in the
# models are derived from these enums (single source of truth) rather than
# hand-copied string literals that can drift.
USER_ROLE_VALUES = tuple(r.value for r in UserRole)
SALE_STATUS_VALUES = tuple(s.value for s in SaleStatus)
RESERVATION_STATUS_VALUES = tuple(s.value for s in ReservationStatus)
ORDER_STATUS_VALUES = tuple(s.value for s in OrderStatus)
PAYMENT_STATUS_VALUES = tuple(s.value for s in PaymentStatus)

ACTIVE_RESERVATION_VALUES = (
    ReservationStatus.HELD.value,
    ReservationStatus.PAYING.value,
)
PENDING_PAYMENT_VALUE = PaymentStatus.PENDING.value


def sql_in_list(values: tuple[str, ...]) -> str:
    """Render values as the body of a SQL ``IN (...)`` list, e.g. ``'a', 'b'``."""
    return ", ".join(repr(v) for v in values)


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
