"""Passwords, JWT tokens, cursors and bonus math: security.py, pagination.py, services/bonus.py."""

import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.models import Product, User
from app.pagination import decode_cursor, encode_cursor
from app.security import ALGORITHM, create_token, decode_token, hash_password, verify_password
from app.services.bonus import cashback_for, max_bonus_for


def test_password_hash_and_verify():
    hashed = hash_password("secret123")
    assert hashed != "secret123"
    assert verify_password("secret123", hashed)
    assert not verify_password("wrong", hashed)


def test_long_password_is_supported():
    long_password = "я" * 100  # 200 bytes, bcrypt only uses 72
    assert verify_password(long_password, hash_password(long_password))


def test_token_roundtrip():
    token = create_token(User(id=42, role="admin"))
    assert decode_token(token) == 42


@pytest.mark.parametrize(
    "token",
    [
        "garbage",
        jwt.encode({"sub": "1"}, "another-secret", algorithm=ALGORITHM),
        jwt.encode({"sub": "1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
                   settings.jwt_secret, algorithm=ALGORITHM),
        jwt.encode({"no_sub": 1}, settings.jwt_secret, algorithm=ALGORITHM),
    ],
)
def test_bad_tokens_give_401(token):
    with pytest.raises(HTTPException) as error:
        decode_token(token)
    assert error.value.status_code == 401


def test_cursor_roundtrip():
    columns = (Product.price, Product.id)
    assert decode_cursor(encode_cursor([1990, 7]), columns) == [1990, 7]


@pytest.mark.parametrize(
    "cursor",
    [
        "not-base64!!",
        encode_cursor([1]),               # wrong length
        encode_cursor(["text", 7]),       # wrong type for price
        encode_cursor([True, 7]),         # bool is not an int here
        base64.urlsafe_b64encode(json.dumps({"price": 1}).encode()).decode(),  # not a list
    ],
)
def test_bad_cursor_gives_400(cursor):
    with pytest.raises(HTTPException) as error:
        decode_cursor(cursor, (Product.price, Product.id))
    assert error.value.status_code == 400


@pytest.mark.parametrize(
    "subtotal, balance, expected",
    [(10_000, 500, 500), (1_000, 500, 300), (999, 10_000, 299), (0, 500, 0), (10_000, 0, 0)],
)
def test_max_bonus_is_30_percent_or_balance(subtotal, balance, expected):
    assert max_bonus_for(subtotal, balance) == expected


def test_cashback_is_5_percent_rounded_down():
    assert cashback_for(10_000) == 500
    assert cashback_for(199) == 9
