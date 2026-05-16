from fastapi import FastAPI

app = FastAPI(
    title="Trending Products API",
    version="0.1.0",
    description="Discover market-validated trending products to sell",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
