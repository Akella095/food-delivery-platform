from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_roles
from app.messaging import EVENT_COURIER_AVAILABILITY_CHANGED, publish_event
from app.metrics import COURIERS_AVAILABLE
from app.models import CourierProfile, User, UserRole
from app.schemas import CourierAvailabilityUpdate, CourierProfileOut

router = APIRouter(prefix="/api/users/couriers", tags=["couriers"])


@router.put("/me/availability", response_model=CourierProfileOut)
async def update_availability(
    payload: CourierAvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(UserRole.courier)),
) -> CourierProfile:
    result = await db.execute(select(CourierProfile).where(CourierProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if profile is None:
        profile = CourierProfile(user_id=current_user.id)
        db.add(profile)

    profile.is_available = payload.is_available
    if payload.vehicle_type:
        profile.vehicle_type = payload.vehicle_type

    await db.commit()
    await db.refresh(profile)

    available_count = await db.execute(select(CourierProfile).where(CourierProfile.is_available.is_(True)))
    COURIERS_AVAILABLE.set(len(available_count.scalars().all()))

    await publish_event(
        EVENT_COURIER_AVAILABILITY_CHANGED,
        {
            "courier_id": current_user.id,
            "is_available": profile.is_available,
            "vehicle_type": profile.vehicle_type,
        },
    )
    return profile


@router.get("/{user_id}", response_model=CourierProfileOut)
async def get_courier_profile(user_id: str, db: AsyncSession = Depends(get_db)) -> CourierProfile:
    result = await db.execute(select(CourierProfile).where(CourierProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Courier profile not found")
    return profile
