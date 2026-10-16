from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.messaging import EVENT_USER_REGISTERED, publish_event
from app.metrics import USERS_REGISTERED_TOTAL
from app.models import User
from app.schemas import Token, UserCreate, UserOut
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(payload: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    existing = await db.execute(select(User).where(User.email == payload.email))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
    )
    db.add(user)
    try:
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create user"
        ) from exc
    await db.refresh(user)

    USERS_REGISTERED_TOTAL.labels(user.role.value).inc()
    await publish_event(
        EVENT_USER_REGISTERED,
        {"user_id": user.id, "email": user.email, "role": user.role.value},
    )
    return user


@router.post("/login", response_model=Token)
async def login(request: Request, db: AsyncSession = Depends(get_db)) -> Token:
    """
    Поддерживает два формата:
    - JSON: {"email": "...", "password": "..."} — для curl/фронтенда
    - form-data: username=...&password=... — для Swagger UI (OAuth2 Password Flow)
    """
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        body = await request.json()
        email = body.get("email")
        password = body.get("password")
    else:
        form = await request.form()
        # Swagger OAuth2 шлёт поле "username", поэтому мапим его на email
        email = form.get("username") or form.get("email")
        password = form.get("password")

    if not email or not password:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email and password are required",
        )

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    token = create_access_token(subject=user.id, role=user.role.value)
    return Token(access_token=token)