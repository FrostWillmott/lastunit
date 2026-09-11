from __future__ import annotations

from typing import Protocol

import httpx


class PaystubClient(Protocol):
    async def charge(
        self,
        reference: str,
        amount_minor: int,
        card_number: str,
        callback_url: str,
    ) -> str:
        """Return the stub's outcome: 'approved' | 'declined' | 'pending'."""

    async def get_status(self, reference: str) -> str:
        """Return a payment's current status (for the shop's check-status button)."""


class HttpPaystubClient:
    def __init__(
        self, base_url: str, http_client: httpx.AsyncClient | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._http_client = http_client or httpx.AsyncClient()

    async def charge(
        self,
        reference: str,
        amount_minor: int,
        card_number: str,
        callback_url: str,
    ) -> str:
        response = await self._http_client.post(
            f"{self._base_url}/payments",
            json={
                "reference": reference,
                "amount_minor": amount_minor,
                "card_number": card_number,
                "callback_url": callback_url,
            },
        )
        response.raise_for_status()
        return str(response.json()["status"])

    async def get_status(self, reference: str) -> str:
        response = await self._http_client.get(f"{self._base_url}/payments/{reference}")
        response.raise_for_status()
        return str(response.json()["status"])
