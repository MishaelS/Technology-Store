from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.i18n import t
from app.models import CartItem, Product, User
from app.schemas import CartAdd, CartAddMany, CartOut, CartSet
from app.services.bonus import max_bonus_for

router = APIRouter(prefix="/api/cart", tags=["Cart"])


def _active_product(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(404, t("errors.product_id_not_found", id=product_id))
    return product


def _check_stock(product: Product, quantity: int) -> None:
    if quantity > product.stock:
        raise HTTPException(400, t("errors.not_enough_stock", name=product.name, stock=product.stock))


def _get_item(db: Session, user: User, product_id: int) -> CartItem | None:
    return db.scalar(select(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product_id))


def _add(db: Session, user: User, product_id: int, quantity: int) -> None:
    product = _active_product(db, product_id)
    item = _get_item(db, user, product_id)
    new_qty = (item.quantity if item else 0) + quantity
    _check_stock(product, new_qty)
    if item:
        item.quantity = new_qty
    else:
        db.add(CartItem(user_id=user.id, product_id=product_id, quantity=quantity))
        db.flush()


def build_cart(db: Session, user: User) -> dict:
    items = db.scalars(select(CartItem).where(CartItem.user_id == user.id).order_by(CartItem.id)).all()
    rows = [
        {"product": i.product, "quantity": i.quantity, "sum": i.product.price * i.quantity}
        for i in items
    ]
    total = sum(r["sum"] for r in rows)
    return {
        "items": rows,
        "count": sum(r["quantity"] for r in rows),
        "total": total,
        "max_bonus": max_bonus_for(total, user.bonus_balance),
    }


@router.get("", response_model=CartOut)
def get_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return build_cart(db, user)


@router.post("", response_model=CartOut)
def add_to_cart(data: CartAdd, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Add a product (if already in the cart, increase the quantity)."""
    _add(db, user, data.product_id, data.quantity)
    db.commit()
    return build_cart(db, user)


@router.post("/add-many", response_model=CartOut)
def add_many(data: CartAddMany, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The "Add all to cart" button from the PC builder. A repeated id = +1 piece."""
    for product_id in data.product_ids:
        _add(db, user, product_id, 1)
    db.commit()
    return build_cart(db, user)


@router.patch("/{product_id}", response_model=CartOut)
def set_quantity(
    product_id: int, data: CartSet, user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Set the quantity. quantity=0 removes the item from the cart."""
    item = _get_item(db, user, product_id)
    if item is None:
        raise HTTPException(404, t("errors.not_in_cart"))
    if data.quantity == 0:
        db.delete(item)
    else:
        _check_stock(item.product, data.quantity)
        item.quantity = data.quantity
    db.commit()
    return build_cart(db, user)


@router.delete("/{product_id}", response_model=CartOut)
def remove_item(product_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(delete(CartItem).where(CartItem.user_id == user.id, CartItem.product_id == product_id))
    db.commit()
    return build_cart(db, user)


@router.delete("", response_model=CartOut)
def clear_cart(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.execute(delete(CartItem).where(CartItem.user_id == user.id))
    db.commit()
    return build_cart(db, user)
