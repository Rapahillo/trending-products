import uuid

from sqlalchemy import Select, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory


def _build_product_query(
    region: str | None = None,
    category: str | None = None,
    status: str = "trending",
    min_score: int | None = None,
    velocity: str | None = None,
    saturation: str | None = None,
    min_margin: float | None = None,
    sort: str = "score",
    order: str = "desc",
) -> Select:
    query = select(ProductCard)

    if status:
        query = query.where(ProductCard.status == ProductStatus(status))
    if region:
        query = query.where(ProductCard.regions.any(region))
    if category:
        query = query.where(ProductCard.category == category)
    if min_score is not None:
        query = query.where(ProductCard.trend_score >= min_score)
    if velocity:
        query = query.where(ProductCard.trend_velocity == TrendVelocity(velocity))
    if saturation:
        query = query.where(
            ProductCard.competition["saturation_level"].astext == saturation
        )
    if min_margin is not None:
        query = query.where(
            ProductCard.pricing["estimated_margin_min"].astext.cast(float) >= min_margin
        )

    sort_column_map = {
        "score": ProductCard.trend_score,
        "velocity": ProductCard.trend_velocity,
        "margin": ProductCard.pricing["estimated_margin_min"].astext,
        "first_seen": ProductCard.first_seen_at,
        "last_seen": ProductCard.last_seen_at,
    }
    sort_col = sort_column_map.get(sort, ProductCard.trend_score)
    if order == "asc":
        query = query.order_by(sort_col)
    else:
        query = query.order_by(desc(sort_col))

    return query


async def list_products(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    **filters,
) -> tuple[list[ProductCard], int]:
    query = _build_product_query(**filters)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    products = list(result.scalars().all())
    return products, total


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> ProductCard | None:
    result = await db.execute(select(ProductCard).where(ProductCard.id == product_id))
    return result.scalar_one_or_none()


async def get_product_history(
    db: AsyncSession, product_id: uuid.UUID
) -> list[ScoreHistory]:
    result = await db.execute(
        select(ScoreHistory)
        .where(ScoreHistory.product_card_id == product_id)
        .order_by(ScoreHistory.recorded_at.asc())
    )
    return list(result.scalars().all())
