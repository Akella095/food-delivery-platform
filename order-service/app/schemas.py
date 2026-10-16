from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models import OrderStatus


class MenuItemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str = ""
    price: Decimal = Field(gt=0)
    is_available: bool = True


class MenuItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: str
    price: Decimal
    is_available: bool


class RestaurantCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=255)


class RestaurantUpdate(BaseModel):
    name: str | None = None
    address: str | None = None
    is_active: bool | None = None


class RestaurantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    address: str
    owner_id: str
    is_active: bool
    created_at: datetime
    menu_items: list[MenuItemOut] = []


class RestaurantListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    address: str
    is_active: bool
    created_at: datetime


class OrderItemCreate(BaseModel):
    menu_item_id: str
    quantity: int = Field(gt=0, default=1)


class OrderCreate(BaseModel):
    restaurant_id: str
    items: list[OrderItemCreate] = Field(min_length=1)


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    menu_item_id: str
    quantity: int
    price: Decimal


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    courier_id: str | None
    restaurant_id: str
    status: OrderStatus
    total_price: Decimal
    created_at: datetime
    items: list[OrderItemOut] = []


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    courier_id: str | None = None


class CourierStatusOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    courier_id: str
    is_available: bool
    vehicle_type: str
