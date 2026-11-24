"""Admin panel. Access is checked by permissions, see app/permissions.py:
* admin    - everything
* manager  - stats, orders, news/promos/facts
* engineer - products, client builds
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_permission
from app.i18n import t
from app.models import ROLES, Build, Category, Fact, News, Order, OrderItem, Product, User
from app.pagination import page_paginate
from app.permissions import permissions_for
from app.routers.builder import build_out
from app.routers.catalog import _like
from app.schemas import (
    AdminOrderOut,
    BonusGrantIn,
    BuildCommentIn,
    BuildOut,
    FactIn,
    FactOut,
    NewsIn,
    NewsOut,
    NewsUpdate,
    OrderStatus,
    OrderStatusIn,
    Page,
    ProductIn,
    ProductOut,
    ProductUpdate,
    Role,
    RoleOut,
    StatsOut,
    UserAdminUpdate,
    UserOut,
)
from app.services.bonus import add_bonus
from app.services.compatibility import missing_spec_fields
from app.services.orders import change_status

router = APIRouter(prefix="/api/admin", tags=["Admin"])

# Every section of the admin panel is guarded by one permission (see app/permissions.py)
can_view_stats = require_permission("stats.view")
can_manage_orders = require_permission("orders.manage")
can_manage_products = require_permission("products.manage")
can_review_builds = require_permission("builds.review")
can_manage_content = require_permission("content.manage")
can_manage_users = require_permission("users.manage")

PageNum = Query(1, ge=1)
PageSize = Query(20, ge=1, le=100)


# ---------- Stats ----------

@router.get("/stats", response_model=StatsOut, dependencies=[Depends(can_view_stats)])
def stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    top = db.execute(
        select(OrderItem.product_id, OrderItem.product_name, func.sum(OrderItem.quantity).label("sold"))
        .join(Order)
        .where(Order.status != "cancelled")
        .group_by(OrderItem.product_id, OrderItem.product_name)
        .order_by(func.sum(OrderItem.quantity).desc())
        .limit(5)
    ).all()
    return {
        "orders_total": sum(by_status.values()),
        "orders_by_status": by_status,
        "revenue_done": db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.status == "done")),
        "revenue_active": db.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(Order.status != "cancelled")
        ),
        "users_total": db.scalar(select(func.count(User.id))),
        "new_users_7d": db.scalar(select(func.count(User.id)).where(User.created_at >= week_ago)),
        "builds_total": db.scalar(select(func.count(Build.id))),
        "low_stock": db.scalar(select(func.count(Product.id)).where(Product.is_active.is_(True), Product.stock <= 3)),
        "top_products": [{"product_id": r.product_id, "name": r.product_name, "sold": r.sold} for r in top],
    }


# ---------- Orders ----------

@router.get("/orders", response_model=Page[AdminOrderOut], dependencies=[Depends(can_manage_orders)])
def list_orders(
    status: OrderStatus | None = None,
    search: str | None = Query(None, description="client email/name or order number"),
    page: int = PageNum,
    page_size: int = PageSize,
    db: Session = Depends(get_db),
):
    stmt = select(Order).join(Order.user).order_by(Order.id.desc())
    if status:
        stmt = stmt.where(Order.status == status)
    if search and search.strip():
        conds = [User.email.ilike(_like(search), escape="\\"), User.name.ilike(_like(search), escape="\\")]
        if search.strip().lstrip("#").isdigit():
            conds.append(Order.id == int(search.strip().lstrip("#")))
        stmt = stmt.where(or_(*conds))
    return page_paginate(db, stmt, page, page_size)


@router.patch("/orders/{order_id}/status", response_model=AdminOrderOut, dependencies=[Depends(can_manage_orders)])
def set_order_status(order_id: int, data: OrderStatusIn, db: Session = Depends(get_db)):
    """Change status. done credits cashback to the client; cancelled returns stock and bonuses."""
    order = db.get(Order, order_id, with_for_update=True)
    if order is None:
        raise HTTPException(404, t("errors.order_not_found"))
    change_status(db, order, data.status)
    db.commit()
    return order


# ---------- Products ----------

def _category(db: Session, slug: str) -> Category:
    category = db.scalar(select(Category).where(Category.slug == slug))
    if category is None:
        raise HTTPException(400, t("errors.category_not_found", slug=slug))
    return category


def _validate_product(product: Product) -> None:
    missing = missing_spec_fields(product.category.slug, product.specs or {})
    if missing:
        raise HTTPException(422, t("errors.specs_missing", fields=", ".join(missing)))
    if product.old_price is not None and product.old_price <= product.price:
        raise HTTPException(422, t("errors.old_price_invalid"))


@router.get("/products", response_model=Page[ProductOut], dependencies=[Depends(can_manage_products)])
def admin_products(
    search: str | None = None,
    category: str | None = None,
    include_inactive: bool = True,
    page: int = PageNum,
    page_size: int = PageSize,
    db: Session = Depends(get_db),
):
    stmt = select(Product).order_by(Product.id.desc())
    if not include_inactive:
        stmt = stmt.where(Product.is_active.is_(True))
    if category:
        stmt = stmt.where(Product.category.has(Category.slug == category))
    if search and search.strip():
        stmt = stmt.where(or_(Product.name.ilike(_like(search), escape="\\"), Product.brand.ilike(_like(search), escape="\\")))
    return page_paginate(db, stmt, page, page_size)


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(can_manage_products)])
def create_product(data: ProductIn, db: Session = Depends(get_db)):
    fields = data.model_dump(exclude={"category"})
    product = Product(**fields, category=_category(db, data.category), is_active=True)
    _validate_product(product)
    db.add(product)
    db.commit()
    return product


@router.patch("/products/{product_id}", response_model=ProductOut, dependencies=[Depends(can_manage_products)])
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, t("errors.product_not_found"))
    changes = data.model_dump(exclude_unset=True)
    if "category" in changes:
        product.category = _category(db, changes.pop("category"))
    for field, value in changes.items():
        if field in {"name", "brand", "price", "stock", "description", "specs", "is_active"} and value is None:
            raise HTTPException(422, t("errors.field_required", field=field))
        setattr(product, field, value)
    _validate_product(product)
    db.commit()
    return product


@router.delete("/products/{product_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(can_manage_products)])
def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Soft delete: the product is hidden from the catalog but stays in past orders and builds."""
    product = db.get(Product, product_id)
    if product is None:
        raise HTTPException(404, t("errors.product_not_found"))
    product.is_active = False
    db.commit()


# ---------- Client builds ----------

@router.get("/builds", response_model=Page[BuildOut], dependencies=[Depends(can_review_builds)])
def admin_builds(
    without_comment: bool = Query(False, description="only builds without an engineer comment"),
    page: int = PageNum,
    page_size: int = PageSize,
    db: Session = Depends(get_db),
):
    stmt = select(Build).order_by(Build.id.desc())
    if without_comment:
        stmt = stmt.where(Build.engineer_comment.is_(None))
    result = page_paginate(db, stmt, page, page_size)
    result["items"] = [build_out(b) for b in result["items"]]
    return result


@router.patch("/builds/{build_id}/comment", response_model=BuildOut)
def comment_build(
    build_id: int, data: BuildCommentIn, user: User = Depends(can_review_builds), db: Session = Depends(get_db)
):
    build = db.get(Build, build_id)
    if build is None:
        raise HTTPException(404, t("errors.build_not_found"))
    build.engineer_comment = data.comment.strip() or None
    build.engineer_id = user.id
    db.commit()
    return build_out(build)


# ---------- News and facts ----------

def _get_news(db: Session, news_id: int) -> News:
    news = db.get(News, news_id)
    if news is None:
        raise HTTPException(404, t("errors.news_not_found"))
    return news


@router.post("/news", response_model=NewsOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(can_manage_content)])
def create_news(data: NewsIn, db: Session = Depends(get_db)):
    news = News(**data.model_dump())
    db.add(news)
    db.commit()
    return news


@router.patch("/news/{news_id}", response_model=NewsOut, dependencies=[Depends(can_manage_content)])
def update_news(news_id: int, data: NewsUpdate, db: Session = Depends(get_db)):
    news = _get_news(db, news_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        if field != "image_url" and value is None:
            raise HTTPException(422, t("errors.field_required", field=field))
        setattr(news, field, value)
    db.commit()
    return news


@router.delete("/news/{news_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(can_manage_content)])
def delete_news(news_id: int, db: Session = Depends(get_db)):
    db.delete(_get_news(db, news_id))
    db.commit()


@router.get("/facts", response_model=list[FactOut], dependencies=[Depends(can_manage_content)])
def list_facts(db: Session = Depends(get_db)):
    return db.scalars(select(Fact).order_by(Fact.id)).all()


@router.post("/facts", response_model=FactOut, status_code=status.HTTP_201_CREATED, dependencies=[Depends(can_manage_content)])
def create_fact(data: FactIn, db: Session = Depends(get_db)):
    fact = Fact(text=data.text.strip())
    db.add(fact)
    db.commit()
    return fact


@router.delete("/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(can_manage_content)])
def delete_fact(fact_id: int, db: Session = Depends(get_db)):
    fact = db.get(Fact, fact_id)
    if fact is None:
        raise HTTPException(404, t("errors.fact_not_found"))
    db.delete(fact)
    db.commit()


# ---------- Users and roles ----------

@router.get("/roles", response_model=list[RoleOut], dependencies=[Depends(can_manage_users)])
def roles():
    """Roles and their permissions (for the role picker in the admin panel)."""
    return [{"role": role, "permissions": permissions_for(role)} for role in ROLES]


@router.get("/users", response_model=Page[UserOut], dependencies=[Depends(can_manage_users)])
def list_users(
    search: str | None = None,
    role: Role | None = None,
    page: int = PageNum,
    page_size: int = PageSize,
    db: Session = Depends(get_db),
):
    stmt = select(User).order_by(User.id)
    if role:
        stmt = stmt.where(User.role == role)
    if search and search.strip():
        stmt = stmt.where(or_(User.email.ilike(_like(search), escape="\\"), User.name.ilike(_like(search), escape="\\")))
    return page_paginate(db, stmt, page, page_size)


def _get_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, t("errors.user_not_found"))
    return user


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: int, data: UserAdminUpdate, admin: User = Depends(can_manage_users), db: Session = Depends(get_db)
):
    """Assign a role or block/unblock."""
    if user_id == admin.id:
        raise HTTPException(400, t("errors.self_modify"))
    user = _get_user(db, user_id)
    if data.role is not None:
        user.role = data.role
    if data.is_blocked is not None:
        user.is_blocked = data.is_blocked
    db.commit()
    return user


@router.post("/users/{user_id}/bonus", response_model=UserOut, dependencies=[Depends(can_manage_users)])
def grant_bonus(user_id: int, data: BonusGrantIn, db: Session = Depends(get_db)):
    """Manually credit (amount > 0) or debit (amount < 0) bonus points."""
    if data.amount == 0:
        raise HTTPException(400, t("errors.amount_zero"))
    user = db.get(User, user_id, with_for_update=True)
    if user is None:
        raise HTTPException(404, t("errors.user_not_found"))
    add_bonus(db, user, data.amount, data.reason.strip())
    db.commit()
    return user
