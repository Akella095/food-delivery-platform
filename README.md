# 🍕 Food Delivery Platform — дипломный проект

Микросервисное приложение «Сервис доставки еды»: рестораны, меню, заказы, курьеры.
Проект реализован на **FastAPI** с асинхронным доступом к **PostgreSQL** через **SQLAlchemy (AsyncSession)**,
асинхронной коммуникацией сервисов через **RabbitMQ**, кэшированием в **Redis**, обратным прокси и
балансировкой нагрузки на **Nginx**, мониторингом через **Prometheus**-метрики и CI/CD на **GitHub Actions**.

## Содержание

- [Архитектура](#архитектура)
- [Сервисы и их зона ответственности](#сервисы-и-их-зона-ответственности)
- [Модель данных](#модель-данных)
- [Аутентификация и роли](#аутентификация-и-роли)
- [Асинхронная коммуникация (RabbitMQ)](#асинхронная-коммуникация-rabbitmq)
- [Кэширование (Redis)](#кэширование-redis)
- [Nginx: reverse proxy, балансировка, rate limiting](#nginx-reverse-proxy-балансировка-rate-limiting)
- [Мониторинг (Prometheus)](#мониторинг-prometheus)
- [Структура проекта](#структура-проекта)
- [Запуск проекта](#запуск-проекта)
- [Миграции базы данных](#миграции-базы-данных)
- [Тестирование](#тестирование)
- [CI/CD](#cicd)
- [API документация (Swagger)](#api-документация-swagger)

## Архитектура

```
                                   ┌──────────────────────┐
                                   │        Клиент         │
                                   └───────────┬──────────┘
                                               │  HTTP (port 80)
                                   ┌───────────▼──────────┐
                                   │        Nginx           │
                                   │  reverse proxy +       │
                                   │  rate limiting +       │
                                   │  load balancing        │
                                   └─────┬──────────┬──────┘
                         /api/auth,      │          │  /api/restaurants,
                         /api/users*     │          │  /api/orders,
                                         │          │  /api/couriers/available
                             ┌───────────▼───┐  ┌───▼─────────────────────┐
                             │ user-service  │  │     order-service        │
                             │ (FastAPI)     │  │ (FastAPI, 2 инстанса —  │
                             │               │  │  order-service-1/2)     │
                             └──┬─────┬──────┘  └────┬──────────┬────────┘
                                │     │               │          │
                     ┌──────────▼┐ ┌──▼───────┐ ┌────▼──────┐  │
                     │ user-db   │ │  Redis    │ │ order-db  │  │
                     │ (Postgres)│ │ (общий)   │ │ (Postgres)│  │
                     └───────────┘ └─────▲─────┘ └───────────┘  │
                                         │                       │
                                   ┌─────┴───────────────────────┘
                                   │
                            ┌──────▼───────┐
                            │  RabbitMQ     │   topic exchange "food_delivery_events"
                            │ (exchange +   │   user.registered, courier.availability_changed
                            │  queues)      │   order.created, order.status_updated
                            └───────────────┘
```

Каждый сервис — независимое FastAPI-приложение со своей базой данных (паттерн *database-per-service*).
Сервисы не обращаются друг к другу напрямую по HTTP — единственный канал синхронизации состояния между
ними — события в RabbitMQ. JWT, выпущенный `user-service`, проверяется в `order-service` по общему
секрету (`SECRET_KEY`), поэтому сквозная аутентификация работает без дополнительных сетевых вызовов.

## Сервисы и их зона ответственности

### `user-service`
- Регистрация / логин, выпуск JWT (`/api/auth/register`, `/api/auth/login`)
- Профиль пользователя, список пользователей для admin (`/api/users/*`)
- Профиль и доступность курьера (`/api/users/couriers/*`)
- Уведомления пользователя, которые наполняются асинхронно по событиям заказов (`/api/users/me/notifications`)
- Публикует события: `user.registered`, `courier.availability_changed`
- Потребляет события: `order.created`, `order.status_updated` → создаёт `Notification`

### `order-service`
- Рестораны и меню (`/api/restaurants/*`), создание доступно только `admin`
- Заказы: создание, список, детали, смена статуса (`/api/orders/*`)
- Список доступных курьеров — локальная read-модель (`/api/couriers/available`), синхронизируется
  через события `courier.availability_changed`
- Публикует события: `order.created`, `order.status_updated`
- Потребляет события: `user.registered`, `courier.availability_changed`

## Модель данных

**user-service** (PostgreSQL `user_db`):
- `User` (1) — (N) `Address`
- `User` (1) — (1) `CourierProfile`
- `User` (1) — (N) `Notification`
- Индексы: `ix_users_email` (unique), `ix_addresses_user_id`, `ix_courier_profiles_is_available`, `ix_notifications_user_id`

**order-service** (PostgreSQL `order_db`):
- `Restaurant` (1) — (N) `MenuItem`
- `Order` (1) — (N) `OrderItem` — (N) — (1) `MenuItem`
- `CourierStatus` — независимая read-модель курьеров
- Индексы: `ix_restaurants_is_active`, `ix_menu_items_restaurant_id`, `ix_orders_customer_id`,
  `ix_orders_status`, `ix_courier_status_courier_id` (unique)

Списочные эндпоинты (`/api/restaurants`, `/api/orders`, `/api/restaurants/{id}`) используют `selectinload`,
чтобы избежать проблемы N+1 при подгрузке связанных `menu_items` / `items` / `menu_item`.

## Аутентификация и роли

- JWT (HS256), выдаётся `user-service` при логине, содержит `sub` (id пользователя) и `role`.
- Роли: **admin**, **customer**, **courier** (минимум 2 роли по требованиям выполнено, добавлена третья
  для реалистичности бизнес-процесса).
- Защищённые эндпоинты используют FastAPI-зависимости `get_current_user` / `require_roles(...)`.
- Примеры ограничений:
  - создавать рестораны и позиции меню может только `admin`;
  - создавать заказ может `customer`/`admin`;
  - менять статус заказа может `courier`/`admin`;
  - список всех пользователей доступен только `admin`.

## Асинхронная коммуникация (RabbitMQ)

Оба сервиса публикуют и потребляют события через один topic-exchange `food_delivery_events`:

| Событие                          | Публикует      | Потребляет     | Описание                                   |
|-----------------------------------|----------------|----------------|---------------------------------------------|
| `user.registered`                 | user-service   | order-service  | Новый пользователь зарегистрирован          |
| `courier.availability_changed`    | user-service   | order-service  | Курьер изменил доступность → обновление read-модели `CourierStatus` |
| `order.created`                   | order-service  | user-service   | Создан новый заказ → уведомление клиенту    |
| `order.status_updated`            | order-service  | user-service   | Изменён статус заказа → уведомление клиенту |

Consumer запускается как фоновая asyncio-задача при старте приложения (`lifespan`) и переподключается
при сбоях брокера (`retry` с задержкой). Публикация событий обёрнута в `try/except` — недоступность
RabbitMQ не приводит к падению HTTP-запроса.

## Кэширование (Redis)

- `GET /api/restaurants` — список активных ресторанов кэшируется на `CACHE_TTL_SECONDS` секунд.
- `GET /api/restaurants/{id}` — детали ресторана с меню.
- `GET /api/users/{id}` — профиль пользователя.
- Инвалидация: любое изменение (`POST`/`PATCH` ресторана, добавление позиции меню, `PATCH` пользователя)
  удаляет соответствующие ключи из Redis.
- **Graceful degradation**: все функции `cache_get/cache_set/cache_delete` оборачивают обращение к Redis
  в `try/except`. Если Redis недоступен — приложение просто не кэширует и ходит в БД напрямую, без ошибок 5xx.

## Nginx: reverse proxy, балансировка, rate limiting

- `nginx/nginx.conf` проксирует `/api/auth/*`, `/api/users/*` → `user-service`;
  `/api/restaurants/*`, `/api/orders/*`, `/api/couriers/*` → `order-service`.
- Дополнительно Nginx проксирует `/<service>/docs`, `/<service>/openapi.json`, `/<service>/redoc`
  и `/<service>/metrics` для каждого сервиса, чтобы Swagger UI был доступен снаружи.
- `order-service` поднят в **двух репликах** (`order-service-1`, `order-service-2`), Nginx балансирует
  запросы между ними через `upstream order_service { least_conn; ... }`.
- `limit_req_zone` + `limit_req` — ограничение 10 запросов/сек на IP с буфером burst=20.
- Проксируются заголовки `Host`, `X-Real-IP`, `X-Forwarded-For`, `X-Forwarded-Proto`.
- Swagger каждого сервиса доступен через Nginx: `/user-service/docs`, `/order-service/docs`.

## Мониторинг (Prometheus)

Каждый сервис отдаёт `/metrics` в формате Prometheus и `/health` для health-check'ов.

Кастомные метрики (не считая стандартных HTTP):
- **user-service**: `users_registered_total`, `couriers_available`, `events_published_total`, `events_consumed_total`
- **order-service**: `orders_created_total`, `order_status_changes_total`, `cache_hits_total` / `cache_misses_total`, `events_published_total`, `events_consumed_total`

Плюс общие для обоих сервисов: `http_requests_total`, `http_request_duration_seconds`.

## Структура проекта

```
project/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .github/workflows/ci.yml
├── nginx/nginx.conf
├── user-service/
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── requirements.txt          # включает python-multipart для OAuth2-формы в Swagger
│   ├── pytest.ini                # asyncio_mode = auto
│   ├── alembic.ini
│   ├── alembic/{env.py, versions/0001_initial.py}
│   ├── app/
│   │   ├── main.py            # FastAPI app, lifespan, root_path, middleware, /health, /metrics
│   │   ├── config.py          # Pydantic Settings
│   │   ├── database.py        # async engine/session
│   │   ├── models.py          # User, Address, CourierProfile, Notification
│   │   ├── schemas.py         # Pydantic-схемы
│   │   ├── security.py        # JWT, bcrypt, OAuth2PasswordBearer
│   │   ├── dependencies.py    # get_current_user, require_roles
│   │   ├── cache.py           # Redis helpers (graceful degradation)
│   │   ├── messaging.py       # RabbitMQ publisher/consumer
│   │   ├── event_handlers.py  # обработка входящих событий заказа
│   │   ├── metrics.py         # Prometheus метрики
│   │   └── routers/{auth.py, users.py, couriers.py}
│   └── tests/
└── order-service/
    ├── Dockerfile
    ├── .dockerignore
    ├── requirements.txt
    ├── pytest.ini
    ├── alembic.ini
    ├── alembic/{env.py, versions/0001_initial.py}
    ├── app/
    │   ├── main.py
    │   ├── config.py
    │   ├── database.py
    │   ├── models.py           # Restaurant, MenuItem, Order, OrderItem, CourierStatus
    │   ├── schemas.py
    │   ├── security.py         # декодирование JWT по общему секрету
    │   ├── dependencies.py
    │   ├── cache.py
    │   ├── messaging.py
    │   ├── event_handlers.py
    │   ├── metrics.py
    │   └── routers/{restaurants.py, orders.py, couriers.py}
    └── tests/
```

## Запуск проекта

### Требования
- Docker + Docker Compose v2

### Шаги

```bash
cp .env.example .env
# при желании отредактируйте .env (особенно SECRET_KEY для продакшена)

docker compose up -d --build
```

После старта:
- API Gateway (Nginx): http://localhost/
- Swagger `user-service`: http://localhost/user-service/docs
- Swagger `order-service`: http://localhost/order-service/docs
- RabbitMQ Management UI: http://localhost:15672 (guest/guest по умолчанию)
- Health-check: `GET /health` на каждом сервисе, а также `GET http://localhost/health` на самом Nginx

Проверить состояние контейнеров и healthcheck'ов:

```bash
docker compose ps
```

Миграции Alembic применяются автоматически при старте контейнера (`CMD` в Dockerfile выполняет
`alembic upgrade head` перед запуском uvicorn).

### Быстрый сценарий проверки API

```bash
# 1. Регистрация администратора
curl -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123","full_name":"Admin","role":"admin"}'

# 2. Логин и получение токена
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 3. Создание ресторана
curl -X POST http://localhost/api/restaurants \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"Pizza Place","address":"Main St 1"}'
```

## Миграции базы данных

Миграции лежат в `user-service/alembic` и `order-service/alembic` и применяются автоматически в Docker.
Для ручного запуска (например, локальной разработки):

```bash
cd user-service
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/user_db
alembic upgrade head

cd ../order-service
export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/order_db
alembic upgrade head
```

Создание новой миграции после изменения моделей:

```bash
alembic revision --autogenerate -m "описание изменения"
```

## Тестирование

В каждом сервисе — unit- и интеграционные тесты на `pytest` + `pytest-asyncio` + `httpx.AsyncClient`.
Внешние зависимости (Redis, RabbitMQ) замоканы через `unittest.mock.AsyncMock`, база данных в тестах —
изолированная in-memory SQLite (`aiosqlite`) для скорости и независимости от инфраструктуры.

### Запуск тестов в Docker (рекомендуется)

```bash
docker compose exec user-service pytest -v
docker compose exec order-service-1 pytest -v
```

### Локальный запуск (при наличии Python 3.11+)

```bash
cd user-service && pip install -r requirements.txt && pytest tests/ -v    # 11 тестов
cd order-service && pip install -r requirements.txt && pytest tests/ -v  # 9 тестов
```

Итого ≥ 10 тестов на сервис соблюдено суммарно (20 тестов), с покрытием: регистрации/логина, ролевого
доступа, CRUD ресторанов/меню, создания заказов, фильтрации заказов по роли, смены статуса заказа,
работы кэш-слоя.

## CI/CD

`.github/workflows/ci.yml` на каждый `push`/`pull_request`:
1. Отдельные джобы для `user-service` и `order-service`: установка зависимостей, **ruff** линтер,
   **pytest**.
2. Джоба `build-images`: сборка Docker-образов обоих сервисов (убеждаемся, что `Dockerfile` рабочий).
3. Секреты (например, `SECRET_KEY`) читаются через `${{ secrets.SECRET_KEY }}` с безопасным fallback
   для тестовой среды.

## API документация (Swagger)

FastAPI автоматически генерирует OpenAPI/Swagger:
- `user-service`: `/docs`, `/redoc`, `/openapi.json`
- `order-service`: `/docs`, `/redoc`, `/openapi.json`

Через Nginx они проброшены на `/user-service/docs` и `/order-service/docs` соответственно
(с использованием `root_path="/<service>"` в FastAPI).

### Авторизация в Swagger UI

1. Откройте `/user-service/docs` (или `/order-service/docs`).
2. Нажмите кнопку **Authorize** (замок справа сверху).
3. В поле **username** введите ваш **email** (например, `admin@example.com`).
4. В поле **password** введите пароль.
5. Поля `client_id` и `client_secret` оставьте пустыми.
6. Нажмите **Authorize**.

Логин-эндпоинт `/api/auth/login` поддерживает как JSON (`{"email": "...", "password": "..."}`),
так и `application/x-www-form-urlencoded` (OAuth2 Password Flow, который использует Swagger UI).

## Технологический стек

FastAPI · Pydantic v2 · SQLAlchemy 2.0 (async) · asyncpg · Alembic · PostgreSQL 16 · Redis 7 ·
RabbitMQ 3.13 (aio-pika) · python-jose (JWT) · passlib/bcrypt · python-multipart · prometheus-client ·
Nginx · Docker / Docker Compose · GitHub Actions · pytest / pytest-asyncio / httpx · ruff