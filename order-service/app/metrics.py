import time
from collections.abc import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["service", "method", "path", "status_code"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["service", "method", "path"]
)
ORDERS_CREATED_TOTAL = Counter("orders_created_total", "Total number of orders created")
ORDER_STATUS_CHANGES_TOTAL = Counter(
    "order_status_changes_total", "Total number of order status transitions", ["status"]
)
CACHE_HITS_TOTAL = Counter("cache_hits_total", "Total number of cache hits", ["endpoint"])
CACHE_MISSES_TOTAL = Counter("cache_misses_total", "Total number of cache misses", ["endpoint"])
EVENTS_PUBLISHED_TOTAL = Counter(
    "events_published_total", "Total events published to RabbitMQ", ["event_type"]
)
EVENTS_CONSUMED_TOTAL = Counter(
    "events_consumed_total", "Total events consumed from RabbitMQ", ["event_type"]
)

SERVICE_NAME = "order-service"


async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    path = request.scope.get("route").path if request.scope.get("route") else request.url.path
    HTTP_REQUESTS_TOTAL.labels(SERVICE_NAME, request.method, path, response.status_code).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(SERVICE_NAME, request.method, path).observe(duration)
    return response


def metrics_response() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
