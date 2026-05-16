import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ProductCard, CollectionRun
from src.pipeline.orchestrator import run_pipeline

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


@pytest.fixture
def tiktok_fixture():
    with open(FIXTURES_DIR / "tiktok_trending_response.json") as f:
        return json.load(f)


@pytest.fixture
def aliexpress_fixture():
    with open(FIXTURES_DIR / "aliexpress_search_response.json") as f:
        return json.load(f)


class TestRunPipeline:
    @patch("src.pipeline.orchestrator.AliExpressCollector")
    @patch("src.pipeline.orchestrator.TikTokCollector")
    async def test_creates_product_cards(
        self, mock_tiktok_cls, mock_ali_cls, db: AsyncSession, tiktok_fixture, aliexpress_fixture
    ):
        from src.collectors.tiktok import TikTokCollector
        from src.collectors.aliexpress import AliExpressCollector

        real_tiktok = TikTokCollector()
        mock_tiktok = AsyncMock()
        mock_tiktok.collect.return_value = real_tiktok.parse_response(tiktok_fixture)
        mock_tiktok_cls.return_value = mock_tiktok

        real_ali = AliExpressCollector()
        mock_ali = AsyncMock()
        mock_ali.search.return_value = real_ali.parse_response(aliexpress_fixture)
        mock_ali_cls.return_value = mock_ali

        await run_pipeline(db)

        result = await db.execute(select(ProductCard))
        cards = result.scalars().all()
        assert len(cards) > 0

    @patch("src.pipeline.orchestrator.AliExpressCollector")
    @patch("src.pipeline.orchestrator.TikTokCollector")
    async def test_creates_collection_runs(
        self, mock_tiktok_cls, mock_ali_cls, db: AsyncSession, tiktok_fixture, aliexpress_fixture
    ):
        from src.collectors.tiktok import TikTokCollector
        from src.collectors.aliexpress import AliExpressCollector

        real_tiktok = TikTokCollector()
        mock_tiktok = AsyncMock()
        mock_tiktok.collect.return_value = real_tiktok.parse_response(tiktok_fixture)
        mock_tiktok_cls.return_value = mock_tiktok

        real_ali = AliExpressCollector()
        mock_ali = AsyncMock()
        mock_ali.search.return_value = real_ali.parse_response(aliexpress_fixture)
        mock_ali_cls.return_value = mock_ali

        await run_pipeline(db)

        result = await db.execute(select(CollectionRun))
        runs = result.scalars().all()
        assert len(runs) >= 1
        assert any(r.source == "tiktok" for r in runs)

    @patch("src.pipeline.orchestrator.AliExpressCollector")
    @patch("src.pipeline.orchestrator.TikTokCollector")
    async def test_handles_tiktok_failure(
        self, mock_tiktok_cls, mock_ali_cls, db: AsyncSession
    ):
        mock_tiktok = AsyncMock()
        mock_tiktok.collect.side_effect = Exception("API down")
        mock_tiktok_cls.return_value = mock_tiktok

        mock_ali = AsyncMock()
        mock_ali_cls.return_value = mock_ali

        await run_pipeline(db)

        result = await db.execute(select(CollectionRun))
        runs = result.scalars().all()
        failed_run = next(r for r in runs if r.source == "tiktok")
        assert failed_run.status.value == "failed"
