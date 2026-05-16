from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.collection_run import CollectionRun

router = APIRouter(tags=["system"])


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/api/v1/status/pipeline")
async def pipeline_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(CollectionRun).order_by(CollectionRun.started_at.desc()).limit(5)
    )
    runs = result.scalars().all()
    return {
        "status": "ok",
        "data": [
            {
                "id": str(r.id),
                "source": r.source,
                "status": r.status.value,
                "started_at": r.started_at.isoformat(),
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "items_collected": r.items_collected,
            }
            for r in runs
        ],
    }
