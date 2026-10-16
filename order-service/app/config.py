from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "order-service"
    database_url: str = "postgresql+asyncpg://postgres:postgres@order-db:5432/order_db"
    secret_key: str = "super-secret-key-change-me"
    algorithm: str = "HS256"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    cache_ttl_seconds: int = 30
    enable_background_consumer: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
