from datetime import datetime, timezone

import redis.asyncio as redis
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from src.database import get_db
from src.models.user import SubscriptionTier, User
from src.services.auth_service import decode_access_token, get_user_by_id

security = HTTPBearer(auto_error=False)

TIER_LIMITS = {
    SubscriptionTier.free: {"queries_per_day": 10, "products_per_query": 5, "regions": 1},
    SubscriptionTier.basic: {"queries_per_day": 100, "products_per_query": 20, "regions": 3},
    SubscriptionTier.pro: {"queries_per_day": 500, "products_per_query": 50, "regions": None},
    SubscriptionTier.enterprise: {"queries_per_day": None, "products_per_query": None, "regions": None},
}

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client


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


async def check_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Check and increment the user's daily query count."""
    limits = TIER_LIMITS[user.subscription_tier]
    max_queries = limits["queries_per_day"]

    if max_queries is None:  # unlimited
        return user

    r = await get_redis()
    key = f"rate_limit:{user.id}:{datetime.now(timezone.utc).date()}"
    current = await r.incr(key)

    if current == 1:
        await r.expire(key, 86400)  # expire after 24h

    if current > max_queries:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily query limit ({max_queries}) exceeded",
        )

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
