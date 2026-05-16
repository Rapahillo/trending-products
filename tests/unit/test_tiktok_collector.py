import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.collectors.tiktok import TikTokCollector, TikTokProduct

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestTikTokCollector:
    @pytest.fixture
    def fixture_data(self):
        with open(FIXTURES_DIR / "tiktok_trending_response.json") as f:
            return json.load(f)

    @pytest.fixture
    def collector(self):
        return TikTokCollector()

    def test_parse_products(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        assert len(products) == 3
        assert all(isinstance(p, TikTokProduct) for p in products)

    def test_product_fields(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert product.title == "Portable Neck Fan"
        assert product.category == "Electronics"
        assert product.advertiser_count == 45
        assert product.creative_count == 120
        assert product.ad_duration_days == 14
        assert product.hashtag_views == 5200000
        assert product.regions == ["US", "EU", "SEA"]

    def test_product_engagement(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert product.engagement["likes"] == 320000
        assert product.engagement["shares"] == 45000

    def test_empty_response(self, collector):
        empty = {"code": 0, "data": {"products": []}}
        products = collector.parse_response(empty)
        assert products == []

    def test_malformed_response_raises(self, collector):
        with pytest.raises(ValueError, match="Invalid TikTok response"):
            collector.parse_response({"code": 1, "message": "error"})

    @patch("src.collectors.tiktok.httpx.AsyncClient")
    async def test_collect_calls_api(self, mock_client_class, collector, fixture_data):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_response = AsyncMock()
        mock_response.json.return_value = fixture_data
        mock_response.raise_for_status = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        products = await collector.collect()
        assert len(products) == 3
        mock_client.get.assert_called_once()
