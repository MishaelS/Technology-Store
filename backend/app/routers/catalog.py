"""Public part: categories, products (infinite scroll), news, facts, home page."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.i18n import t
from app.models import Category, Fact, News, Order, OrderItem, Product
from app.pagination import cursor_paginate
from app.schemas import CategoryOut, CursorPage, FactOut, HomeOut, NewsOut, ProductOut

router = APIRouter(prefix="/api", tags=["Catalog and content"])

# sort -> (sort columns, descending?)
PRODUCT_SORTS = {
    "new": ((Product.id,), True),
    "price_asc": ((Product.price, Product.id), False),
    "price_desc": ((Product.price, Product.id), True),
    "name": ((Product.name, Product.id), False),
}


def _like(text: str) -> str:
    escaped = text.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


@router.get("/categories", response_model=list[CategoryOut])
def categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.position, Category.id)).all()


@router.get("/products", response_model=CursorPage[ProductOut])
def list_products(
    category: str | None = Query(None, description="category slug: cpu, gpu, ram..."),
    search: str | None = Query(None, max_length=100),
    brand: str | None = None,
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    in_stock: bool = False,
    discount: bool = Query(False, description="only discounted products"),
    socket: str | None = Query(None, description="PC builder filter: AM5, LGA1700..."),
    ram_type: str | None = Query(None, description="PC builder filter: DDR4, DDR5"),
    sort: Literal["new", "price_asc", "price_desc", "name"] = "new",
    limit: int = Query(20, ge=1, le=100),
    cursor: str | None = Query(None, description="next_cursor from the previous response"),
    db: Session = Depends(get_db),
):
    """Products in chunks for infinite scroll.

    First request: no cursor. Next one: cursor=next_cursor from the response.
    next_cursor = null means there are no more products.
    """
    filters: list[ColumnElement[bool]] = [Product.is_active.is_(True)]
    if category:
        filters.append(Product.category.has(Category.slug == category))
    if search and search.strip():
        like = _like(search)
        filters.append(or_(Product.name.ilike(like, escape="\\"), Product.brand.ilike(like, escape="\\")))
    if brand:
        filters.append(func.lower(Product.brand) == brand.strip().lower())
    if min_price is not None:
        filters.append(Product.price >= min_price)
    if max_price is not None:
        filters.append(Product.price <= max_price)
    if in_stock:
        filters.append(Product.stock > 0)
    if discount:
        filters.append(Product.old_price > Product.price)
    if socket:
        filters.append(Product.specs["socket"].astext == socket)
    if ram_type:
        filters.append(Product.specs["ram_type"].astext == ram_type)

    total = db.scalar(select(func.count(Product.id)).where(*filters))
    columns, descending = PRODUCT_SORTS[sort]
    items, next_cursor = cursor_paginate(
        db, select(Product).where(*filters), columns, descending, cursor, limit
    )
    return {"items": items, "next_cursor": next_cursor, "total": total}


@router.get("/products/brands", response_model=list[str])
def brands(category: str | None = None, db: Session = Depends(get_db)):
    """Brand list for the filter."""
    stmt = select(Product.brand).where(Product.is_active.is_(True)).distinct().order_by(Product.brand)
    if category:
        stmt = stmt.where(Product.category.has(Category.slug == category))
    return db.scalars(stmt).all()


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None or not product.is_active:
        raise HTTPException(404, t("errors.product_not_found"))
    return product


@router.get("/news", response_model=CursorPage[NewsOut])
def list_news(
    type: Literal["news", "promo", "game"] | None = None,
    limit: int = Query(10, ge=1, le=50),
    cursor: str | None = None,
    db: Session = Depends(get_db),
):
    """News feed in chunks (infinite scroll), newest first."""
    stmt = select(News)
    if type:
        stmt = stmt.where(News.type == type)
    items, next_cursor = cursor_paginate(db, stmt, (News.id,), True, cursor, limit)
    return {"items": items, "next_cursor": next_cursor}


@router.get("/news/{news_id}", response_model=NewsOut)
def get_news(news_id: int, db: Session = Depends(get_db)):
    news = db.get(News, news_id)
    if news is None:
        raise HTTPException(404, t("errors.news_not_found"))
    return news


def _random_fact(db: Session) -> Fact | None:
    return db.scalar(select(Fact).order_by(func.random()).limit(1))


@router.get("/facts/random", response_model=FactOut)
def random_fact(db: Session = Depends(get_db)):
    fact = _random_fact(db)
    if fact is None:
        raise HTTPException(404, t("errors.no_facts"))
    return fact


@router.get("/home", response_model=HomeOut)
def home(db: Session = Depends(get_db)):
    """Everything for the home page in one request."""
    active = Product.is_active.is_(True)

    promos = db.scalars(select(News).where(News.type == "promo").order_by(News.id.desc()).limit(5)).all()
    news = db.scalars(
        select(News).where(News.type.in_(("news", "game"))).order_by(News.id.desc()).limit(6)
    ).all()
    discounts = db.scalars(
        select(Product)
        .where(active, Product.old_price > Product.price, Product.stock > 0)
        .order_by(((Product.old_price - Product.price) * 100 / Product.old_price).desc())
        .limit(8)
    ).all()

    # Best sellers: most sold (excluding cancelled orders). If there are too few sales, fill up with new products.
    sold = (
        select(OrderItem.product_id, func.sum(OrderItem.quantity).label("sold"))
        .join(Order)
        .where(Order.status != "cancelled")
        .group_by(OrderItem.product_id)
        .subquery()
    )
    hits = list(
        db.scalars(
            select(Product).join(sold, sold.c.product_id == Product.id).where(active)
            .order_by(sold.c.sold.desc()).limit(8)
        )
    )
    if len(hits) < 8:
        exclude = [p.id for p in hits] or [0]
        hits += db.scalars(
            select(Product).where(active, Product.id.not_in(exclude))
            .order_by(Product.id.desc()).limit(8 - len(hits))
        ).all()

    return {
        "promos": promos,
        "discounts": discounts,
        "news": news,
        "hits": hits,
        "fact": _random_fact(db),
    }
