import pytest

from src.collectors.aliexpress import AliExpressProduct
from src.collectors.tiktok import TikTokProduct
from src.pipeline.enricher import enrich_product, EnrichedProduct
from src.pipeline.matcher import Match


@pytest.fixture
def match():
    tiktok = TikTokProduct(
        id="tt_001",
        title="Portable Neck Fan",
        category="Electronics",
        thumbnail="https://example.com/fan.jpg",
        advertiser_count=45,
        creative_count=120,
        ad_duration_days=14,
        hashtag_views=5200000,
        regions=["US", "EU"],
        engagement={"likes": 320000, "shares": 45000},
        sample_creatives=[{"url": "https://example.com/vid.mp4", "thumbnail": "https://example.com/t.jpg"}],
    )
    ali = AliExpressProduct(
        product_id="ali_001",
        title="Portable Bladeless Neck Fan USB Rechargeable",
        url="https://aliexpress.com/item/001.html",
        price=4.50,
        original_price=8.99,
        currency="USD",
        images=["https://example.com/fan1.jpg", "https://example.com/fan2.jpg"],
        order_count=15000,
        rating=4.6,
        seller_name="TechStore",
        seller_rating=95.0,
        shipping=[
            {"region": "US", "cost": 2.50, "days_min": 7, "days_max": 15},
            {"region": "EU", "cost": 3.00, "days_min": 10, "days_max": 20},
        ],
        variants=[{"name": "White", "price": 4.50}, {"name": "Black", "price": 4.50}],
    )
    return Match(tiktok_product=tiktok, ali_product=ali, similarity=0.75)


class TestEnrichProduct:
    def test_returns_enriched_product(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert isinstance(result, EnrichedProduct)

    def test_title_from_tiktok(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.title == "Portable Neck Fan"

    def test_pricing_calculated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        # best price is 4.50, markup 2.5-3.0x
        assert result.pricing["cost_min"] == 4.50
        assert result.pricing["suggested_sell_price_min"] == pytest.approx(11.25)  # 4.50 * 2.5
        assert result.pricing["suggested_sell_price_max"] == pytest.approx(13.50)  # 4.50 * 3.0

    def test_margin_calculated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        # margin at min sell price: 11.25 - 4.50 - 2.50(shipping) - 11.25*0.05(fees) = 3.69
        assert result.pricing["estimated_margin_min"] == pytest.approx(3.69, abs=0.01)

    def test_regions_from_tiktok(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.regions == ["US", "EU"]

    def test_supplier_data_populated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.supplier_data["supplier_count"] == 1
        assert result.supplier_data["best_price"] == 4.50
        assert len(result.supplier_data["listings"]) == 1

    def test_tiktok_data_populated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.tiktok_data["advertiser_count"] == 45
        assert result.tiktok_data["creative_count"] == 120
        assert result.tiktok_data["ad_duration_days"] == 14

    def test_competition_with_multiple_suppliers(self, match):
        extra_supplier = AliExpressProduct(
            product_id="ali_002",
            title="Neck Fan Portable",
            url="https://aliexpress.com/item/002.html",
            price=3.80,
            original_price=7.50,
            currency="USD",
            images=[],
            order_count=8000,
            rating=4.3,
            seller_name="OtherStore",
            seller_rating=92.0,
            shipping=[{"region": "US", "cost": 3.00, "days_min": 10, "days_max": 20}],
            variants=[],
        )
        result = enrich_product(
            match, all_ali_products_for_keyword=[match.ali_product, extra_supplier]
        )
        assert result.supplier_data["supplier_count"] == 2
        assert result.supplier_data["best_price"] == 3.80
