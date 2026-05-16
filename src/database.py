from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import settings

engine = create_async_engine(settings.async_database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
