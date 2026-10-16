import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.messaging import close_connection, start_consumer
from app.metrics import metrics_middleware, metrics_response
from app.routers import auth, couriers, users

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("user-service")

_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _consumer_task
    if settings.enable_background_consumer:
        _consumer_task = asyncio.create_task(start_consumer())
        logger.info("Started RabbitMQ consumer background task")
    yield
    if _consumer_task is not None:
        _consumer_task.cancel()
    await close_connection()


app = FastAPI(
    title="User Service",
    description="...",
    version="1.0.0",
    lifespan=lifespan,
    root_path="/user-service",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.middleware("http")(metrics_middleware)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(couriers.router)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled exception while processing %s %s", request.method, request.url)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": settings.service_name}


@app.get("/metrics", tags=["monitoring"])
async def metrics():
    return metrics_response()
