"""Insert sample product cards for local development."""
import asyncio
from datetime import datetime, timedelta, timezone

from src.database import async_session, engine
from src.models import Base, ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory


SAMPLE_PRODUCTS = [
    {
        "title": "Portable Neck Fan",
        "category": "Electronics",
        "image_urls": ["https://example.com/neck-fan-1.jpg"],
        "trend_score": 85,
        "trend_velocity": TrendVelocity.accelerating,
        "regions": ["US", "EU", "SEA"],
        "status": ProductStatus.trending,
        "tiktok_data": {
            "advertiser_count": 45,
            "creative_count": 120,
            "ad_duration_days": 14,
            "hashtag_views": 5200000,
            "engagement": {"likes": 320000, "shares": 45000},
        },
        "supplier_data": {
            "listings": [
                {"url": "https://aliexpress.com/item/001.html", "price": 4.50, "order_count": 15000}
            ],
            "best_price": 4.50,
            "best_margin": 7.05,
            "supplier_count": 5,
        },
        "competition": {"saturation_level": "medium", "estimated_sellers": 45, "supplier_count": 5},
        "pricing": {
            "cost_min": 4.50,
            "suggested_sell_price_min": 11.25,
            "suggested_sell_price_max": 13.50,
            "estimated_margin_min": 3.69,
            "estimated_margin_max": 7.05,
            "estimated_margin_percent_min": 32.8,
            "estimated_margin_percent_max": 52.2,
        },
    },
    {
        "title": "LED Galaxy Projector",
        "category": "Home & Garden",
        "image_urls": ["https://example.com/galaxy-1.jpg"],
        "trend_score": 72,
        "trend_velocity": TrendVelocity.stable,
        "regions": ["US", "EU"],
        "status": ProductStatus.trending,
        "tiktok_data": {
            "advertiser_count": 28,
            "creative_count": 75,
            "ad_duration_days": 21,
            "hashtag_views": 3100000,
            "engagement": {"likes": 180000, "shares": 28000},
        },
        "supplier_data": {
            "listings": [
                {"url": "https://aliexpress.com/item/003.html", "price": 8.20, "order_count": 22000}
            ],
            "best_price": 8.20,
            "best_margin": 13.44,
            "supplier_count": 3,
        },
        "competition": {"saturation_level": "medium", "estimated_sellers": 28, "supplier_count": 3},
        "pricing": {
            "cost_min": 8.20,
            "suggested_sell_price_min": 20.50,
            "suggested_sell_price_max": 24.60,
            "estimated_margin_min": 8.47,
            "estimated_margin_max": 13.44,
            "estimated_margin_percent_min": 41.3,
            "estimated_margin_percent_max": 54.6,
        },
    },
    {
        "title": "Magnetic Phone Mount for Car",
        "category": "Accessories",
        "image_urls": ["https://example.com/mount-1.jpg"],
        "trend_score": 45,
        "trend_velocity": TrendVelocity.decelerating,
        "regions": ["US"],
        "status": ProductStatus.declining,
        "tiktok_data": {
            "advertiser_count": 8,
            "creative_count": 15,
            "ad_duration_days": 30,
            "hashtag_views": 800000,
            "engagement": {"likes": 50000, "shares": 7000},
        },
        "supplier_data": {
            "listings": [
                {"url": "https://aliexpress.com/item/005.html", "price": 2.10, "order_count": 8000}
            ],
            "best_price": 2.10,
            "best_margin": 3.93,
            "supplier_count": 12,
        },
        "competition": {"saturation_level": "low", "estimated_sellers": 8, "supplier_count": 12},
        "pricing": {
            "cost_min": 2.10,
            "suggested_sell_price_min": 5.25,
            "suggested_sell_price_max": 6.30,
            "estimated_margin_min": 2.37,
            "estimated_margin_max": 3.93,
            "estimated_margin_percent_min": 45.1,
            "estimated_margin_percent_max": 62.4,
        },
    },
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        for product_data in SAMPLE_PRODUCTS:
            card = ProductCard(**product_data)
            db.add(card)
            await db.flush()

            # Add score history
            now = datetime.now(timezone.utc)
            for i in range(5):
                base_score = product_data["trend_score"] - (5 - i) * 5
                db.add(ScoreHistory(
                    product_card_id=card.id,
                    trend_score=max(0, base_score),
                    recorded_at=now - timedelta(days=5 - i),
                ))

        await db.commit()
        print(f"Seeded {len(SAMPLE_PRODUCTS)} product cards with score history")


if __name__ == "__main__":
    asyncio.run(seed())
