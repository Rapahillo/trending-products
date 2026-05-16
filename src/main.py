from fastapi import FastAPI

from src.api.routes.auth import router as auth_router

app = FastAPI(
    title="Trending Products API",
    version="0.1.0",
    description="Discover market-validated trending products to sell",
)

app.include_router(auth_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
