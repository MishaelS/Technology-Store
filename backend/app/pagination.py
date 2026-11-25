"""Pagination.

* Cursor-based (for infinite scroll): the client sends `cursor` from the previous response
  and gets the next chunk. The cursor encodes the sort values of the last record,
  so records are never duplicated or skipped, even if new rows are added meanwhile.
* Page-based (for admin tables): page + page_size.
"""

import base64
import json
import math
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Select, func, select, tuple_
from sqlalchemy.orm import Session

from app.i18n import t


def encode_cursor(values: list[Any]) -> str:
    return base64.urlsafe_b64encode(json.dumps(values).encode()).decode()


def decode_cursor(cursor: str, columns) -> list[Any]:
    try:
        values = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        if not isinstance(values, list) or len(values) != len(columns):
            raise ValueError
        for value, column in zip(values, columns):
            if not isinstance(value, column.type.python_type) or isinstance(value, bool):
                raise ValueError
        return values
    except (ValueError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, t("errors.invalid_cursor"))


def cursor_paginate(
    db: Session, stmt: Select, columns, descending: bool, cursor: str | None, limit: int
) -> tuple[list, str | None]:
    """Returns (rows, next_cursor). next_cursor=None means there are no more rows."""
    if cursor:
        values = decode_cursor(cursor, columns)
        row, last = tuple_(*columns), tuple_(*values)
        stmt = stmt.where(row < last if descending else row > last)
    stmt = stmt.order_by(*[c.desc() if descending else c.asc() for c in columns])
    rows = list(db.scalars(stmt.limit(limit + 1)).unique())
    if len(rows) <= limit:
        return rows, None
    rows = rows[:limit]
    last_row = rows[-1]
    return rows, encode_cursor([getattr(last_row, c.key) for c in columns])


def page_paginate(db: Session, stmt: Select, page: int, page_size: int) -> dict:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    items = list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique())
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, math.ceil(total / page_size)),
    }
