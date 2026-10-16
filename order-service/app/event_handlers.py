import logging

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models import CourierStatus

logger = logging.getLogger("order-service.event_handlers")


async def handle_user_event(event_type: str, payload: dict) -> None:
    if event_type == "courier.availability_changed":
        courier_id = payload.get("courier_id")
        if not courier_id:
            return
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(CourierStatus).where(CourierStatus.courier_id == courier_id)
            )
            status_row = result.scalar_one_or_none()
            if status_row is None:
                status_row = CourierStatus(courier_id=courier_id)
                session.add(status_row)
            status_row.is_available = bool(payload.get("is_available", False))
            status_row.vehicle_type = payload.get("vehicle_type", status_row.vehicle_type)
            await session.commit()
    elif event_type == "user.registered":
        logger.info("New user registered upstream: %s", payload)
    else:
        logger.info("Unhandled event type %s: %s", event_type, payload)
