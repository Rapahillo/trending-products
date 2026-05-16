import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory


@pytest.fixture
async def sample_products(db: AsyncSession):
    products = [
        ProductCard(
            title="Portable Neck Fan",
            category="Electronics",
            image_urls=["https://example.com/fan.jpg"],
            trend_score=85,
            trend_velocity=TrendVelocity.accelerating,
            regions=["US", "EU", "SEA"],
            status=ProductStatus.trending,
            tiktok_data={"advertiser_count": 45, "creative_count": 120},
            supplier_data={"best_price": 4.50, "supplier_count": 5, "listings": []},
            competition={"saturation_level": "medium", "estimated_sellers": 45},
            pricing={"suggested_sell_price_min": 11.25, "estimated_margin_min": 3.69},
        ),
        ProductCard(
            title="LED Galaxy Projector",
            category="Home & Garden",
            image_urls=["https://example.com/projector.jpg"],
            trend_score=62,
            trend_velocity=TrendVelocity.stable,
            regions=["US", "EU"],
            status=ProductStatus.trending,
            tiktok_data={"advertiser_count": 28, "creative_count": 75},
            supplier_data={"best_price": 8.20, "supplier_count": 3, "listings": []},
            competition={"saturation_level": "medium", "estimated_sellers": 28},
            pricing={"suggested_sell_price_min": 20.50, "estimated_margin_min": 8.47},
        ),
        ProductCard(
            title="Old Trend Widget",
            category="Gadgets",
            image_urls=[],
            trend_score=15,
            trend_velocity=TrendVelocity.decelerating,
            regions=["US"],
            status=ProductStatus.expired,
            tiktok_data={"advertiser_count": 2, "creative_count": 3},
            supplier_data={"best_price": 2.00, "supplier_count": 1, "listings": []},
            competition={"saturation_level": "low", "estimated_sellers": 2},
            pricing={"suggested_sell_price_min": 5.00, "estimated_margin_min": 1.50},
        ),
    ]
    for p in products:
        db.add(p)
    await db.commit()
    for p in products:
        await db.refresh(p)
    return products


@pytest.fixture
async def auth_headers(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={"email": "products@test.com", "password": "testpass"})
    login = await client.post("/api/v1/auth/login", json={"email": "products@test.com", "password": "testpass"})
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestListProducts:
    async def test_list_default_returns_trending(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert all(p["status"] == "trending" for p in data["data"])

    async def test_list_with_region_filter(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products?region=SEA", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1
        assert response.json()["data"][0]["title"] == "Portable Neck Fan"

    async def test_list_with_min_score(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products?min_score=70", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 1

    async def test_list_sorted_by_score_desc(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products?sort=score&order=desc", headers=auth_headers)
        scores = [p["trend_score"] for p in response.json()["data"]]
        assert scores == sorted(scores, reverse=True)

    async def test_list_pagination(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products?limit=1&page=1", headers=auth_headers)
        data = response.json()
        assert len(data["data"]) == 1
        assert data["meta"]["total"] == 2

    async def test_list_requires_auth(self, client, sample_products):
        response = await client.get("/api/v1/products")
        assert response.status_code == 401


class TestGetProduct:
    async def test_get_by_id(self, client, auth_headers, sample_products):
        product_id = str(sample_products[0].id)
        response = await client.get(f"/api/v1/products/{product_id}", headers=auth_headers)
        assert response.status_code == 200
        assert response.json()["data"]["title"] == "Portable Neck Fan"

    async def test_get_nonexistent(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/products/{fake_id}", headers=auth_headers)
        assert response.status_code == 404


class TestGetProductHistory:
    async def test_get_history(self, client, auth_headers, sample_products, db: AsyncSession):
        product = sample_products[0]
        for i, score in enumerate([60, 70, 80, 85]):
            db.add(ScoreHistory(
                product_card_id=product.id,
                trend_score=score,
                recorded_at=datetime.now(timezone.utc) - timedelta(days=3 - i),
            ))
        await db.commit()
        response = await client.get(f"/api/v1/products/{product.id}/history", headers=auth_headers)
        assert response.status_code == 200
        assert len(response.json()["data"]) == 4
