from dataclasses import dataclass, field

import httpx

from config.settings import settings
from src.collectors.base import BaseCollector


@dataclass
class TikTokProduct:
    id: str
    title: str
    category: str
    thumbnail: str
    advertiser_count: int
    creative_count: int
    ad_duration_days: int
    hashtag_views: int
    regions: list[str]
    engagement: dict
    sample_creatives: list[dict] = field(default_factory=list)


class TikTokCollector(BaseCollector):
    HEADERS = [
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
        {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        },
    ]

    def __init__(self):
        self._header_index = 0

    def _get_headers(self) -> dict:
        headers = self.HEADERS[self._header_index % len(self.HEADERS)]
        self._header_index += 1
        return headers

    def parse_response(self, data: dict) -> list[TikTokProduct]:
        if data.get("code") != 0 or "data" not in data:
            raise ValueError(f"Invalid TikTok response: {data.get('message', 'unknown error')}")

        products = []
        for item in data["data"].get("products", []):
            product = TikTokProduct(
                id=item["id"],
                title=item["title"],
                category=item.get("category", "Unknown"),
                thumbnail=item.get("thumbnail", ""),
                advertiser_count=item.get("advertiser_count", 0),
                creative_count=item.get("creative_count", 0),
                ad_duration_days=item.get("ad_duration_days", 0),
                hashtag_views=item.get("hashtag_views", 0),
                regions=item.get("regions", []),
                engagement=item.get("engagement", {}),
                sample_creatives=item.get("sample_creatives", []),
            )
            products.append(product)
        return products

    async def collect(self) -> list[TikTokProduct]:
        async with httpx.AsyncClient(headers=self._get_headers(), timeout=30.0) as client:
            response = await client.get(
                f"{settings.tiktok_base_url}top_products",
                params={"period": 7, "limit": 50},
            )
            await response.raise_for_status()
            data = await response.json()
        return self.parse_response(data)
