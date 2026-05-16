import pytest

from src.collectors.aliexpress import AliExpressProduct
from src.collectors.tiktok import TikTokProduct
from src.pipeline.matcher import (
    Match,
    calculate_jaccard_similarity,
    find_best_match,
    tokenize,
)


class TestTokenize:
    def test_basic_tokenization(self):
        tokens = tokenize("Portable Neck Fan")
        assert tokens == {"portable", "neck", "fan"}

    def test_removes_common_words(self):
        tokens = tokenize("The Best USB Rechargeable Neck Fan for You")
        assert "the" not in tokens
        assert "for" not in tokens
        assert "you" not in tokens

    def test_lowercases(self):
        tokens = tokenize("LED Galaxy PROJECTOR")
        assert tokens == {"led", "galaxy", "projector"}


class TestJaccardSimilarity:
    def test_identical_sets(self):
        result = calculate_jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"})
        assert result == 1.0

    def test_no_overlap(self):
        result = calculate_jaccard_similarity({"a", "b"}, {"c", "d"})
        assert result == 0.0

    def test_partial_overlap(self):
        result = calculate_jaccard_similarity({"portable", "neck", "fan"}, {"portable", "bladeless", "neck", "fan", "usb", "rechargeable"})
        # intersection: {portable, neck, fan} = 3
        # union: {portable, neck, fan, bladeless, usb, rechargeable} = 6
        assert result == pytest.approx(0.5)

    def test_high_overlap(self):
        result = calculate_jaccard_similarity(
            {"led", "galaxy", "projector"},
            {"galaxy", "star", "projector", "led", "night", "light"},
        )
        # intersection: {led, galaxy, projector} = 3
        # union: {led, galaxy, projector, star, night, light} = 6
        assert result == pytest.approx(0.5)


class TestFindBestMatch:
    @pytest.fixture
    def tiktok_product(self):
        return TikTokProduct(
            id="tt_001",
            title="Portable Neck Fan",
            category="Electronics",
            thumbnail="https://example.com/fan.jpg",
            advertiser_count=45,
            creative_count=120,
            ad_duration_days=14,
            hashtag_views=5200000,
            regions=["US", "EU"],
            engagement={"likes": 320000},
            sample_creatives=[],
        )

    @pytest.fixture
    def ali_products(self):
        return [
            AliExpressProduct(
                product_id="ali_001",
                title="Portable Bladeless Neck Fan USB Rechargeable",
                url="https://aliexpress.com/item/001.html",
                price=4.50,
                original_price=8.99,
                currency="USD",
                images=["https://example.com/fan.jpg"],
                order_count=15000,
                rating=4.6,
                seller_name="TechStore",
                seller_rating=95.0,
                shipping=[{"region": "US", "cost": 2.50, "days_min": 7, "days_max": 15}],
                variants=[],
            ),
            AliExpressProduct(
                product_id="ali_099",
                title="Wireless Bluetooth Headphones Over Ear",
                url="https://aliexpress.com/item/099.html",
                price=12.00,
                original_price=25.00,
                currency="USD",
                images=[],
                order_count=5000,
                rating=4.2,
                seller_name="AudioShop",
                seller_rating=90.0,
                shipping=[{"region": "US", "cost": 3.00, "days_min": 10, "days_max": 20}],
                variants=[],
            ),
        ]

    def test_finds_matching_product(self, tiktok_product, ali_products):
        match = find_best_match(tiktok_product, ali_products)
        assert match is not None
        assert match.ali_product.product_id == "ali_001"

    def test_returns_none_for_no_match(self, tiktok_product):
        unrelated = [
            AliExpressProduct(
                product_id="ali_999",
                title="Yoga Mat Non-Slip Exercise",
                url="https://aliexpress.com/item/999.html",
                price=10.00,
                original_price=20.00,
                currency="USD",
                images=[],
                order_count=3000,
                rating=4.5,
                seller_name="FitShop",
                seller_rating=93.0,
                shipping=[],
                variants=[],
            ),
        ]
        match = find_best_match(tiktok_product, unrelated)
        assert match is None

    def test_match_contains_similarity_score(self, tiktok_product, ali_products):
        match = find_best_match(tiktok_product, ali_products)
        assert match is not None
        assert 0.0 < match.similarity <= 1.0
