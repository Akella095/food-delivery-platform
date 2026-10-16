from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import CurrentUser, get_current_user, require_roles
from app.messaging import EVENT_ORDER_CREATED, EVENT_ORDER_STATUS_UPDATED, publish_event
from app.metrics import ORDER_STATUS_CHANGES_TOTAL, ORDERS_CREATED_TOTAL
from app.models import MenuItem, Order, OrderItem, OrderStatus, Restaurant
from app.schemas import OrderCreate, OrderOut, OrderStatusUpdate

router = APIRouter(prefix="/api/orders", tags=["orders"])

# Eager-load relationships consistently to avoid N+1 queries in list/detail endpoints.
ORDER_LOAD_OPTIONS = (
    selectinload(Order.items).selectinload(OrderItem.menu_item),
    selectinload(Order.restaurant),
)


@router.post("", response_model=OrderOut, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("customer", "admin")),
) -> Order:
    restaurant_result = await db.execute(
        select(Restaurant).where(Restaurant.id == payload.restaurant_id, Restaurant.is_active.is_(True))
    )
    restaurant = restaurant_result.scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found or inactive")

    menu_item_ids = [item.menu_item_id for item in payload.items]
    menu_result = await db.execute(
        select(MenuItem).where(
            MenuItem.id.in_(menu_item_ids), MenuItem.restaurant_id == payload.restaurant_id
        )
    )
    menu_items_by_id = {item.id: item for item in menu_result.scalars().all()}

    if len(menu_items_by_id) != len(set(menu_item_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="One or more menu items are invalid"
        )

    order = Order(
        customer_id=current_user.id, restaurant_id=payload.restaurant_id, status=OrderStatus.pending
    )
    total_price = 0
    for item in payload.items:
        menu_item = menu_items_by_id[item.menu_item_id]
        if not menu_item.is_available:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Menu item {menu_item.name} is unavailable"
            )
        line_price = float(menu_item.price) * item.quantity
        total_price += line_price
        order.items.append(
            OrderItem(menu_item_id=menu_item.id, quantity=item.quantity, price=menu_item.price)
        )

    order.total_price = total_price
    db.add(order)

    try:
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create order"
        ) from exc

    result = await db.execute(select(Order).options(*ORDER_LOAD_OPTIONS).where(Order.id == order.id))
    order = result.scalar_one()

    ORDERS_CREATED_TOTAL.inc()
    await publish_event(
        EVENT_ORDER_CREATED,
        {
            "order_id": order.id,
            "customer_id": order.customer_id,
            "restaurant_id": order.restaurant_id,
            "total_price": float(order.total_price),
        },
    )
    return order


@router.get("", response_model=list[OrderOut])
async def list_orders(
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[Order]:
    query = select(Order).options(*ORDER_LOAD_OPTIONS).order_by(Order.created_at.desc())
    if current_user.role == "customer":
        query = query.where(Order.customer_id == current_user.id)
    elif current_user.role == "courier":
        query = query.where(Order.courier_id == current_user.id)
    # admins see every order

    result = await db.execute(query)
    return list(result.scalars().all())


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(
    order_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Order:
    result = await db.execute(select(Order).options(*ORDER_LOAD_OPTIONS).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if current_user.role == "customer" and order.customer_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")
    if current_user.role == "courier" and order.courier_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return order


@router.patch("/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: str,
    payload: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("courier", "admin")),
) -> Order:
    result = await db.execute(select(Order).options(*ORDER_LOAD_OPTIONS).where(Order.id == order_id))
    order = result.scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    order.status = payload.status
    if payload.courier_id is not None:
        order.courier_id = payload.courier_id
    elif current_user.role == "courier" and order.courier_id is None:
        order.courier_id = current_user.id

    await db.commit()
    await db.refresh(order, attribute_names=["status", "courier_id"])

    ORDER_STATUS_CHANGES_TOTAL.labels(payload.status.value).inc()
    await publish_event(
        EVENT_ORDER_STATUS_UPDATED,
        {
            "order_id": order.id,
            "customer_id": order.customer_id,
            "status": order.status.value,
            "courier_id": order.courier_id,
        },
    )
    return order
