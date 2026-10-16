import time
from collections.abc import Callable

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.requests import Request
from starlette.responses import Response

HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total", "Total HTTP requests", ["service", "method", "path", "status_code"]
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds", "HTTP request duration in seconds", ["service", "method", "path"]
)
USERS_REGISTERED_TOTAL = Counter("users_registered_total", "Total number of registered users", ["role"])
COURIERS_AVAILABLE = Gauge("couriers_available", "Current number of couriers marked as available")
EVENTS_PUBLISHED_TOTAL = Counter(
    "events_published_total", "Total events published to RabbitMQ", ["event_type"]
)
EVENTS_CONSUMED_TOTAL = Counter(
    "events_consumed_total", "Total events consumed from RabbitMQ", ["event_type"]
)

SERVICE_NAME = "user-service"


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
