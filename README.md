# Trending Products API

A batch-processing backend API that collects trending product data from TikTok Creative Center and AliExpress twice daily, scores and enriches it, and serves pre-computed product cards via a REST API.

Built for e-commerce sellers (dropshippers, FBA, store owners, agencies) to discover market-validated niche products to sell.

## Tech Stack

- **API:** Python 3.12, FastAPI, Uvicorn
- **Database:** PostgreSQL 16, SQLAlchemy 2.0 (async), Alembic
- **Cache/Rate Limiting:** Redis 7
- **Pipeline:** APScheduler, httpx, Playwright
- **Auth:** JWT (python-jose), bcrypt (passlib)
- **Infrastructure:** Docker Compose

## Architecture

```
[Scheduler] → [TikTok Collector] → [Matcher] → [Enricher] → [Scoring Engine] → [PostgreSQL]
              [AliExpress Collector] ↗                                                 ↓
                                                                               [FastAPI] → Users
                                                                               [Redis cache]
```

The pipeline runs every 12 hours: **Collect → Match → Enrich → Score → Store**.

The API serves pre-computed product cards with filtering, sorting, and pagination.

## Local Development Setup

### Prerequisites

- Python 3.12+
- Docker and Docker Compose
- (Optional) A virtual environment tool (`venv`, `uv`, etc.)

### Option A: Full Stack with Docker Compose

This starts all services (API, worker, PostgreSQL, Redis) in containers:

```bash
# 1. Clone and enter project
cd trending-products

# 2. Create .env from template
cp .env.example .env

# 3. Start everything
docker compose up --build -d

# 4. Run database migrations
docker compose exec api alembic upgrade head

# 5. (Optional) Seed sample data
docker compose exec api python -m scripts.seed_data

# 6. Verify it's running
curl http://localhost:8000/health
```

The API is now available at `http://localhost:8000`.

### Option B: Local Python + Docker for Services

Run PostgreSQL and Redis in Docker, but run the API locally for faster iteration:

```bash
# 1. Start only database services
docker compose up postgres redis -d

# 2. Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -e ".[dev]"

# 4. Create .env with localhost URLs
cat > .env << 'EOF'
DATABASE_URL=postgresql+asyncpg://trending:trending_dev@localhost:5432/trending
REDIS_URL=redis://localhost:6379/0
JWT_SECRET=dev-secret-change-in-production
PIPELINE_SCHEDULE_HOURS=12
SCORING_WEIGHTS_PATH=config/scoring_weights.yml
TIKTOK_BASE_URL=https://ads.tiktok.com/creative_radar_api/v1/
ALIEXPRESS_API_KEY=your-key-here
EOF

# 5. Run database migrations
alembic upgrade head

# 6. (Optional) Seed sample data
python -m scripts.seed_data

# 7. Start the API server
uvicorn src.main:app --reload --port 8000

# 8. (In another terminal) Start the pipeline worker
python -m src.scheduler.jobs
```

### Running Tests

```bash
# Unit tests (no external services needed)
pytest tests/unit/ -v

# Integration tests (requires PostgreSQL running)
pytest tests/integration/ -v

# All tests with coverage
pytest tests/ --cov=src --cov-report=term-missing
```

## API Usage

### Register and Login

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@test.com","password":"demo123"}'

# Login (returns JWT token)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@test.com","password":"demo123"}'
```

### Browse Products

```bash
# List trending products (use token from login)
curl http://localhost:8000/api/v1/products \
  -H "Authorization: Bearer <TOKEN>"

# Filter by region and category
curl "http://localhost:8000/api/v1/products?region=US&category=Electronics&min_score=50" \
  -H "Authorization: Bearer <TOKEN>"

# Get product detail
curl http://localhost:8000/api/v1/products/<PRODUCT_ID> \
  -H "Authorization: Bearer <TOKEN>"

# Get score history
curl http://localhost:8000/api/v1/products/<PRODUCT_ID>/history \
  -H "Authorization: Bearer <TOKEN>"
```

### System Endpoints

```bash
# Health check (no auth)
curl http://localhost:8000/health

# Pipeline status (no auth)
curl http://localhost:8000/api/v1/status/pipeline
```

## Subscription Tiers

| Feature | Free | Basic | Pro | Enterprise |
|---------|------|-------|-----|------------|
| Products per query | 5 | 20 | 50 | unlimited |
| Queries per day | 10 | 100 | 500 | unlimited |
| Regions | 1 | 3 | all | all |
| API key access | no | no | no | yes |

## Project Structure

```
trending-products/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic/                    # DB migrations
├── config/
│   ├── settings.py             # App config (env-based)
│   └── scoring_weights.yml     # Tunable scoring config
├── src/
│   ├── main.py                 # FastAPI app entry
│   ├── database.py             # Async SQLAlchemy setup
│   ├── api/
│   │   ├── routes/             # products, auth, health
│   │   ├── dependencies.py     # Auth, rate limiting
│   │   └── schemas.py          # Pydantic models
│   ├── collectors/             # TikTok, AliExpress data fetchers
│   ├── pipeline/               # matcher, enricher, scorer, orchestrator
│   ├── models/                 # SQLAlchemy models
│   ├── services/               # Business logic
│   └── scheduler/              # APScheduler jobs
├── tests/
│   ├── unit/                   # No external deps
│   ├── integration/            # Requires PostgreSQL
│   └── fixtures/               # Sample API responses
└── scripts/
    └── seed_data.py            # Dev data seeding
```
