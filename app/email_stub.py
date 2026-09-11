from __future__ import annotations

import logging

logger = logging.getLogger("app.email_stub")


def send_email(recipient: str, subject: str, body: str) -> None:
    """Stub that logs the email instead of actually sending it."""
    logger.info("email to %s — %s: %s", recipient, subject, body)
