"""Pydantic schemas: what the API accepts and returns."""

import re
from datetime import datetime
from typing import Annotated, Generic, Literal, TypeVar
from urllib.parse import urlparse

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.i18n import t

T = TypeVar("T")

Role = Literal["client", "employee", "engineer", "senior_engineer", "manager", "admin"]
OrderStatus = Literal["new", "confirmed", "assembling", "shipped", "done", "cancelled"]
NewsType = Literal["news", "promo", "game"]
RepairStatus = Literal["accepted", "diagnostics", "repairing", "ready", "issued", "cancelled"]

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\+?[0-9()\-\s]+$")


def _check_phone(value: str) -> str:
    digits = sum(ch.isdigit() for ch in value)
    if not PHONE_RE.match(value) or not 7 <= digits <= 15:
        raise ValueError(t("errors.invalid_phone"))
    return value


def _check_image_url(value: str) -> str:
    """Only http(s) links or paths on our own site: no javascript:, data: and so on."""
    parsed = urlparse(value)
    is_web = parsed.scheme in ("http", "https") and bool(parsed.netloc)
    is_local = not parsed.scheme and not parsed.netloc and value.startswith("/")
    if not (is_web or is_local):
        raise ValueError(t("errors.invalid_image_url"))
    return value


def _text(min_length: int = 0, max_length: int | None = None):
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


# Strings with spaces trimmed BEFORE the length check, so "   " counts as empty.
# Name = (min length, max length).
Text_1_100 = Annotated[str, _text(1, 100)]
Text_1_200 = Annotated[str, _text(1, 200)]
Text_1_1000 = Annotated[str, _text(1, 1000)]
Text_5_300 = Annotated[str, _text(5, 300)]
Text_0_500 = Annotated[str, _text(0, 500)]
Text_0_2000 = Annotated[str, _text(0, 2000)]
TextRequired = Annotated[str, _text(1)]
TextOptional = Annotated[str, _text()]


Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=30), AfterValidator(_check_phone)]
ImageUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_check_image_url)]


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
    name: Text_1_100
    phone: Phone | None = None

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
    avatar_url: str | None = None
    created_at: datetime


class UserShort(ORM):
    id: int
    email: str
    name: str


class TokenOut(BaseModel):
    token: str
    user: UserOut


class ProfileUpdate(BaseModel):
    name: Text_1_100 | None = None
    phone: Phone | None = None


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
    images: list[str] = []
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
    address: Text_5_300
    phone: Phone
    comment: Text_0_500 = ""
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
    name: Text_1_100
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
    comment: Text_0_2000


# ---------- Admin ----------

MAX_PRODUCT_IMAGES = 10  # extra photos of one product

class ProductIn(BaseModel):
    category: str  # category slug
    name: Text_1_200
    brand: Text_1_100
    price: int = Field(gt=0)
    old_price: int | None = Field(default=None, gt=0)
    stock: int = Field(default=0, ge=0)
    image_url: ImageUrl | None = None
    images: list[ImageUrl] = Field(default_factory=list, max_length=MAX_PRODUCT_IMAGES)
    description: TextOptional = ""
    specs: dict = Field(default_factory=dict)


class ProductUpdate(BaseModel):
    category: str | None = None
    name: Text_1_200 | None = None
    brand: Text_1_100 | None = None
    price: int | None = Field(default=None, gt=0)
    old_price: int | None = Field(default=None, gt=0)
    stock: int | None = Field(default=None, ge=0)
    image_url: ImageUrl | None = None
    images: list[ImageUrl] | None = Field(default=None, max_length=MAX_PRODUCT_IMAGES)
    description: TextOptional | None = None
    specs: dict | None = None
    is_active: bool | None = None


class NewsIn(BaseModel):
    title: Text_1_200
    text: TextRequired
    image_url: ImageUrl | None = None
    type: NewsType = "news"


class NewsUpdate(BaseModel):
    title: Text_1_200 | None = None
    text: TextRequired | None = None
    image_url: ImageUrl | None = None
    type: NewsType | None = None


class FactIn(BaseModel):
    text: Text_1_1000


class UserAdminUpdate(BaseModel):
    role: Role | None = None
    is_blocked: bool | None = None


class BonusGrantIn(BaseModel):
    amount: int  # can be negative (debit)
    reason: Text_1_200


class SpecFieldOut(BaseModel):
    key: str
    kind: Literal["text", "number", "score", "flag", "text_list"]
    required: bool
    suggestions: list[str]  # values already used by other products of the category


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


# ---------- Repairs ----------

class RepairCreate(BaseModel):
    client_email: str | None = None   # link the repair to a registered client (optional)
    client_name: Text_1_100
    client_phone: Phone
    device: Text_1_200
    problem: TextRequired
    price: int | None = Field(default=None, ge=0)


class RepairUpdate(BaseModel):
    status: RepairStatus | None = None
    price: int | None = Field(default=None, ge=0)
    engineer_comment: Text_0_2000 | None = None
    device: Text_1_200 | None = None
    problem: TextRequired | None = None


class RepairOut(ORM):
    id: int
    client_id: int | None
    client_name: str
    client_phone: str
    device: str
    problem: str
    status: str
    price: int | None
    engineer_comment: str
    engineer: UserShort | None
    created_at: datetime
    updated_at: datetime


# ---------- Stock receipts ----------

class StockReceiptIn(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=100_000)
    supplier: Text_0_500 = ""
    comment: Text_0_500 = ""


class ProductShort(ORM):
    id: int
    name: str
    stock: int


class StockReceiptOut(ORM):
    id: int
    product: ProductShort
    quantity: int
    supplier: str
    comment: str
    received_by: UserShort | None
    created_at: datetime


# ---------- Tech support ----------

class ErrorLogOut(ORM):
    id: int
    method: str
    path: str
    error: str
    created_at: datetime


class DatabaseInfo(BaseModel):
    ok: bool
    version: str
    size: str
    migration: str | None


class SystemOut(BaseModel):
    api_version: str
    python_version: str
    uptime_seconds: int
    database: DatabaseInfo
    counts: dict[str, int]
    recent_errors: list[ErrorLogOut]
