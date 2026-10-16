from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import CurrentUser, require_roles
from app.models import CourierStatus
from app.schemas import CourierStatusOut

router = APIRouter(prefix="/api/couriers", tags=["couriers"])


@router.get("/available", response_model=list[CourierStatusOut])
async def list_available_couriers(
    db: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_roles("admin", "courier")),
) -> list[CourierStatus]:
    """Backed by a local read-model kept in sync via RabbitMQ events from user-service."""
    result = await db.execute(select(CourierStatus).where(CourierStatus.is_available.is_(True)))
    return list(result.scalars().all())
