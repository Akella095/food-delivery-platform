from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.cache import cache_delete, cache_get, cache_set
from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.metrics import CACHE_HITS_TOTAL, CACHE_MISSES_TOTAL
from app.models import MenuItem, Restaurant
from app.schemas import (
    MenuItemCreate,
    MenuItemOut,
    RestaurantCreate,
    RestaurantListItem,
    RestaurantOut,
    RestaurantUpdate,
)

router = APIRouter(prefix="/api/restaurants", tags=["restaurants"])

RESTAURANT_LIST_CACHE_KEY = "order-service:restaurants:list"


def _restaurant_detail_cache_key(restaurant_id: str) -> str:
    return f"order-service:restaurant:{restaurant_id}"


@router.get("", response_model=list[RestaurantListItem])
async def list_restaurants(db: AsyncSession = Depends(get_db)) -> list:
    cached = await cache_get(RESTAURANT_LIST_CACHE_KEY)
    if cached is not None:
        CACHE_HITS_TOTAL.labels("restaurants_list").inc()
        return cached

    CACHE_MISSES_TOTAL.labels("restaurants_list").inc()
    result = await db.execute(
        select(Restaurant).where(Restaurant.is_active.is_(True)).order_by(Restaurant.created_at.desc())
    )
    restaurants = result.scalars().all()
    data = [RestaurantListItem.model_validate(r).model_dump(mode="json") for r in restaurants]
    await cache_set(RESTAURANT_LIST_CACHE_KEY, data)
    return data


@router.get("/{restaurant_id}", response_model=RestaurantOut)
async def get_restaurant(restaurant_id: str, db: AsyncSession = Depends(get_db)) -> Restaurant:
    cache_key = _restaurant_detail_cache_key(restaurant_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        CACHE_HITS_TOTAL.labels("restaurant_detail").inc()
        return RestaurantOut.model_validate(cached)

    CACHE_MISSES_TOTAL.labels("restaurant_detail").inc()
    result = await db.execute(
        select(Restaurant).options(selectinload(Restaurant.menu_items)).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    out = RestaurantOut.model_validate(restaurant)
    await cache_set(cache_key, out.model_dump(mode="json"))
    return out


@router.post("", response_model=RestaurantOut, status_code=status.HTTP_201_CREATED)
async def create_restaurant(
    payload: RestaurantCreate,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(require_roles("admin")),
) -> Restaurant:
    restaurant = Restaurant(name=payload.name, address=payload.address, owner_id=current_user.id)
    db.add(restaurant)
    await db.commit()
    await db.refresh(restaurant)

    await cache_delete(RESTAURANT_LIST_CACHE_KEY)
    return restaurant


@router.patch("/{restaurant_id}", response_model=RestaurantOut)
async def update_restaurant(
    restaurant_id: str,
    payload: RestaurantUpdate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_roles("admin")),
) -> Restaurant:
    result = await db.execute(
        select(Restaurant).options(selectinload(Restaurant.menu_items)).where(Restaurant.id == restaurant_id)
    )
    restaurant = result.scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    if payload.name is not None:
        restaurant.name = payload.name
    if payload.address is not None:
        restaurant.address = payload.address
    if payload.is_active is not None:
        restaurant.is_active = payload.is_active

    await db.commit()
    await db.refresh(restaurant)

    # Invalidate caches affected by this change
    await cache_delete(RESTAURANT_LIST_CACHE_KEY, _restaurant_detail_cache_key(restaurant_id))
    return restaurant


@router.post("/{restaurant_id}/menu", response_model=MenuItemOut, status_code=status.HTTP_201_CREATED)
async def add_menu_item(
    restaurant_id: str,
    payload: MenuItemCreate,
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_roles("admin")),
) -> MenuItem:
    result = await db.execute(select(Restaurant).where(Restaurant.id == restaurant_id))
    restaurant = result.scalar_one_or_none()
    if restaurant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Restaurant not found")

    menu_item = MenuItem(restaurant_id=restaurant_id, **payload.model_dump())
    db.add(menu_item)
    await db.commit()
    await db.refresh(menu_item)

    await cache_delete(RESTAURANT_LIST_CACHE_KEY, _restaurant_detail_cache_key(restaurant_id))
    return menu_item


@router.get("/{restaurant_id}/menu", response_model=list[MenuItemOut])
async def list_menu(restaurant_id: str, db: AsyncSession = Depends(get_db)) -> list[MenuItem]:
    result = await db.execute(select(MenuItem).where(MenuItem.restaurant_id == restaurant_id))
    return list(result.scalars().all())
