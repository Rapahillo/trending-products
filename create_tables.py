"""Create all database tables directly using SQLAlchemy metadata."""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from config.settings import settings
from src.models import Base


async def main():
    print(f"Connecting to database...")
    engine = create_async_engine(settings.async_database_url, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("All tables created successfully.")


if __name__ == "__main__":
    asyncio.run(main())
