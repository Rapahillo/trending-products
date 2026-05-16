from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import LoginRequest, RegisterRequest
from src.database import get_db
from src.models.user import User
from src.services.auth_service import authenticate_user, create_access_token, register_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, request.email, request.password)
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    return {
        "status": "ok",
        "data": {
            "id": str(user.id),
            "email": user.email,
            "subscription_tier": user.subscription_tier.value,
            "region_preference": user.region_preference,
        },
    }


@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    return {"status": "ok", "data": {"access_token": token, "token_type": "bearer"}}


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "status": "ok",
        "data": {
            "id": str(user.id),
            "email": user.email,
            "subscription_tier": user.subscription_tier.value,
            "region_preference": user.region_preference,
        },
    }
