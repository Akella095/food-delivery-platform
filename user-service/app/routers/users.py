from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache_delete, cache_get, cache_set
from app.database import get_db
from app.dependencies import get_current_user, require_roles
from app.models import User, UserRole
from app.schemas import NotificationOut, UserOut, UserUpdate

router = APIRouter(prefix="/api/users", tags=["users"])


def _user_cache_key(user_id: str) -> str:
    return f"user-service:user:{user_id}"


@router.get("/me", response_model=UserOut)
async def read_me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.get("/me/notifications", response_model=list[NotificationOut])
async def my_notifications(current_user: User = Depends(get_current_user)) -> list:
    return sorted(current_user.notifications, key=lambda n: n.created_at, reverse=True)


@router.get("", response_model=list[UserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role != UserRole.admin and current_user.id != user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    cache_key = _user_cache_key(user_id)
    cached = await cache_get(cache_key)
    if cached is not None:
        return UserOut.model_validate(cached)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    user_out = UserOut.model_validate(user)
    await cache_set(cache_key, user_out.model_dump(mode="json"))
    return user_out


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.admin)),
) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.is_active is not None:
        user.is_active = payload.is_active

    await db.commit()
    await db.refresh(user)

    # Invalidate cache on data change
    await cache_delete(_user_cache_key(user_id))
    return user
