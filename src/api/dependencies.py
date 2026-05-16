from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.user import SubscriptionTier, User
from src.services.auth_service import decode_access_token, get_user_by_id

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def require_tier(minimum: SubscriptionTier):
    tier_order = [SubscriptionTier.free, SubscriptionTier.basic, SubscriptionTier.pro, SubscriptionTier.enterprise]
    def checker(user: User = Depends(get_current_user)):
        user_level = tier_order.index(user.subscription_tier)
        required_level = tier_order.index(minimum)
        if user_level < required_level:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires {minimum.value} tier or higher")
        return user
    return checker
