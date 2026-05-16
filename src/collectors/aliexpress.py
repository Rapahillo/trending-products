from dataclasses import dataclass, field

import httpx

from config.settings import settings
from src.collectors.base import BaseCollector


@dataclass
class AliExpressProduct:
    product_id: str
    title: str
    url: str
    price: float
    original_price: float
    currency: str
    images: list[str]
    order_count: int
    rating: float
    seller_name: str
    seller_rating: float
    shipping: list[dict]
    variants: list[dict] = field(default_factory=list)


class AliExpressCollector(BaseCollector):
    def parse_response(self, data: dict) -> list[AliExpressProduct]:
        products = []
        for item in data.get("results", []):
            product = AliExpressProduct(
                product_id=item["product_id"],
                title=item["title"],
                url=item["url"],
                price=item["price"],
                original_price=item.get("original_price", item["price"]),
                currency=item.get("currency", "USD"),
                images=item.get("images", []),
                order_count=item.get("order_count", 0),
                rating=item.get("rating", 0.0),
                seller_name=item.get("seller_name", ""),
                seller_rating=item.get("seller_rating", 0.0),
                shipping=item.get("shipping", []),
                variants=item.get("variants", []),
            )
            products.append(product)
        return products

    async def search(self, keyword: str) -> list[AliExpressProduct]:
        """Search AliExpress for products matching a keyword."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.aliexpress.com/v2/product/search",
                params={"keyword": keyword, "limit": 20},
                headers={"Authorization": f"Bearer {settings.aliexpress_api_key}"},
            )
            await response.raise_for_status()
            data = await response.json()
        return self.parse_response(data)

    async def collect(self) -> list[AliExpressProduct]:
        """Not used directly - search is called per keyword from matcher."""
        return []
