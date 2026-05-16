import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.aliexpress import AliExpressCollector
from src.collectors.tiktok import TikTokCollector
from src.models import CollectionRun, CollectionStatus, ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory
from src.pipeline.enricher import enrich_product
from src.pipeline.matcher import find_best_match
from src.pipeline.scorer import (
    calculate_competition,
    calculate_trend_score,
    calculate_velocity,
    determine_status,
)

logger = logging.getLogger(__name__)


async def run_pipeline(db: AsyncSession) -> None:
    """Run the full data pipeline: collect, match, enrich, score, store."""

    # 1. Collect from TikTok
    tiktok_products = []
    tiktok_run = CollectionRun(source="tiktok", status=CollectionStatus.failed)
    db.add(tiktok_run)

    try:
        collector = TikTokCollector()
        tiktok_products = await collector.collect()
        tiktok_run.status = CollectionStatus.success
        tiktok_run.items_collected = len(tiktok_products)
    except Exception as e:
        logger.error(f"TikTok collection failed: {e}")
        tiktok_run.errors = {"message": str(e)}
    finally:
        tiktok_run.completed_at = datetime.now(timezone.utc)

    if not tiktok_products:
        await db.commit()
        return

    # 2. For each TikTok product, search AliExpress and match
    ali_collector = AliExpressCollector()
    matches = []

    for tiktok_product in tiktok_products:
        try:
            ali_products = await ali_collector.search(tiktok_product.title)
            match = find_best_match(tiktok_product, ali_products)
            if match:
                matches.append((match, ali_products))
        except Exception as e:
            logger.warning(f"AliExpress search failed for '{tiktok_product.title}': {e}")

    # 3. Enrich matched products
    enriched_products = []
    for match, ali_products in matches:
        enriched = enrich_product(match, ali_products)
        enriched_products.append(enriched)

    # 4. Score all products together
    all_signals = []
    for match, ali_products in matches:
        signals = {
            "advertiser_count": match.tiktok_product.advertiser_count,
            "ad_duration": match.tiktok_product.ad_duration_days,
            "creative_volume": match.tiktok_product.creative_count,
            "engagement_velocity": match.tiktok_product.hashtag_views,
            "order_volume_growth": match.ali_product.order_count,
            "supplier_availability": len(ali_products),
        }
        all_signals.append(signals)

    # 5. Store product cards
    for i, enriched in enumerate(enriched_products):
        signals = all_signals[i]
        score = calculate_trend_score(signals, all_signals)

        # Check if product already exists (by title match)
        existing_result = await db.execute(
            select(ProductCard).where(ProductCard.title == enriched.title)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update existing card
            existing.trend_score = score
            existing.last_seen_at = datetime.now(timezone.utc)
            existing.tiktok_data = enriched.tiktok_data
            existing.supplier_data = enriched.supplier_data
            existing.competition = enriched.competition
            existing.pricing = enriched.pricing
            existing.regions = enriched.regions

            # Calculate velocity from history
            history_result = await db.execute(
                select(ScoreHistory)
                .where(ScoreHistory.product_card_id == existing.id)
                .order_by(ScoreHistory.recorded_at.asc())
            )
            history = [h.trend_score for h in history_result.scalars().all()]
            history.append(score)

            velocity_str = calculate_velocity(history)
            existing.trend_velocity = TrendVelocity(velocity_str)

            # Determine status
            declining_runs = 0
            if velocity_str == "decelerating":
                for h_score in reversed(history[:-1]):
                    if h_score > score:
                        declining_runs += 1
                    else:
                        break

            competition = calculate_competition(
                signals["advertiser_count"], enriched.supplier_data["supplier_count"]
            )
            existing.competition = {
                **enriched.competition,
                "saturation_level": competition,
            }

            status_str = determine_status(score, velocity_str, declining_runs)
            existing.status = ProductStatus(status_str)

            # Record score history
            db.add(ScoreHistory(product_card_id=existing.id, trend_score=score))
        else:
            # Create new card
            competition = calculate_competition(
                signals["advertiser_count"], enriched.supplier_data["supplier_count"]
            )
            card = ProductCard(
                title=enriched.title,
                category=enriched.category,
                image_urls=enriched.image_urls,
                trend_score=score,
                trend_velocity=TrendVelocity.stable,
                regions=enriched.regions,
                status=ProductStatus.trending,
                tiktok_data=enriched.tiktok_data,
                supplier_data=enriched.supplier_data,
                competition={**enriched.competition, "saturation_level": competition},
                pricing=enriched.pricing,
            )
            db.add(card)
            await db.flush()
            db.add(ScoreHistory(product_card_id=card.id, trend_score=score))

    await db.commit()
