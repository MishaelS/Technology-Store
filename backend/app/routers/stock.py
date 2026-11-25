"""Stock receipts: an employee records a delivery, the product stock grows."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_permission
from app.i18n import t
from app.models import Product, StockReceipt, User
from app.pagination import page_paginate
from app.schemas import Page, StockReceiptIn, StockReceiptOut

router = APIRouter(prefix="/api/admin/stock", tags=["Stock"])
can_receive = require_permission("stock.receive")


@router.post("/receipts", response_model=StockReceiptOut, status_code=status.HTTP_201_CREATED)
def receive(data: StockReceiptIn, user: User = Depends(can_receive), db: Session = Depends(get_db)):
    """Accept a delivery: stock of the product grows by `quantity`, the receipt is kept in the log."""
    product = db.get(Product, data.product_id, with_for_update=True)
    if product is None:
        raise HTTPException(404, t("errors.product_not_found"))
    product.stock += data.quantity
    receipt = StockReceipt(
        product_id=product.id,
        quantity=data.quantity,
        supplier=data.supplier,
        comment=data.comment,
        received_by_id=user.id,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


@router.get("/receipts", response_model=Page[StockReceiptOut], dependencies=[Depends(can_receive)])
def receipts(
    product_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Log of deliveries, newest first."""
    stmt = select(StockReceipt).order_by(StockReceipt.id.desc())
    if product_id:
        stmt = stmt.where(StockReceipt.product_id == product_id)
    return page_paginate(db, stmt, page, page_size)
