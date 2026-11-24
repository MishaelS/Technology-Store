"""Pydantic schemas: what the API accepts and returns."""

import re
from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.i18n import t

T = TypeVar("T")

Role = Literal["client", "manager", "engineer", "admin"]
OrderStatus = Literal["new", "confirmed", "assembling", "shipped", "done", "cancelled"]
NewsType = Literal["news", "promo", "game"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Common ----------

class CursorPage(BaseModel, Generic[T]):
    """A chunk for infinite scroll."""
    items: list[T]
    next_cursor: str | None
    total: int | None = None


class Page(BaseModel, Generic[T]):
    """A page for admin tables."""
    items: list[T]
    total: int
    page: int
    pages: int


class Message(BaseModel):
    detail: str


# ---------- Users and auth ----------

class RegisterIn(BaseModel):
    email: str = Field(max_length=255)
    password: str = Field(min_length=6, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    @field_validator("email")
    @classmethod
    def check_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not EMAIL_RE.match(v):
            raise ValueError(t("errors.invalid_email"))
        return v


class LoginIn(BaseModel):
    email: str
    password: str


class UserOut(ORM):
    id: int
    email: str
    name: str
    phone: str | None
    role: str
    permissions: list[str]  # what the frontend may show this user, see app/permissions.py
    bonus_balance: int
    is_blocked: bool
    created_at: datetime


class UserShort(ORM):
    id: int
    email: str
    name: str


class TokenOut(BaseModel):
    token: str
    user: UserOut


class ProfileUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)


# ---------- Catalog ----------

class CategoryOut(ORM):
    id: int
    name: str = Field(validation_alias="display_name")
    slug: str


class ProductOut(ORM):
    id: int
    category: str = Field(validation_alias="category_slug")
    category_name: str
    name: str
    brand: str
    price: int
    old_price: int | None
    discount_percent: int
    stock: int
    image_url: str | None
    description: str
    specs: dict
    is_active: bool


class NewsOut(ORM):
    id: int
    title: str
    text: str
    image_url: str | None
    type: str
    created_at: datetime


class FactOut(ORM):
    id: int
    text: str


class HomeOut(BaseModel):
    promos: list[NewsOut]
    discounts: list[ProductOut]
    news: list[NewsOut]
    hits: list[ProductOut]
    fact: FactOut | None


# ---------- Cart ----------

class CartAdd(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class CartAddMany(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=50)


class CartSet(BaseModel):
    quantity: int = Field(ge=0, le=99)


class CartItemOut(BaseModel):
    product: ProductOut
    quantity: int
    sum: int


class CartOut(BaseModel):
    items: list[CartItemOut]
    count: int
    total: int
    max_bonus: int  # how many bonus points can be spent on this cart


# ---------- Orders and bonuses ----------

class OrderCreate(BaseModel):
    address: str = Field(min_length=5, max_length=300)
    phone: str = Field(min_length=5, max_length=30)
    comment: str = Field(default="", max_length=500)
    bonus_to_use: int = Field(default=0, ge=0)


class OrderItemOut(ORM):
    product_id: int
    product_name: str
    quantity: int
    price: int


class OrderOut(ORM):
    id: int
    status: str
    subtotal: int
    bonus_used: int
    total: int
    bonus_earned: int
    address: str
    phone: str
    comment: str
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemOut]


class AdminOrderOut(OrderOut):
    user: UserShort


class OrderStatusIn(BaseModel):
    status: OrderStatus


class BonusHistoryOut(ORM):
    id: int
    amount: int
    reason: str
    order_id: int | None
    created_at: datetime


class BonusOut(BaseModel):
    balance: int
    history: list[BonusHistoryOut]


# ---------- PC builder and builds ----------

class BuilderIn(BaseModel):
    product_ids: list[int] = Field(max_length=30)


class CheckItem(BaseModel):
    code: str
    status: Literal["ok", "warning", "error", "skip"]
    message: str


class CheckResult(BaseModel):
    checks: list[CheckItem]
    is_compatible: bool   # no errors
    is_complete: bool     # all required parts are selected
    cpu_score: int
    gpu_score: int
    score: int            # 0–100
    tier: str             # office | gaming | powerful | top
    tier_name: str
    total_price: int
    power_draw: int       # estimated power draw, W
    recommended_psu: int  # recommended PSU wattage, W
    ram_total_gb: int


class BuildCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    product_ids: list[int] = Field(min_length=1, max_length=30)


class BuildOut(BaseModel):
    id: int
    name: str
    engineer_comment: str | None
    created_at: datetime
    user: UserShort
    items: list[ProductOut]
    check: CheckResult


class BuildCommentIn(BaseModel):
    comment: str = Field(max_length=2000)


# ---------- Admin ----------

class ProductIn(BaseModel):
    category: str  # category slug
    name: str = Field(min_length=1, max_length=200)
    brand: str = Field(min_length=1, max_length=100)
    price: int = Field(gt=0)
    old_price: int | None = Field(default=None, gt=0)
    stock: int = Field(default=0, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    description: str = ""
    specs: dict = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    category: str | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    brand: str | None = Field(default=None, min_length=1, max_length=100)
    price: int | None = Field(default=None, gt=0)
    old_price: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    image_url: str | None = Field(default=None, max_length=500)
    description: str | None = None
    specs: dict | None = None
    is_active: bool | None = None


class NewsIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1)
    image_url: str | None = Field(default=None, max_length=500)
    type: NewsType = "news"


class NewsUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    text: str | None = Field(default=None, min_length=1)
    image_url: str | None = Field(default=None, max_length=500)
    type: NewsType | None = None


class FactIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)


class UserAdminUpdate(BaseModel):
    role: Role | None = None
    is_blocked: bool | None = None


class BonusGrantIn(BaseModel):
    amount: int  # can be negative (debit)
    reason: str = Field(min_length=1, max_length=200)


class RoleOut(BaseModel):
    role: str
    permissions: list[str]


class TopProduct(BaseModel):
    product_id: int
    name: str
    sold: int


class StatsOut(BaseModel):
    orders_total: int
    orders_by_status: dict[str, int]
    revenue_done: int        # revenue from completed orders
    revenue_active: int      # total of all non-cancelled orders
    users_total: int
    new_users_7d: int
    builds_total: int
    low_stock: int           # products with stock <= 3
    top_products: list[TopProduct]
