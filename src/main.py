from fastapi import FastAPI

from src.api.routes.auth import router as auth_router
from src.api.routes.health import router as health_router
from src.api.routes.products import router as products_router

app = FastAPI(
    title="Trending Products API",
    version="0.1.0",
    description="Discover market-validated trending products to sell",
)

app.include_router(health_router)
app.include_router(auth_router)
app.include_router(products_router)
