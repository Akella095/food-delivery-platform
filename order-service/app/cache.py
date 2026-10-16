import json
import logging
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger("order-service.cache")

_redis_client: redis.Redis | None = None


def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2)
    return _redis_client


async def cache_get(key: str) -> Any | None:
    """Graceful degradation: any Redis failure results in a cache miss, never a crash."""
    try:
        client = get_redis_client()
        raw = await client.get(key)
        if raw is None:
            return None
        return json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable on GET %s: %s", key, exc)
        return None


async def cache_set(key: str, value: Any, ttl_seconds: int | None = None) -> None:
    try:
        client = get_redis_client()
        await client.set(key, json.dumps(value), ex=ttl_seconds or settings.cache_ttl_seconds)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable on SET %s: %s", key, exc)


async def cache_delete(*keys: str) -> None:
    if not keys:
        return
    try:
        client = get_redis_client()
        await client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable on DELETE %s: %s", keys, exc)


async def cache_delete_pattern(pattern: str) -> None:
    try:
        client = get_redis_client()
        keys = [key async for key in client.scan_iter(match=pattern)]
        if keys:
            await client.delete(*keys)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Redis unavailable on pattern DELETE %s: %s", pattern, exc)
