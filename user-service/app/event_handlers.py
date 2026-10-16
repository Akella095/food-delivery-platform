import logging

from app.database import AsyncSessionLocal
from app.models import Notification

logger = logging.getLogger("user-service.event_handlers")


async def handle_order_event(event_type: str, payload: dict) -> None:
    """Persist a notification for the customer whenever an order event arrives."""
    customer_id = payload.get("customer_id")
    if not customer_id:
        logger.warning("Order event %s missing customer_id: %s", event_type, payload)
        return

    if event_type == "order.created":
        message = f"Your order #{payload.get('order_id')} has been created."
    elif event_type == "order.status_updated":
        message = f"Order #{payload.get('order_id')} status changed to {payload.get('status')}."
    else:
        message = f"Event {event_type} received."

    async with AsyncSessionLocal() as session:
        notification = Notification(user_id=customer_id, event_type=event_type, message=message)
        session.add(notification)
        await session.commit()
