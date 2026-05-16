from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user, require_tier
from src.api.schemas import LoginRequest, RegisterRequest
from src.database import get_db
from src.models.user import SubscriptionTier, User
from src.services.auth_service import authenticate_user, create_access_token, create_api_key, delete_api_key, register_user

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


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def generate_api_key_endpoint(
    name: str = "default",
    user: User = Depends(require_tier(SubscriptionTier.enterprise)),
    db: AsyncSession = Depends(get_db),
):
    api_key, raw_key = await create_api_key(db, str(user.id), name)
    return {
        "status": "ok",
        "data": {
            "id": str(api_key.id),
            "name": api_key.name,
            "key": raw_key,  # Only shown once
            "created_at": api_key.created_at.isoformat(),
        },
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(require_tier(SubscriptionTier.enterprise)),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_api_key(db, key_id, str(user.id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"status": "ok", "data": {"deleted": True}}
