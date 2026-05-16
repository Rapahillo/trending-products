from dataclasses import dataclass, field

import yaml

from config.settings import settings
from src.collectors.aliexpress import AliExpressProduct
from src.pipeline.matcher import Match


@dataclass
class EnrichedProduct:
    title: str
    category: str
    image_urls: list[str]
    regions: list[str]
    tiktok_data: dict
    supplier_data: dict
    competition: dict
    pricing: dict


def _load_margin_config() -> dict:
    with open(settings.scoring_weights_path) as f:
        config = yaml.safe_load(f)
    return config["margin"]


def enrich_product(
    match: Match,
    all_ali_products_for_keyword: list[AliExpressProduct],
) -> EnrichedProduct:
    """Enrich a matched product with pricing, competition, and supplier data."""
    margin_config = _load_margin_config()
    markup_min = margin_config["markup_min"]
    markup_max = margin_config["markup_max"]
    platform_fee = margin_config["platform_fee_percent"] / 100

    tiktok = match.tiktok_product
    ali = match.ali_product

    # Supplier data from all matching AliExpress products
    listings = []
    for product in all_ali_products_for_keyword:
        listings.append({
            "product_id": product.product_id,
            "url": product.url,
            "price": product.price,
            "shipping": product.shipping,
            "order_count": product.order_count,
            "rating": product.rating,
            "seller_name": product.seller_name,
            "variants": product.variants,
        })

    best_price = min(p.price for p in all_ali_products_for_keyword)
    best_shipping_cost = 0.0
    if ali.shipping:
        best_shipping_cost = min(s["cost"] for s in ali.shipping)

    # Pricing
    sell_min = best_price * markup_min
    sell_max = best_price * markup_max
    margin_min = sell_min - best_price - best_shipping_cost - (sell_min * platform_fee)
    margin_max = sell_max - best_price - best_shipping_cost - (sell_max * platform_fee)
    margin_percent_min = (margin_min / sell_min * 100) if sell_min > 0 else 0
    margin_percent_max = (margin_max / sell_max * 100) if sell_max > 0 else 0

    # Images: prefer AliExpress product images, fallback to TikTok thumbnail
    image_urls = ali.images if ali.images else [tiktok.thumbnail]

    return EnrichedProduct(
        title=tiktok.title,
        category=tiktok.category,
        image_urls=image_urls,
        regions=tiktok.regions,
        tiktok_data={
            "advertiser_count": tiktok.advertiser_count,
            "creative_count": tiktok.creative_count,
            "ad_duration_days": tiktok.ad_duration_days,
            "hashtag_views": tiktok.hashtag_views,
            "engagement": tiktok.engagement,
            "sample_creatives": tiktok.sample_creatives,
        },
        supplier_data={
            "listings": listings,
            "best_price": best_price,
            "best_margin": margin_max,
            "supplier_count": len(all_ali_products_for_keyword),
        },
        competition={
            "estimated_sellers": tiktok.advertiser_count,
            "supplier_count": len(all_ali_products_for_keyword),
        },
        pricing={
            "cost_min": best_price,
            "cost_max": max(p.price for p in all_ali_products_for_keyword),
            "suggested_sell_price_min": sell_min,
            "suggested_sell_price_max": sell_max,
            "estimated_margin_min": round(margin_min, 2),
            "estimated_margin_max": round(margin_max, 2),
            "estimated_margin_percent_min": round(margin_percent_min, 1),
            "estimated_margin_percent_max": round(margin_percent_max, 1),
        },
    )
