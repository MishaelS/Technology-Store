"""Order status changes: return stock and bonuses on cancel, cashback on completion."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.i18n import t
from app.models import Order, Product
from app.services.bonus import add_bonus, cashback_for

# Allowed transitions: status -> next statuses
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "new": ("confirmed", "cancelled"),
    "confirmed": ("assembling", "cancelled"),
    "assembling": ("shipped", "cancelled"),
    "shipped": ("done",),
    "done": (),
    "cancelled": (),
}


def change_status(db: Session, order: Order, new_status: str) -> None:
    if new_status not in TRANSITIONS[order.status]:
        status_name = lambda s: t(f"orders.status.{s}")  # noqa: E731
        allowed = ", ".join(map(status_name, TRANSITIONS[order.status])) or t("errors.status_none")
        raise HTTPException(
            400,
            t("errors.status_transition", from_status=status_name(order.status),
              to_status=status_name(new_status), allowed=allowed),
        )

    # lock the user row so the bonus balance isn't changed concurrently
    db.refresh(order.user, with_for_update=True)

    if new_status == "cancelled":
        # return items to stock
        for item in order.items:
            product = db.get(Product, item.product_id, with_for_update=True)
            if product:
                product.stock += item.quantity
        # refund spent bonus points
        add_bonus(db, order.user, order.bonus_used, t("bonus.reason.order_refund", id=order.id), order.id)

    if new_status == "done":
        earned = cashback_for(order.total)
        order.bonus_earned = earned
        add_bonus(db, order.user, earned, t("bonus.reason.order_cashback", id=order.id), order.id)

    order.status = new_status
