from __future__ import annotations

from app.services.auth import hash_password, new_session_token, verify_password


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("correct horse battery staple")
    assert hashed != "correct horse battery staple"
    assert verify_password("correct horse battery staple", hashed)


def test_verify_password_rejects_wrong_password() -> None:
    hashed = hash_password("correct")
    assert not verify_password("wrong", hashed)


def test_session_tokens_are_unique_and_long() -> None:
    first = new_session_token()
    second = new_session_token()
    assert first != second
    assert len(first) >= 32
