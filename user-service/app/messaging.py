import asyncio
import json
import logging
from typing import Any

import aio_pika
from aio_pika import ExchangeType
from aio_pika.abc import AbstractRobustConnection

from app.config import settings
from app.metrics import EVENTS_CONSUMED_TOTAL, EVENTS_PUBLISHED_TOTAL

logger = logging.getLogger("user-service.messaging")

EXCHANGE_NAME = "food_delivery_events"

# Event types published by this service
EVENT_USER_REGISTERED = "user.registered"
EVENT_COURIER_AVAILABILITY_CHANGED = "courier.availability_changed"

# Event types this service consumes (published by order-service)
EVENT_ORDER_CREATED = "order.created"
EVENT_ORDER_STATUS_UPDATED = "order.status_updated"

_connection: AbstractRobustConnection | None = None


async def _get_connection() -> AbstractRobustConnection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    return _connection


async def publish_event(event_type: str, payload: dict[str, Any]) -> None:
    """Publish an event to the shared topic exchange. Failures are logged, not fatal."""
    try:
        connection = await _get_connection()
        channel = await connection.channel()
        exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await exchange.publish(message, routing_key=event_type)
        EVENTS_PUBLISHED_TOTAL.labels(event_type).inc()
        logger.info("Published event %s: %s", event_type, payload)
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to publish event %s: %s", event_type, exc)


async def _handle_message(message: aio_pika.IncomingMessage) -> None:
    async with message.process():
        try:
            payload = json.loads(message.body.decode("utf-8"))
        except json.JSONDecodeError:
            logger.error("Could not decode message body")
            return
        event_type = message.routing_key or "unknown"
        EVENTS_CONSUMED_TOTAL.labels(event_type).inc()
        from app.event_handlers import handle_order_event

        await handle_order_event(event_type, payload)


async def start_consumer() -> None:
    """Background consumer for order-service events. Resilient to broker downtime."""
    while True:
        try:
            connection = await _get_connection()
            channel = await connection.channel()
            await channel.set_qos(prefetch_count=10)
            exchange = await channel.declare_exchange(EXCHANGE_NAME, ExchangeType.TOPIC, durable=True)
            queue = await channel.declare_queue("user_service.order_events", durable=True)
            await queue.bind(exchange, routing_key=EVENT_ORDER_CREATED)
            await queue.bind(exchange, routing_key=EVENT_ORDER_STATUS_UPDATED)
            logger.info("user-service consumer listening for order events")
            await queue.consume(_handle_message)
            # Keep the coroutine alive until the connection drops
            await asyncio.Future()
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("RabbitMQ consumer error, retrying in 5s: %s", exc)
            await asyncio.sleep(5)


async def close_connection() -> None:
    global _connection
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
