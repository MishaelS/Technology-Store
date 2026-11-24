"""Database tables (SQLAlchemy)."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.i18n import t
from app.permissions import permissions_for

ROLES = ("client", "manager", "engineer", "admin")
ORDER_STATUSES = ("new", "confirmed", "assembling", "shipped", "done", "cancelled")
NEWS_TYPES = ("news", "promo", "game")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(_in("role", ROLES), name="ck_users_role"),
        CheckConstraint("bonus_balance >= 0", name="ck_users_bonus_balance"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(30))
    role: Mapped[str] = mapped_column(String(20), default="client")
    bonus_balance: Mapped[int] = mapped_column(Integer, default=0)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)

    @property
    def permissions(self) -> list[str]:
        return permissions_for(self.role)


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    position: Mapped[int] = mapped_column(Integer, default=0)

    @property
    def display_name(self) -> str:
        """Name in the request language (locales: categories.<slug>); DB name as a fallback."""
        return t(f"categories.{self.slug}", default=self.name)


class Product(TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("price > 0", name="ck_products_price"),
        CheckConstraint("stock >= 0", name="ck_products_stock"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    brand: Mapped[str] = mapped_column(String(100))
    price: Mapped[int] = mapped_column(Integer)                 # in rubles
    old_price: Mapped[int | None] = mapped_column(Integer)      # price before discount
    stock: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    specs: Mapped[dict] = mapped_column(JSONB, default=dict)    # specs used by the PC builder
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # False = "deleted" from the catalog

    category: Mapped[Category] = relationship(lazy="joined", innerjoin=True)

    @property
    def category_slug(self) -> str:
        return self.category.slug

    @property
    def category_name(self) -> str:
        return self.category.display_name

    @property
    def discount_percent(self) -> int:
        if self.old_price and self.old_price > self.price:
            return round((self.old_price - self.price) * 100 / self.old_price)
        return 0


class CartItem(Base):
    __tablename__ = "cart_items"
    __table_args__ = (
        UniqueConstraint("user_id", "product_id", name="uq_cart_user_product"),
        CheckConstraint("quantity > 0", name="ck_cart_quantity"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

    product: Mapped[Product] = relationship(lazy="joined", innerjoin=True)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint(_in("status", ORDER_STATUSES), name="ck_orders_status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    subtotal: Mapped[int] = mapped_column(Integer)        # sum of item prices
    bonus_used: Mapped[int] = mapped_column(Integer, default=0)
    total: Mapped[int] = mapped_column(Integer)           # amount to pay = subtotal - bonus_used
    bonus_earned: Mapped[int] = mapped_column(Integer, default=0)
    address: Mapped[str] = mapped_column(String(300))
    phone: Mapped[str] = mapped_column(String(30))
    comment: Mapped[str] = mapped_column(String(500), default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(lazy="joined", innerjoin=True)
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(200))  # name at the time of purchase
    quantity: Mapped[int] = mapped_column(Integer)
    price: Mapped[int] = mapped_column(Integer)             # price at the time of purchase

    order: Mapped[Order] = relationship(back_populates="items")


class BonusHistory(TimestampMixin, Base):
    __tablename__ = "bonus_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[int] = mapped_column(Integer)  # + credit, - debit
    reason: Mapped[str] = mapped_column(String(200))
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id", ondelete="SET NULL"))


class Build(TimestampMixin, Base):
    __tablename__ = "builds"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    engineer_comment: Mapped[str | None] = mapped_column(Text)
    engineer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    user: Mapped[User] = relationship(foreign_keys=[user_id], lazy="joined", innerjoin=True)
    items: Mapped[list["BuildItem"]] = relationship(
        back_populates="build", cascade="all, delete-orphan", lazy="selectin"
    )


class BuildItem(Base):
    __tablename__ = "build_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    build_id: Mapped[int] = mapped_column(ForeignKey("builds.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))

    build: Mapped[Build] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined", innerjoin=True)


class News(TimestampMixin, Base):
    __tablename__ = "news"
    __table_args__ = (CheckConstraint(_in("type", NEWS_TYPES), name="ck_news_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    text: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    type: Mapped[str] = mapped_column(String(20), default="news", index=True)


class Fact(Base):
    __tablename__ = "facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
