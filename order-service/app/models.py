import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class OrderStatus(str, enum.Enum):
    pending = "pending"
    confirmed = "confirmed"
    preparing = "preparing"
    on_the_way = "on_the_way"
    delivered = "delivered"
    cancelled = "cancelled"


class Restaurant(Base):
    __tablename__ = "restaurants"
    __table_args__ = (Index("ix_restaurants_is_active", "is_active"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    owner_id: Mapped[str] = mapped_column(String(36), index=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    menu_items: Mapped[list["MenuItem"]] = relationship(
        "MenuItem", back_populates="restaurant", cascade="all, delete-orphan", lazy="selectin"
    )


class MenuItem(Base):
    __tablename__ = "menu_items"
    __table_args__ = (Index("ix_menu_items_restaurant_id", "restaurant_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    restaurant_id: Mapped[str] = mapped_column(
        ForeignKey("restaurants.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(1000), default="")
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    restaurant: Mapped["Restaurant"] = relationship("Restaurant", back_populates="menu_items")


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        Index("ix_orders_customer_id", "customer_id"),
        Index("ix_orders_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    customer_id: Mapped[str] = mapped_column(String(36), nullable=False)
    courier_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    restaurant_id: Mapped[str] = mapped_column(
        ForeignKey("restaurants.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus, name="order_status"), default=OrderStatus.pending, nullable=False
    )
    total_price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    restaurant: Mapped["Restaurant"] = relationship("Restaurant", lazy="selectin")


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (Index("ix_order_items_order_id", "order_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    menu_item_id: Mapped[str] = mapped_column(
        ForeignKey("menu_items.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    order: Mapped["Order"] = relationship("Order", back_populates="items")
    menu_item: Mapped["MenuItem"] = relationship("MenuItem", lazy="selectin")


class CourierStatus(Base):
    """Local read-model populated asynchronously from user-service RabbitMQ events."""

    __tablename__ = "courier_status"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    courier_id: Mapped[str] = mapped_column(String(36), unique=True, index=True, nullable=False)
    is_available: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vehicle_type: Mapped[str] = mapped_column(String(50), default="bike")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
