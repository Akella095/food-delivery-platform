from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import UserRole


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: str = Field(min_length=1, max_length=255)
    role: UserRole = UserRole.customer


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AddressOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    street: str
    city: str
    is_default: bool


class AddressCreate(BaseModel):
    street: str
    city: str
    is_default: bool = False


class CourierProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    vehicle_type: str
    is_available: bool
    rating: float


class CourierAvailabilityUpdate(BaseModel):
    is_available: bool
    vehicle_type: str | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    addresses: list[AddressOut] = []
    courier_profile: CourierProfileOut | None = None


class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    message: str
    is_read: bool
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = None
    is_active: bool | None = None
