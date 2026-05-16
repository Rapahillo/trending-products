import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from config.settings import settings
from src.database import async_session
from src.pipeline.orchestrator import run_pipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def pipeline_job():
    """Run the full data pipeline."""
    logger.info("Starting pipeline run...")
    async with async_session() as db:
        try:
            await run_pipeline(db)
            logger.info("Pipeline run completed successfully")
        except Exception as e:
            logger.error(f"Pipeline run failed: {e}")


async def _run_scheduler():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        pipeline_job,
        "interval",
        hours=settings.pipeline_schedule_hours,
        id="pipeline_run",
        name="Trending Products Pipeline",
    )

    logger.info(
        f"Starting scheduler - pipeline runs every {settings.pipeline_schedule_hours} hours"
    )
    scheduler.start()

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler")
        scheduler.shutdown()


def main():
    asyncio.run(_run_scheduler())


if __name__ == "__main__":
    main()
