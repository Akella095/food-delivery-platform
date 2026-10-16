from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    service_name: str = "user-service"
    database_url: str = "postgresql+asyncpg://postgres:postgres@user-db:5432/user_db"
    secret_key: str = "super-secret-key-change-me"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    cache_ttl_seconds: int = 60
    run_migrations_on_startup: bool = False
    enable_background_consumer: bool = True

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
