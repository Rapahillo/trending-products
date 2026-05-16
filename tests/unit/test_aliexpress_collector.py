import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.collectors.aliexpress import AliExpressCollector, AliExpressProduct

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestAliExpressCollector:
    @pytest.fixture
    def fixture_data(self):
        with open(FIXTURES_DIR / "aliexpress_search_response.json") as f:
            return json.load(f)

    @pytest.fixture
    def collector(self):
        return AliExpressCollector()

    def test_parse_products(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        assert len(products) == 3
        assert all(isinstance(p, AliExpressProduct) for p in products)

    def test_product_fields(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert product.title == "Portable Bladeless Neck Fan USB Rechargeable"
        assert product.price == 4.50
        assert product.order_count == 15000
        assert product.rating == 4.6
        assert len(product.shipping) == 3

    def test_product_shipping(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        us_shipping = next(s for s in product.shipping if s["region"] == "US")
        assert us_shipping["cost"] == 2.50
        assert us_shipping["days_min"] == 7

    def test_product_variants(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert len(product.variants) == 3
        assert product.variants[0]["name"] == "White"

    def test_empty_results(self, collector):
        empty = {"results": []}
        products = collector.parse_response(empty)
        assert products == []

    @patch("src.collectors.aliexpress.httpx.AsyncClient")
    async def test_search_by_keyword(self, mock_client_class, collector, fixture_data):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_response = AsyncMock()
        mock_response.json.return_value = fixture_data
        mock_response.raise_for_status = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        products = await collector.search("portable neck fan")
        assert len(products) == 3
