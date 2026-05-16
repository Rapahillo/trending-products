import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.database import get_db
from src.models.user import User
from src.services.product_service import get_product, get_product_history, list_products

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _serialize_product(product) -> dict:
    return {
        "id": str(product.id),
        "title": product.title,
        "category": product.category,
        "image_urls": product.image_urls,
        "trend_score": product.trend_score,
        "trend_velocity": product.trend_velocity.value,
        "first_seen_at": product.first_seen_at.isoformat(),
        "last_seen_at": product.last_seen_at.isoformat(),
        "regions": product.regions,
        "status": product.status.value,
        "tiktok_data": product.tiktok_data,
        "supplier_data": product.supplier_data,
        "competition": product.competition,
        "pricing": product.pricing,
    }


@router.get("")
async def list_products_endpoint(
    region: str | None = Query(None),
    category: str | None = Query(None),
    status_filter: str = Query("trending", alias="status"),
    min_score: int | None = Query(None, ge=0, le=100),
    velocity: str | None = Query(None),
    saturation: str | None = Query(None),
    min_margin: float | None = Query(None),
    sort: str = Query("score"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    products, total = await list_products(
        db, page=page, limit=limit, region=region, category=category,
        status=status_filter, min_score=min_score, velocity=velocity,
        saturation=saturation, min_margin=min_margin, sort=sort, order=order,
    )
    return {
        "status": "ok",
        "data": [_serialize_product(p) for p in products],
        "meta": {"page": page, "limit": limit, "total": total},
    }


@router.get("/{product_id}")
async def get_product_endpoint(
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return {"status": "ok", "data": _serialize_product(product)}


@router.get("/{product_id}/history")
async def get_history_endpoint(
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    history = await get_product_history(db, product_id)
    return {
        "status": "ok",
        "data": [
            {"trend_score": h.trend_score, "recorded_at": h.recorded_at.isoformat()}
            for h in history
        ],
    }
