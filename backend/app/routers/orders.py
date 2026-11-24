from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.i18n import t
from app.models import BonusHistory, CartItem, Order, OrderItem, Product, User
from app.permissions import has_permission
from app.schemas import BonusOut, OrderCreate, OrderOut
from app.services.bonus import add_bonus, max_bonus_for
from app.services.orders import change_status

router = APIRouter(tags=["Orders and bonuses"])


@router.post("/api/orders", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
def create_order(data: OrderCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Place an order from the cart. Bonus points can be spent (up to 30% of the total)."""
    # lock the user row so bonus points aren't spent twice on a double click
    db.refresh(user, with_for_update=True)

    # order by product_id so products are always locked in the same order (no deadlocks)
    cart = db.scalars(select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.product_id)).all()
    if not cart:
        raise HTTPException(400, t("errors.cart_empty"))

    items: list[OrderItem] = []
    subtotal = 0
    for ci in cart:
        product = db.get(Product, ci.product_id, with_for_update=True, populate_existing=True)
        if product is None or not product.is_active:
            raise HTTPException(400, t("errors.product_unavailable", id=ci.product_id))
        if ci.quantity > product.stock:
            raise HTTPException(400, t("errors.not_enough_stock", name=product.name, stock=product.stock))
        product.stock -= ci.quantity
        subtotal += product.price * ci.quantity
        items.append(
            OrderItem(product_id=product.id, product_name=product.name, quantity=ci.quantity, price=product.price)
        )

    max_bonus = max_bonus_for(subtotal, user.bonus_balance)
    if data.bonus_to_use > max_bonus:
        raise HTTPException(400, t("errors.bonus_limit", max=max_bonus))

    order = Order(
        user_id=user.id,
        status="new",
        subtotal=subtotal,
        bonus_used=data.bonus_to_use,
        total=subtotal - data.bonus_to_use,
        address=data.address.strip(),
        phone=data.phone.strip(),
        comment=data.comment.strip(),
        items=items,
    )
    db.add(order)
    db.flush()
    add_bonus(db, user, -data.bonus_to_use, t("bonus.reason.order_payment", id=order.id), order.id)
    db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    db.commit()
    db.refresh(order)
    return order


@router.get("/api/orders/my", response_model=list[OrderOut])
def my_orders(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())).all()


def _get_order(db: Session, order_id: int, user: User) -> Order:
    order = db.get(Order, order_id)
    if order is None or (order.user_id != user.id and not has_permission(user, "orders.manage")):
        raise HTTPException(404, t("errors.order_not_found"))
    return order


@router.get("/api/orders/{order_id}", response_model=OrderOut)
def get_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _get_order(db, order_id, user)


@router.post("/api/orders/{order_id}/cancel", response_model=OrderOut)
def cancel_order(order_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A client can cancel their own order while it is in status new."""
    order = _get_order(db, order_id, user)
    if order.user_id != user.id:
        raise HTTPException(404, t("errors.order_not_found"))
    if order.status != "new":
        raise HTTPException(400, t("errors.order_in_progress"))
    change_status(db, order, "cancelled")
    db.commit()
    return order


@router.get("/api/bonus", response_model=BonusOut)
def my_bonus(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Bonus balance and history."""
    history = db.scalars(
        select(BonusHistory).where(BonusHistory.user_id == user.id).order_by(BonusHistory.id.desc())
    ).all()
    return {"balance": user.bonus_balance, "history": history}
