from __future__ import annotations

import logging

import pytest

from app import email_stub
from app.main import create_app


def test_email_stub_logs_to_caplog(caplog: pytest.LogCaptureFixture) -> None:
    # create_app wires the root handler and sets the ``app`` logger to LOG_LEVEL,
    # so a stub send is observable (under uvicorn it would otherwise fall through
    # to Python's WARNING-only ``lastResort`` handler).
    create_app()
    with caplog.at_level(logging.INFO, logger="app.email_stub"):
        email_stub.send_email("buyer@example.com", "order_paid", "{}")
    assert "email to buyer@example.com" in caplog.text
