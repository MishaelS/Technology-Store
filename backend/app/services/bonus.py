"""Bonus system: every balance change goes through add_bonus and is logged in the history."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.i18n import t
from app.models import BonusHistory, User


def add_bonus(db: Session, user: User, amount: int, reason: str, order_id: int | None = None) -> None:
    """amount > 0 credits, amount < 0 debits. The caller commits."""
    if amount == 0:
        return
    if user.bonus_balance + amount < 0:
        raise HTTPException(400, t("errors.bonus_insufficient", balance=user.bonus_balance))
    user.bonus_balance += amount
    db.add(BonusHistory(user_id=user.id, amount=amount, reason=reason, order_id=order_id))


def max_bonus_for(subtotal: int, balance: int) -> int:
    """How many bonus points can be spent: no more than the balance and no more than 30% of the total."""
    return min(balance, subtotal * settings.max_bonus_percent // 100)


def cashback_for(total: int) -> int:
    return total * settings.cashback_percent // 100
