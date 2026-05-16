# Trending Products Backend API — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a batch-processing backend API that collects trending product data from TikTok Creative Center and AliExpress 2x/day, scores it, and serves pre-computed product cards via REST API with subscription tier gating.

**Architecture:** Batch pipeline (Collect → Match → Enrich → Score → Store) runs on a 12-hour schedule. FastAPI serves pre-computed product cards from PostgreSQL. Redis handles caching and rate limiting. Docker Compose orchestrates all services.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL 16, Redis, APScheduler, httpx, Playwright, Pydantic v2, pytest, Docker Compose.

---

## File Structure

```
trending-products/
├── docker-compose.yml              # PostgreSQL, Redis, API, Worker services
├── Dockerfile                      # Multi-stage Python build
├── pyproject.toml                  # Dependencies and project config
├── alembic.ini                     # Alembic config
├── .env.example                    # Example env vars
├── alembic/
│   ├── env.py                      # Migration environment
│   └── versions/                   # Generated migrations
├── config/
│   ├── settings.py                 # Pydantic settings (env-based)
│   └── scoring_weights.yml         # Tunable scoring weights
├── src/
│   ├── __init__.py
│   ├── main.py                     # FastAPI app entry + lifespan
│   ├── database.py                 # Async engine + session factory
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── products.py         # GET /products, /products/{id}, /products/{id}/history
│   │   │   ├── auth.py             # POST /auth/register, /auth/login, GET /auth/me
│   │   │   └── health.py           # GET /health, /status/pipeline
│   │   ├── dependencies.py         # get_current_user, require_tier, rate_limiter
│   │   └── schemas.py              # Pydantic request/response models
│   ├── collectors/
│   │   ├── __init__.py
│   │   ├── base.py                 # BaseCollector abstract class
│   │   ├── tiktok.py              # TikTok Creative Center collector
│   │   └── aliexpress.py          # AliExpress collector
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── orchestrator.py         # Runs full pipeline end-to-end
│   │   ├── matcher.py              # Jaccard + perceptual hash matching
│   │   ├── enricher.py             # Margins, competition, pricing
│   │   └── scorer.py               # Trend score, velocity, status
│   ├── models/
│   │   ├── __init__.py
│   │   ├── base.py                 # Base model class with UUID + timestamps
│   │   ├── product_card.py         # ProductCard model
│   │   ├── score_history.py        # ScoreHistory model
│   │   ├── collection_run.py       # CollectionRun model
│   │   ├── user.py                 # User model
│   │   └── api_key.py              # ApiKey model
│   ├── services/
│   │   ├── __init__.py
│   │   ├── product_service.py      # Query/filter/paginate products
│   │   └── auth_service.py         # Register, login, JWT, API keys
│   └── scheduler/
│       ├── __init__.py
│       └── jobs.py                 # APScheduler pipeline job
├── tests/
│   ├── __init__.py
│   ├── conftest.py                 # Shared fixtures (db session, client, etc.)
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── test_scorer.py
│   │   ├── test_matcher.py
│   │   ├── test_enricher.py
│   │   ├── test_tiktok_collector.py
│   │   └── test_aliexpress_collector.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_products_api.py
│   │   ├── test_auth_api.py
│   │   └── test_pipeline.py
│   └── fixtures/
│       ├── tiktok_trending_response.json
│       └── aliexpress_search_response.json
└── scripts/
    └── seed_data.py                # Insert sample product cards for dev
```

---

### Task 1: Project Scaffolding & Docker Setup

**Files:**
- Create: `pyproject.toml`
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `src/__init__.py`
- Create: `src/main.py`

- [ ] **Step 1: Create pyproject.toml with all dependencies**

```toml
[project]
name = "trending-products"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "sqlalchemy[asyncio]>=2.0.30",
    "asyncpg>=0.30.0",
    "alembic>=1.13.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "redis>=5.0.0",
    "httpx>=0.27.0",
    "playwright>=1.44.0",
    "apscheduler>=3.10.0",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "pyyaml>=6.0.0",
    "imagehash>=4.3.0",
    "Pillow>=10.3.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "httpx>=0.27.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.4.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 100
```

- [ ] **Step 2: Create Dockerfile**

```dockerfile
FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY . .

FROM base AS api
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS worker
CMD ["python", "-m", "src.scheduler.jobs"]
```

- [ ] **Step 3: Create docker-compose.yml**

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: trending
      POSTGRES_PASSWORD: trending_dev
      POSTGRES_DB: trending
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

  api:
    build:
      context: .
      target: api
    ports:
      - "8000:8000"
    env_file: .env
    depends_on:
      - postgres
      - redis

  worker:
    build:
      context: .
      target: worker
    env_file: .env
    depends_on:
      - postgres
      - redis

volumes:
  pgdata:
```

- [ ] **Step 4: Create .env.example**

```bash
DATABASE_URL=postgresql+asyncpg://trending:trending_dev@postgres:5432/trending
REDIS_URL=redis://redis:6379/0
JWT_SECRET=change-me-in-production
PIPELINE_SCHEDULE_HOURS=12
SCORING_WEIGHTS_PATH=config/scoring_weights.yml
TIKTOK_BASE_URL=https://ads.tiktok.com/creative_radar_api/v1/
ALIEXPRESS_API_KEY=your-key-here
```

- [ ] **Step 5: Create minimal FastAPI app entry**

Create `src/__init__.py` (empty) and `src/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(
    title="Trending Products API",
    version="0.1.0",
    description="Discover market-validated trending products to sell",
)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Verify Docker Compose starts**

Run: `docker compose up --build -d && sleep 5 && curl http://localhost:8000/health`

Expected: `{"status":"ok"}`

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml Dockerfile docker-compose.yml .env.example src/__init__.py src/main.py
git commit -m "feat: project scaffolding with Docker Compose and FastAPI"
```

---

### Task 2: Configuration & Settings

**Files:**
- Create: `config/settings.py`
- Create: `config/scoring_weights.yml`

- [ ] **Step 1: Create settings module**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://trending:trending_dev@localhost:5432/trending"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours
    pipeline_schedule_hours: int = 12
    scoring_weights_path: str = "config/scoring_weights.yml"
    tiktok_base_url: str = "https://ads.tiktok.com/creative_radar_api/v1/"
    aliexpress_api_key: str = ""
    collector_retry_attempts: int = 3
    collector_retry_backoff: float = 2.0

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **Step 2: Create scoring weights config**

```yaml
# Scoring weights - adjust without code changes
# All weights must sum to 1.0

weights:
  advertiser_count: 0.25
  ad_duration: 0.20
  creative_volume: 0.15
  engagement_velocity: 0.15
  order_volume_growth: 0.15
  supplier_availability: 0.10

# Score calibration
calibration_factor: 1.0

# Velocity thresholds
velocity_stable_threshold: 3
velocity_declining_threshold: -5
velocity_consecutive_runs_for_status: 3

# Score thresholds
trending_min_score: 30

# Competition thresholds
competition:
  low_max_advertisers: 10
  low_max_suppliers: 20
  medium_max_advertisers: 50
  medium_max_suppliers: 100

# Margin calculation
margin:
  markup_min: 2.5
  markup_max: 3.0
  platform_fee_percent: 5
```

- [ ] **Step 3: Commit**

```bash
git add config/
git commit -m "feat: add pydantic settings and scoring weights config"
```

---

### Task 3: Database Models & Migrations

**Files:**
- Create: `src/database.py`
- Create: `src/models/__init__.py`
- Create: `src/models/base.py`
- Create: `src/models/product_card.py`
- Create: `src/models/score_history.py`
- Create: `src/models/collection_run.py`
- Create: `src/models/user.py`
- Create: `src/models/api_key.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`

- [ ] **Step 1: Create database connection module**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
```

- [ ] **Step 2: Create base model**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
```

- [ ] **Step 3: Create ProductCard model**

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class TrendVelocity(str, enum.Enum):
    accelerating = "accelerating"
    stable = "stable"
    decelerating = "decelerating"


class ProductStatus(str, enum.Enum):
    trending = "trending"
    declining = "declining"
    expired = "expired"


class ProductCard(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "product_cards"

    title: Mapped[str] = mapped_column(String(500))
    category: Mapped[str | None] = mapped_column(String(200))
    image_urls: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    trend_score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    trend_velocity: Mapped[TrendVelocity] = mapped_column(
        Enum(TrendVelocity), default=TrendVelocity.stable
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    regions: Mapped[list[str]] = mapped_column(ARRAY(String), default=list, index=True)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), default=ProductStatus.trending, index=True
    )
    tiktok_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    supplier_data: Mapped[dict] = mapped_column(JSONB, default=dict)
    competition: Mapped[dict] = mapped_column(JSONB, default=dict)
    pricing: Mapped[dict] = mapped_column(JSONB, default=dict)

    score_history: Mapped[list["ScoreHistory"]] = relationship(back_populates="product_card")
```

- [ ] **Step 4: Create ScoreHistory model**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin


class ScoreHistory(UUIDMixin, Base):
    __tablename__ = "score_history"

    product_card_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("product_cards.id", ondelete="CASCADE"), index=True
    )
    trend_score: Mapped[int] = mapped_column(Integer)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    product_card: Mapped["ProductCard"] = relationship(back_populates="score_history")
```

- [ ] **Step 5: Create CollectionRun model**

```python
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base, UUIDMixin


class CollectionStatus(str, enum.Enum):
    success = "success"
    partial = "partial"
    failed = "failed"


class CollectionRun(UUIDMixin, Base):
    __tablename__ = "collection_runs"

    source: Mapped[str] = mapped_column(String(50))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[CollectionStatus] = mapped_column(Enum(CollectionStatus))
    items_collected: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[dict] = mapped_column(JSONB, default=dict)
```

- [ ] **Step 6: Create User model**

```python
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, TimestampMixin, UUIDMixin


class SubscriptionTier(str, enum.Enum):
    free = "free"
    basic = "basic"
    pro = "pro"
    enterprise = "enterprise"


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200))
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        Enum(SubscriptionTier), default=SubscriptionTier.free
    )
    region_preference: Mapped[str | None] = mapped_column(String(10), nullable=True)

    api_keys: Mapped[list["ApiKey"]] = relationship(back_populates="user")
```

- [ ] **Step 7: Create ApiKey model**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import Base, UUIDMixin


class ApiKey(UUIDMixin, Base):
    __tablename__ = "api_keys"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    key_hash: Mapped[str] = mapped_column(String(200))
    name: Mapped[str] = mapped_column(String(100))
    rate_limit: Mapped[int] = mapped_column(Integer, default=1000)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="api_keys")
```

- [ ] **Step 8: Create models __init__.py that imports all models**

```python
from src.models.base import Base
from src.models.product_card import ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory
from src.models.collection_run import CollectionRun, CollectionStatus
from src.models.user import User, SubscriptionTier
from src.models.api_key import ApiKey

__all__ = [
    "Base",
    "ProductCard",
    "ProductStatus",
    "TrendVelocity",
    "ScoreHistory",
    "CollectionRun",
    "CollectionStatus",
    "User",
    "SubscriptionTier",
    "ApiKey",
]
```

- [ ] **Step 9: Set up Alembic**

Create `alembic.ini`:
```ini
[alembic]
script_location = alembic
sqlalchemy.url = postgresql+asyncpg://trending:trending_dev@localhost:5432/trending

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

Create `alembic/env.py`:
```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from config.settings import settings
from src.models import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online():
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 10: Generate initial migration**

Run: `alembic revision --autogenerate -m "initial schema"`

Expected: Migration file created in `alembic/versions/`

- [ ] **Step 11: Apply migration**

Run: `alembic upgrade head`

Expected: All tables created in PostgreSQL

- [ ] **Step 12: Commit**

```bash
git add src/database.py src/models/ alembic.ini alembic/
git commit -m "feat: database models and initial migration"
```

---

### Task 4: Test Infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/unit/__init__.py`
- Create: `tests/integration/__init__.py`
- Create: `tests/fixtures/tiktok_trending_response.json`
- Create: `tests/fixtures/aliexpress_search_response.json`

- [ ] **Step 1: Create test configuration and fixtures**

`tests/__init__.py` (empty)
`tests/unit/__init__.py` (empty)
`tests/integration/__init__.py` (empty)

`tests/conftest.py`:
```python
import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import get_db
from src.main import app
from src.models import Base

TEST_DATABASE_URL = "postgresql+asyncpg://trending:trending_dev@localhost:5432/trending_test"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
test_session = async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    async with test_session() as session:
        yield session


@pytest.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
```

- [ ] **Step 2: Create TikTok fixture data**

`tests/fixtures/tiktok_trending_response.json`:
```json
{
  "code": 0,
  "data": {
    "products": [
      {
        "id": "tiktok_001",
        "title": "Portable Neck Fan",
        "category": "Electronics",
        "thumbnail": "https://example.com/neck-fan.jpg",
        "advertiser_count": 45,
        "creative_count": 120,
        "ad_duration_days": 14,
        "hashtag_views": 5200000,
        "regions": ["US", "EU", "SEA"],
        "engagement": {
          "likes": 320000,
          "shares": 45000,
          "comments": 12000
        },
        "sample_creatives": [
          {"url": "https://example.com/creative1.mp4", "thumbnail": "https://example.com/thumb1.jpg"},
          {"url": "https://example.com/creative2.mp4", "thumbnail": "https://example.com/thumb2.jpg"}
        ]
      },
      {
        "id": "tiktok_002",
        "title": "LED Galaxy Projector",
        "category": "Home & Garden",
        "thumbnail": "https://example.com/galaxy-projector.jpg",
        "advertiser_count": 28,
        "creative_count": 75,
        "ad_duration_days": 21,
        "hashtag_views": 3100000,
        "regions": ["US", "EU"],
        "engagement": {
          "likes": 180000,
          "shares": 28000,
          "comments": 8000
        },
        "sample_creatives": [
          {"url": "https://example.com/creative3.mp4", "thumbnail": "https://example.com/thumb3.jpg"}
        ]
      },
      {
        "id": "tiktok_003",
        "title": "Magnetic Phone Mount",
        "category": "Accessories",
        "thumbnail": "https://example.com/phone-mount.jpg",
        "advertiser_count": 8,
        "creative_count": 15,
        "ad_duration_days": 5,
        "hashtag_views": 800000,
        "regions": ["US"],
        "engagement": {
          "likes": 50000,
          "shares": 7000,
          "comments": 2000
        },
        "sample_creatives": []
      }
    ]
  }
}
```

- [ ] **Step 3: Create AliExpress fixture data**

`tests/fixtures/aliexpress_search_response.json`:
```json
{
  "results": [
    {
      "product_id": "ali_001",
      "title": "Portable Bladeless Neck Fan USB Rechargeable",
      "url": "https://aliexpress.com/item/001.html",
      "price": 4.50,
      "original_price": 8.99,
      "currency": "USD",
      "images": ["https://example.com/ali-fan1.jpg", "https://example.com/ali-fan2.jpg"],
      "order_count": 15000,
      "rating": 4.6,
      "seller_name": "TechGadgets Store",
      "seller_rating": 95.2,
      "shipping": [
        {"region": "US", "cost": 2.50, "days_min": 7, "days_max": 15},
        {"region": "EU", "cost": 3.00, "days_min": 10, "days_max": 20},
        {"region": "SEA", "cost": 1.50, "days_min": 5, "days_max": 10}
      ],
      "variants": [
        {"name": "White", "price": 4.50},
        {"name": "Black", "price": 4.50},
        {"name": "Pink", "price": 4.80}
      ]
    },
    {
      "product_id": "ali_002",
      "title": "Neck Fan Portable Mini USB Bladeless",
      "url": "https://aliexpress.com/item/002.html",
      "price": 3.80,
      "original_price": 7.50,
      "currency": "USD",
      "images": ["https://example.com/ali-fan3.jpg"],
      "order_count": 8500,
      "rating": 4.3,
      "seller_name": "CoolBreeze Official",
      "seller_rating": 92.1,
      "shipping": [
        {"region": "US", "cost": 3.00, "days_min": 10, "days_max": 20},
        {"region": "EU", "cost": 3.50, "days_min": 12, "days_max": 25}
      ],
      "variants": [
        {"name": "White", "price": 3.80},
        {"name": "Blue", "price": 3.80}
      ]
    },
    {
      "product_id": "ali_003",
      "title": "Galaxy Star Projector LED Night Light",
      "url": "https://aliexpress.com/item/003.html",
      "price": 8.20,
      "original_price": 15.99,
      "currency": "USD",
      "images": ["https://example.com/ali-projector1.jpg"],
      "order_count": 22000,
      "rating": 4.7,
      "seller_name": "HomeDecor Plus",
      "seller_rating": 97.0,
      "shipping": [
        {"region": "US", "cost": 0.00, "days_min": 8, "days_max": 18},
        {"region": "EU", "cost": 2.00, "days_min": 10, "days_max": 22}
      ],
      "variants": [
        {"name": "Basic", "price": 8.20},
        {"name": "Bluetooth Speaker", "price": 12.50}
      ]
    }
  ]
}
```

- [ ] **Step 4: Verify test infrastructure**

Run: `pytest tests/ --co -q`

Expected: "no tests ran" (but no import errors)

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "feat: test infrastructure with fixtures and conftest"
```

---

### Task 5: Scoring Engine (TDD)

**Files:**
- Create: `src/pipeline/scorer.py`
- Create: `src/pipeline/__init__.py`
- Test: `tests/unit/test_scorer.py`

- [ ] **Step 1: Write failing tests for scoring**

`tests/unit/test_scorer.py`:
```python
import pytest

from src.pipeline.scorer import (
    calculate_competition,
    calculate_trend_score,
    calculate_velocity,
    determine_status,
)


class TestCalculateTrendScore:
    def test_high_signals_produce_high_score(self):
        signals = {
            "advertiser_count": 50,
            "ad_duration": 30,
            "creative_volume": 100,
            "engagement_velocity": 5000000,
            "order_volume_growth": 500,
            "supplier_availability": 30,
        }
        # All products in this batch for percentile calculation
        all_signals = [signals]
        score = calculate_trend_score(signals, all_signals)
        assert 0 <= score <= 100

    def test_low_signals_produce_low_score(self):
        low = {
            "advertiser_count": 1,
            "ad_duration": 1,
            "creative_volume": 1,
            "engagement_velocity": 1000,
            "order_volume_growth": 5,
            "supplier_availability": 1,
        }
        high = {
            "advertiser_count": 50,
            "ad_duration": 30,
            "creative_volume": 100,
            "engagement_velocity": 5000000,
            "order_volume_growth": 500,
            "supplier_availability": 30,
        }
        all_signals = [low, high]
        low_score = calculate_trend_score(low, all_signals)
        high_score = calculate_trend_score(high, all_signals)
        assert low_score < high_score

    def test_score_capped_at_100(self):
        signals = {
            "advertiser_count": 1000,
            "ad_duration": 365,
            "creative_volume": 5000,
            "engagement_velocity": 100000000,
            "order_volume_growth": 10000,
            "supplier_availability": 500,
        }
        all_signals = [signals]
        score = calculate_trend_score(signals, all_signals)
        assert score <= 100

    def test_single_product_gets_percentile_of_100(self):
        signals = {
            "advertiser_count": 20,
            "ad_duration": 10,
            "creative_volume": 30,
            "engagement_velocity": 1000000,
            "order_volume_growth": 100,
            "supplier_availability": 10,
        }
        all_signals = [signals]
        score = calculate_trend_score(signals, all_signals)
        assert score == 100


class TestCalculateVelocity:
    def test_accelerating(self):
        scores = [50, 60, 70]  # oldest to newest
        velocity = calculate_velocity(scores)
        assert velocity == "accelerating"

    def test_stable(self):
        scores = [50, 51, 52]
        velocity = calculate_velocity(scores)
        assert velocity == "stable"

    def test_decelerating(self):
        scores = [70, 60, 50]
        velocity = calculate_velocity(scores)
        assert velocity == "decelerating"

    def test_insufficient_history_returns_stable(self):
        scores = [50]
        velocity = calculate_velocity(scores)
        assert velocity == "stable"


class TestDetermineStatus:
    def test_trending(self):
        status = determine_status(score=50, velocity="stable", declining_runs=0)
        assert status == "trending"

    def test_declining(self):
        status = determine_status(score=50, velocity="decelerating", declining_runs=3)
        assert status == "declining"

    def test_not_declining_until_3_runs(self):
        status = determine_status(score=50, velocity="decelerating", declining_runs=2)
        assert status == "trending"

    def test_expired(self):
        status = determine_status(score=20, velocity="decelerating", declining_runs=3)
        assert status == "expired"

    def test_expired_needs_3_consecutive_runs(self):
        status = determine_status(score=20, velocity="decelerating", declining_runs=2)
        assert status == "trending"


class TestCalculateCompetition:
    def test_low_competition(self):
        result = calculate_competition(advertiser_count=5, supplier_count=10)
        assert result == "low"

    def test_medium_competition(self):
        result = calculate_competition(advertiser_count=25, supplier_count=50)
        assert result == "medium"

    def test_high_competition(self):
        result = calculate_competition(advertiser_count=60, supplier_count=150)
        assert result == "high"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_scorer.py -v`

Expected: FAIL with ImportError (module doesn't exist yet)

- [ ] **Step 3: Implement the scoring engine**

Create `src/pipeline/__init__.py` (empty).

`src/pipeline/scorer.py`:
```python
import yaml

from config.settings import settings

_weights_cache: dict | None = None


def _load_weights() -> dict:
    global _weights_cache
    if _weights_cache is None:
        with open(settings.scoring_weights_path) as f:
            _weights_cache = yaml.safe_load(f)
    return _weights_cache


def _percentile_rank(value: float, all_values: list[float]) -> float:
    """Return percentile rank (0-1) of value within all_values."""
    if len(all_values) <= 1:
        return 1.0
    sorted_values = sorted(all_values)
    rank = sorted_values.index(value)
    return rank / (len(sorted_values) - 1)


def calculate_trend_score(signals: dict, all_signals: list[dict]) -> int:
    """Calculate trend score (0-100) using weighted percentile ranking."""
    config = _load_weights()
    weights = config["weights"]
    calibration = config["calibration_factor"]

    signal_keys = [
        "advertiser_count",
        "ad_duration",
        "creative_volume",
        "engagement_velocity",
        "order_volume_growth",
        "supplier_availability",
    ]

    raw_score = 0.0
    for key in signal_keys:
        value = signals.get(key, 0)
        all_values = [s.get(key, 0) for s in all_signals]
        percentile = _percentile_rank(value, all_values)
        raw_score += percentile * weights[key]

    score = min(100, int(raw_score * 100 * calibration))
    return score


def calculate_velocity(scores: list[int]) -> str:
    """Calculate velocity from score history (oldest to newest)."""
    config = _load_weights()
    threshold = config["velocity_stable_threshold"]

    if len(scores) < 3:
        return "stable"

    velocity = (scores[-1] - scores[-3]) / 2

    if abs(velocity) < threshold:
        return "stable"
    elif velocity > 0:
        return "accelerating"
    else:
        return "decelerating"


def determine_status(score: int, velocity: str, declining_runs: int) -> str:
    """Determine product status based on score, velocity, and history."""
    config = _load_weights()
    min_score = config["trending_min_score"]
    consecutive_needed = config["velocity_consecutive_runs_for_status"]
    velocity_threshold = config["velocity_declining_threshold"]

    if score < min_score and declining_runs >= consecutive_needed:
        return "expired"

    if score >= min_score and velocity == "decelerating" and declining_runs >= consecutive_needed:
        return "declining"

    return "trending"


def calculate_competition(advertiser_count: int, supplier_count: int) -> str:
    """Classify competition level based on advertiser and supplier counts."""
    config = _load_weights()
    comp = config["competition"]

    if (
        advertiser_count <= comp["low_max_advertisers"]
        and supplier_count <= comp["low_max_suppliers"]
    ):
        return "low"
    elif (
        advertiser_count <= comp["medium_max_advertisers"]
        and supplier_count <= comp["medium_max_suppliers"]
    ):
        return "medium"
    else:
        return "high"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_scorer.py -v`

Expected: All 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/__init__.py src/pipeline/scorer.py tests/unit/test_scorer.py
git commit -m "feat: scoring engine with trend score, velocity, status, competition"
```

---

### Task 6: TikTok Collector (TDD)

**Files:**
- Create: `src/collectors/__init__.py`
- Create: `src/collectors/base.py`
- Create: `src/collectors/tiktok.py`
- Test: `tests/unit/test_tiktok_collector.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_tiktok_collector.py`:
```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.collectors.tiktok import TikTokCollector, TikTokProduct

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestTikTokCollector:
    @pytest.fixture
    def fixture_data(self):
        with open(FIXTURES_DIR / "tiktok_trending_response.json") as f:
            return json.load(f)

    @pytest.fixture
    def collector(self):
        return TikTokCollector()

    def test_parse_products(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        assert len(products) == 3
        assert all(isinstance(p, TikTokProduct) for p in products)

    def test_product_fields(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert product.title == "Portable Neck Fan"
        assert product.category == "Electronics"
        assert product.advertiser_count == 45
        assert product.creative_count == 120
        assert product.ad_duration_days == 14
        assert product.hashtag_views == 5200000
        assert product.regions == ["US", "EU", "SEA"]

    def test_product_engagement(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert product.engagement["likes"] == 320000
        assert product.engagement["shares"] == 45000

    def test_empty_response(self, collector):
        empty = {"code": 0, "data": {"products": []}}
        products = collector.parse_response(empty)
        assert products == []

    def test_malformed_response_raises(self, collector):
        with pytest.raises(ValueError, match="Invalid TikTok response"):
            collector.parse_response({"code": 1, "message": "error"})

    @patch("src.collectors.tiktok.httpx.AsyncClient")
    async def test_collect_calls_api(self, mock_client_class, collector, fixture_data):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_response = AsyncMock()
        mock_response.json.return_value = fixture_data
        mock_response.raise_for_status = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        products = await collector.collect()
        assert len(products) == 3
        mock_client.get.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_tiktok_collector.py -v`

Expected: FAIL with ImportError

- [ ] **Step 3: Implement base collector**

`src/collectors/__init__.py` (empty).

`src/collectors/base.py`:
```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CollectorResult:
    source: str
    items: list
    errors: list[str]


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self) -> list:
        """Fetch data from the source. Returns list of parsed items."""
        ...

    @abstractmethod
    def parse_response(self, data: dict) -> list:
        """Parse raw API response into structured items."""
        ...
```

- [ ] **Step 4: Implement TikTok collector**

`src/collectors/tiktok.py`:
```python
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
            response.raise_for_status()
            data = response.json()
        return self.parse_response(data)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/unit/test_tiktok_collector.py -v`

Expected: All 7 tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/collectors/ tests/unit/test_tiktok_collector.py
git commit -m "feat: TikTok Creative Center collector with fixture-based tests"
```

---

### Task 7: AliExpress Collector (TDD)

**Files:**
- Create: `src/collectors/aliexpress.py`
- Test: `tests/unit/test_aliexpress_collector.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_aliexpress_collector.py`:
```python
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.collectors.aliexpress import AliExpressCollector, AliExpressProduct

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestAliExpressCollector:
    @pytest.fixture
    def fixture_data(self):
        with open(FIXTURES_DIR / "aliexpress_search_response.json") as f:
            return json.load(f)

    @pytest.fixture
    def collector(self):
        return AliExpressCollector()

    def test_parse_products(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        assert len(products) == 3
        assert all(isinstance(p, AliExpressProduct) for p in products)

    def test_product_fields(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert product.title == "Portable Bladeless Neck Fan USB Rechargeable"
        assert product.price == 4.50
        assert product.order_count == 15000
        assert product.rating == 4.6
        assert len(product.shipping) == 3

    def test_product_shipping(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        us_shipping = next(s for s in product.shipping if s["region"] == "US")
        assert us_shipping["cost"] == 2.50
        assert us_shipping["days_min"] == 7

    def test_product_variants(self, collector, fixture_data):
        products = collector.parse_response(fixture_data)
        product = products[0]
        assert len(product.variants) == 3
        assert product.variants[0]["name"] == "White"

    def test_empty_results(self, collector):
        empty = {"results": []}
        products = collector.parse_response(empty)
        assert products == []

    @patch("src.collectors.aliexpress.httpx.AsyncClient")
    async def test_search_by_keyword(self, mock_client_class, collector, fixture_data):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_response = AsyncMock()
        mock_response.json.return_value = fixture_data
        mock_response.raise_for_status = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_class.return_value = mock_client

        products = await collector.search("portable neck fan")
        assert len(products) == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_aliexpress_collector.py -v`

Expected: FAIL with ImportError

- [ ] **Step 3: Implement AliExpress collector**

`src/collectors/aliexpress.py`:
```python
from dataclasses import dataclass, field

import httpx

from config.settings import settings
from src.collectors.base import BaseCollector


@dataclass
class AliExpressProduct:
    product_id: str
    title: str
    url: str
    price: float
    original_price: float
    currency: str
    images: list[str]
    order_count: int
    rating: float
    seller_name: str
    seller_rating: float
    shipping: list[dict]
    variants: list[dict] = field(default_factory=list)


class AliExpressCollector(BaseCollector):
    def parse_response(self, data: dict) -> list[AliExpressProduct]:
        products = []
        for item in data.get("results", []):
            product = AliExpressProduct(
                product_id=item["product_id"],
                title=item["title"],
                url=item["url"],
                price=item["price"],
                original_price=item.get("original_price", item["price"]),
                currency=item.get("currency", "USD"),
                images=item.get("images", []),
                order_count=item.get("order_count", 0),
                rating=item.get("rating", 0.0),
                seller_name=item.get("seller_name", ""),
                seller_rating=item.get("seller_rating", 0.0),
                shipping=item.get("shipping", []),
                variants=item.get("variants", []),
            )
            products.append(product)
        return products

    async def search(self, keyword: str) -> list[AliExpressProduct]:
        """Search AliExpress for products matching a keyword."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.aliexpress.com/v2/product/search",
                params={"keyword": keyword, "limit": 20},
                headers={"Authorization": f"Bearer {settings.aliexpress_api_key}"},
            )
            response.raise_for_status()
            data = response.json()
        return self.parse_response(data)

    async def collect(self) -> list[AliExpressProduct]:
        """Not used directly — search is called per keyword from matcher."""
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_aliexpress_collector.py -v`

Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/collectors/aliexpress.py tests/unit/test_aliexpress_collector.py
git commit -m "feat: AliExpress collector with keyword search and fixture tests"
```

---

### Task 8: Matcher (TDD)

**Files:**
- Create: `src/pipeline/matcher.py`
- Test: `tests/unit/test_matcher.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_matcher.py`:
```python
import pytest

from src.collectors.aliexpress import AliExpressProduct
from src.collectors.tiktok import TikTokProduct
from src.pipeline.matcher import (
    Match,
    calculate_jaccard_similarity,
    find_best_match,
    tokenize,
)


class TestTokenize:
    def test_basic_tokenization(self):
        tokens = tokenize("Portable Neck Fan")
        assert tokens == {"portable", "neck", "fan"}

    def test_removes_common_words(self):
        tokens = tokenize("The Best USB Rechargeable Neck Fan for You")
        assert "the" not in tokens
        assert "for" not in tokens
        assert "you" not in tokens

    def test_lowercases(self):
        tokens = tokenize("LED Galaxy PROJECTOR")
        assert tokens == {"led", "galaxy", "projector"}


class TestJaccardSimilarity:
    def test_identical_sets(self):
        result = calculate_jaccard_similarity({"a", "b", "c"}, {"a", "b", "c"})
        assert result == 1.0

    def test_no_overlap(self):
        result = calculate_jaccard_similarity({"a", "b"}, {"c", "d"})
        assert result == 0.0

    def test_partial_overlap(self):
        result = calculate_jaccard_similarity({"portable", "neck", "fan"}, {"portable", "bladeless", "neck", "fan", "usb", "rechargeable"})
        # intersection: {portable, neck, fan} = 3
        # union: {portable, neck, fan, bladeless, usb, rechargeable} = 6
        assert result == pytest.approx(0.5)

    def test_high_overlap(self):
        result = calculate_jaccard_similarity(
            {"led", "galaxy", "projector"},
            {"galaxy", "star", "projector", "led", "night", "light"},
        )
        # intersection: {led, galaxy, projector} = 3
        # union: {led, galaxy, projector, star, night, light} = 6
        assert result == pytest.approx(0.5)


class TestFindBestMatch:
    @pytest.fixture
    def tiktok_product(self):
        return TikTokProduct(
            id="tt_001",
            title="Portable Neck Fan",
            category="Electronics",
            thumbnail="https://example.com/fan.jpg",
            advertiser_count=45,
            creative_count=120,
            ad_duration_days=14,
            hashtag_views=5200000,
            regions=["US", "EU"],
            engagement={"likes": 320000},
            sample_creatives=[],
        )

    @pytest.fixture
    def ali_products(self):
        return [
            AliExpressProduct(
                product_id="ali_001",
                title="Portable Bladeless Neck Fan USB Rechargeable",
                url="https://aliexpress.com/item/001.html",
                price=4.50,
                original_price=8.99,
                currency="USD",
                images=["https://example.com/fan.jpg"],
                order_count=15000,
                rating=4.6,
                seller_name="TechStore",
                seller_rating=95.0,
                shipping=[{"region": "US", "cost": 2.50, "days_min": 7, "days_max": 15}],
                variants=[],
            ),
            AliExpressProduct(
                product_id="ali_099",
                title="Wireless Bluetooth Headphones Over Ear",
                url="https://aliexpress.com/item/099.html",
                price=12.00,
                original_price=25.00,
                currency="USD",
                images=[],
                order_count=5000,
                rating=4.2,
                seller_name="AudioShop",
                seller_rating=90.0,
                shipping=[{"region": "US", "cost": 3.00, "days_min": 10, "days_max": 20}],
                variants=[],
            ),
        ]

    def test_finds_matching_product(self, tiktok_product, ali_products):
        match = find_best_match(tiktok_product, ali_products)
        assert match is not None
        assert match.ali_product.product_id == "ali_001"

    def test_returns_none_for_no_match(self, tiktok_product):
        unrelated = [
            AliExpressProduct(
                product_id="ali_999",
                title="Yoga Mat Non-Slip Exercise",
                url="https://aliexpress.com/item/999.html",
                price=10.00,
                original_price=20.00,
                currency="USD",
                images=[],
                order_count=3000,
                rating=4.5,
                seller_name="FitShop",
                seller_rating=93.0,
                shipping=[],
                variants=[],
            ),
        ]
        match = find_best_match(tiktok_product, unrelated)
        assert match is None

    def test_match_contains_similarity_score(self, tiktok_product, ali_products):
        match = find_best_match(tiktok_product, ali_products)
        assert match is not None
        assert 0.0 < match.similarity <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_matcher.py -v`

Expected: FAIL with ImportError

- [ ] **Step 3: Implement matcher**

`src/pipeline/matcher.py`:
```python
from dataclasses import dataclass

from src.collectors.aliexpress import AliExpressProduct
from src.collectors.tiktok import TikTokProduct

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "this", "that", "are", "was",
    "be", "has", "had", "not", "no", "you", "your", "we", "our", "new",
}

JACCARD_THRESHOLD = 0.6


@dataclass
class Match:
    tiktok_product: TikTokProduct
    ali_product: AliExpressProduct
    similarity: float


def tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase words, removing stop words."""
    words = set(text.lower().split())
    return words - STOP_WORDS


def calculate_jaccard_similarity(set_a: set[str], set_b: set[str]) -> float:
    """Calculate Jaccard similarity between two sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def find_best_match(
    tiktok_product: TikTokProduct,
    ali_products: list[AliExpressProduct],
) -> Match | None:
    """Find the best AliExpress match for a TikTok product by keyword similarity."""
    tiktok_tokens = tokenize(tiktok_product.title)

    best_match: Match | None = None
    best_similarity = 0.0

    for ali_product in ali_products:
        ali_tokens = tokenize(ali_product.title)
        similarity = calculate_jaccard_similarity(tiktok_tokens, ali_tokens)

        if similarity > best_similarity:
            best_similarity = similarity
            best_match = Match(
                tiktok_product=tiktok_product,
                ali_product=ali_product,
                similarity=similarity,
            )

    if best_match and best_match.similarity >= JACCARD_THRESHOLD:
        return best_match

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_matcher.py -v`

Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/matcher.py tests/unit/test_matcher.py
git commit -m "feat: product matcher with Jaccard similarity"
```

---

### Task 9: Enricher (TDD)

**Files:**
- Create: `src/pipeline/enricher.py`
- Test: `tests/unit/test_enricher.py`

- [ ] **Step 1: Write failing tests**

`tests/unit/test_enricher.py`:
```python
import pytest

from src.collectors.aliexpress import AliExpressProduct
from src.collectors.tiktok import TikTokProduct
from src.pipeline.enricher import enrich_product, EnrichedProduct
from src.pipeline.matcher import Match


@pytest.fixture
def match():
    tiktok = TikTokProduct(
        id="tt_001",
        title="Portable Neck Fan",
        category="Electronics",
        thumbnail="https://example.com/fan.jpg",
        advertiser_count=45,
        creative_count=120,
        ad_duration_days=14,
        hashtag_views=5200000,
        regions=["US", "EU"],
        engagement={"likes": 320000, "shares": 45000},
        sample_creatives=[{"url": "https://example.com/vid.mp4", "thumbnail": "https://example.com/t.jpg"}],
    )
    ali = AliExpressProduct(
        product_id="ali_001",
        title="Portable Bladeless Neck Fan USB Rechargeable",
        url="https://aliexpress.com/item/001.html",
        price=4.50,
        original_price=8.99,
        currency="USD",
        images=["https://example.com/fan1.jpg", "https://example.com/fan2.jpg"],
        order_count=15000,
        rating=4.6,
        seller_name="TechStore",
        seller_rating=95.0,
        shipping=[
            {"region": "US", "cost": 2.50, "days_min": 7, "days_max": 15},
            {"region": "EU", "cost": 3.00, "days_min": 10, "days_max": 20},
        ],
        variants=[{"name": "White", "price": 4.50}, {"name": "Black", "price": 4.50}],
    )
    return Match(tiktok_product=tiktok, ali_product=ali, similarity=0.75)


class TestEnrichProduct:
    def test_returns_enriched_product(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert isinstance(result, EnrichedProduct)

    def test_title_from_tiktok(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.title == "Portable Neck Fan"

    def test_pricing_calculated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        # best price is 4.50, markup 2.5-3.0x
        assert result.pricing["cost_min"] == 4.50
        assert result.pricing["suggested_sell_price_min"] == pytest.approx(11.25)  # 4.50 * 2.5
        assert result.pricing["suggested_sell_price_max"] == pytest.approx(13.50)  # 4.50 * 3.0

    def test_margin_calculated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        # margin at min sell price: 11.25 - 4.50 - 2.50(shipping) - 11.25*0.05(fees) = 3.69
        assert result.pricing["estimated_margin_min"] == pytest.approx(3.69, abs=0.01)

    def test_regions_from_tiktok(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.regions == ["US", "EU"]

    def test_supplier_data_populated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.supplier_data["supplier_count"] == 1
        assert result.supplier_data["best_price"] == 4.50
        assert len(result.supplier_data["listings"]) == 1

    def test_tiktok_data_populated(self, match):
        result = enrich_product(match, all_ali_products_for_keyword=[match.ali_product])
        assert result.tiktok_data["advertiser_count"] == 45
        assert result.tiktok_data["creative_count"] == 120
        assert result.tiktok_data["ad_duration_days"] == 14

    def test_competition_with_multiple_suppliers(self, match):
        extra_supplier = AliExpressProduct(
            product_id="ali_002",
            title="Neck Fan Portable",
            url="https://aliexpress.com/item/002.html",
            price=3.80,
            original_price=7.50,
            currency="USD",
            images=[],
            order_count=8000,
            rating=4.3,
            seller_name="OtherStore",
            seller_rating=92.0,
            shipping=[{"region": "US", "cost": 3.00, "days_min": 10, "days_max": 20}],
            variants=[],
        )
        result = enrich_product(
            match, all_ali_products_for_keyword=[match.ali_product, extra_supplier]
        )
        assert result.supplier_data["supplier_count"] == 2
        assert result.supplier_data["best_price"] == 3.80
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_enricher.py -v`

Expected: FAIL with ImportError

- [ ] **Step 3: Implement enricher**

`src/pipeline/enricher.py`:
```python
from dataclasses import dataclass, field

import yaml

from config.settings import settings
from src.collectors.aliexpress import AliExpressProduct
from src.pipeline.matcher import Match


@dataclass
class EnrichedProduct:
    title: str
    category: str
    image_urls: list[str]
    regions: list[str]
    tiktok_data: dict
    supplier_data: dict
    competition: dict
    pricing: dict


def _load_margin_config() -> dict:
    with open(settings.scoring_weights_path) as f:
        config = yaml.safe_load(f)
    return config["margin"]


def enrich_product(
    match: Match,
    all_ali_products_for_keyword: list[AliExpressProduct],
) -> EnrichedProduct:
    """Enrich a matched product with pricing, competition, and supplier data."""
    margin_config = _load_margin_config()
    markup_min = margin_config["markup_min"]
    markup_max = margin_config["markup_max"]
    platform_fee = margin_config["platform_fee_percent"] / 100

    tiktok = match.tiktok_product
    ali = match.ali_product

    # Supplier data from all matching AliExpress products
    listings = []
    for product in all_ali_products_for_keyword:
        listings.append({
            "product_id": product.product_id,
            "url": product.url,
            "price": product.price,
            "shipping": product.shipping,
            "order_count": product.order_count,
            "rating": product.rating,
            "seller_name": product.seller_name,
            "variants": product.variants,
        })

    best_price = min(p.price for p in all_ali_products_for_keyword)
    best_shipping_cost = 0.0
    if ali.shipping:
        best_shipping_cost = min(s["cost"] for s in ali.shipping)

    # Pricing
    sell_min = best_price * markup_min
    sell_max = best_price * markup_max
    margin_min = sell_min - best_price - best_shipping_cost - (sell_min * platform_fee)
    margin_max = sell_max - best_price - best_shipping_cost - (sell_max * platform_fee)
    margin_percent_min = (margin_min / sell_min * 100) if sell_min > 0 else 0
    margin_percent_max = (margin_max / sell_max * 100) if sell_max > 0 else 0

    # Images: prefer AliExpress product images, fallback to TikTok thumbnail
    image_urls = ali.images if ali.images else [tiktok.thumbnail]

    return EnrichedProduct(
        title=tiktok.title,
        category=tiktok.category,
        image_urls=image_urls,
        regions=tiktok.regions,
        tiktok_data={
            "advertiser_count": tiktok.advertiser_count,
            "creative_count": tiktok.creative_count,
            "ad_duration_days": tiktok.ad_duration_days,
            "hashtag_views": tiktok.hashtag_views,
            "engagement": tiktok.engagement,
            "sample_creatives": tiktok.sample_creatives,
        },
        supplier_data={
            "listings": listings,
            "best_price": best_price,
            "best_margin": margin_max,
            "supplier_count": len(all_ali_products_for_keyword),
        },
        competition={
            "estimated_sellers": tiktok.advertiser_count,
            "supplier_count": len(all_ali_products_for_keyword),
        },
        pricing={
            "cost_min": best_price,
            "cost_max": max(p.price for p in all_ali_products_for_keyword),
            "suggested_sell_price_min": sell_min,
            "suggested_sell_price_max": sell_max,
            "estimated_margin_min": round(margin_min, 2),
            "estimated_margin_max": round(margin_max, 2),
            "estimated_margin_percent_min": round(margin_percent_min, 1),
            "estimated_margin_percent_max": round(margin_percent_max, 1),
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_enricher.py -v`

Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/enricher.py tests/unit/test_enricher.py
git commit -m "feat: product enricher with margin and supplier calculations"
```

---

### Task 10: Pipeline Orchestrator

**Files:**
- Create: `src/pipeline/orchestrator.py`
- Test: `tests/integration/test_pipeline.py`

- [ ] **Step 1: Write integration test for pipeline**

`tests/integration/test_pipeline.py`:
```python
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
        # Mock TikTok collector
        mock_tiktok = AsyncMock()
        mock_tiktok.collect.return_value = mock_tiktok.parse_response(tiktok_fixture)
        mock_tiktok_cls.return_value = mock_tiktok

        # Use real parse for setup
        from src.collectors.tiktok import TikTokCollector
        real_tiktok = TikTokCollector()
        mock_tiktok.collect.return_value = real_tiktok.parse_response(tiktok_fixture)

        # Mock AliExpress collector
        from src.collectors.aliexpress import AliExpressCollector
        real_ali = AliExpressCollector()
        mock_ali = AsyncMock()
        mock_ali.search.return_value = real_ali.parse_response(aliexpress_fixture)
        mock_ali_cls.return_value = mock_ali

        await run_pipeline(db)

        # Check product cards were created
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

        # Should not raise — handles failure gracefully
        await run_pipeline(db)

        result = await db.execute(select(CollectionRun))
        runs = result.scalars().all()
        failed_run = next(r for r in runs if r.source == "tiktok")
        assert failed_run.status.value == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_pipeline.py -v`

Expected: FAIL with ImportError

- [ ] **Step 3: Implement orchestrator**

`src/pipeline/orchestrator.py`:
```python
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.collectors.aliexpress import AliExpressCollector
from src.collectors.tiktok import TikTokCollector
from src.models import CollectionRun, CollectionStatus, ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory
from src.pipeline.enricher import enrich_product
from src.pipeline.matcher import find_best_match
from src.pipeline.scorer import (
    calculate_competition,
    calculate_trend_score,
    calculate_velocity,
    determine_status,
)

logger = logging.getLogger(__name__)


async def run_pipeline(db: AsyncSession) -> None:
    """Run the full data pipeline: collect, match, enrich, score, store."""

    # 1. Collect from TikTok
    tiktok_products = []
    tiktok_run = CollectionRun(source="tiktok", status=CollectionStatus.failed)
    db.add(tiktok_run)

    try:
        collector = TikTokCollector()
        tiktok_products = await collector.collect()
        tiktok_run.status = CollectionStatus.success
        tiktok_run.items_collected = len(tiktok_products)
    except Exception as e:
        logger.error(f"TikTok collection failed: {e}")
        tiktok_run.errors = {"message": str(e)}
    finally:
        tiktok_run.completed_at = datetime.now(timezone.utc)

    if not tiktok_products:
        await db.commit()
        return

    # 2. For each TikTok product, search AliExpress and match
    ali_collector = AliExpressCollector()
    matches = []

    for tiktok_product in tiktok_products:
        try:
            ali_products = await ali_collector.search(tiktok_product.title)
            match = find_best_match(tiktok_product, ali_products)
            if match:
                matches.append((match, ali_products))
        except Exception as e:
            logger.warning(f"AliExpress search failed for '{tiktok_product.title}': {e}")

    # 3. Enrich matched products
    enriched_products = []
    for match, ali_products in matches:
        enriched = enrich_product(match, ali_products)
        enriched_products.append(enriched)

    # 4. Score all products together
    all_signals = []
    for match, _ in matches:
        signals = {
            "advertiser_count": match.tiktok_product.advertiser_count,
            "ad_duration": match.tiktok_product.ad_duration_days,
            "creative_volume": match.tiktok_product.creative_count,
            "engagement_velocity": match.tiktok_product.hashtag_views,
            "order_volume_growth": match.ali_product.order_count,
            "supplier_availability": len([p for p in _ if p]),
        }
        all_signals.append(signals)

    # 5. Store product cards
    for i, enriched in enumerate(enriched_products):
        signals = all_signals[i]
        score = calculate_trend_score(signals, all_signals)

        # Check if product already exists (by title match)
        existing_result = await db.execute(
            select(ProductCard).where(ProductCard.title == enriched.title)
        )
        existing = existing_result.scalar_one_or_none()

        if existing:
            # Update existing card
            existing.trend_score = score
            existing.last_seen_at = datetime.now(timezone.utc)
            existing.tiktok_data = enriched.tiktok_data
            existing.supplier_data = enriched.supplier_data
            existing.competition = enriched.competition
            existing.pricing = enriched.pricing
            existing.regions = enriched.regions

            # Calculate velocity from history
            history_result = await db.execute(
                select(ScoreHistory)
                .where(ScoreHistory.product_card_id == existing.id)
                .order_by(ScoreHistory.recorded_at.asc())
            )
            history = [h.trend_score for h in history_result.scalars().all()]
            history.append(score)

            velocity_str = calculate_velocity(history)
            existing.trend_velocity = TrendVelocity(velocity_str)

            # Determine status
            declining_runs = 0
            if velocity_str == "decelerating":
                # Count consecutive declining runs
                for h_score in reversed(history[:-1]):
                    if h_score > score:
                        declining_runs += 1
                    else:
                        break

            competition = calculate_competition(
                signals["advertiser_count"], enriched.supplier_data["supplier_count"]
            )
            existing.competition = {
                **enriched.competition,
                "saturation_level": competition,
            }

            status_str = determine_status(score, velocity_str, declining_runs)
            existing.status = ProductStatus(status_str)

            # Record score history
            db.add(ScoreHistory(product_card_id=existing.id, trend_score=score))
        else:
            # Create new card
            competition = calculate_competition(
                signals["advertiser_count"], enriched.supplier_data["supplier_count"]
            )
            card = ProductCard(
                title=enriched.title,
                category=enriched.category,
                image_urls=enriched.image_urls,
                trend_score=score,
                trend_velocity=TrendVelocity.stable,
                regions=enriched.regions,
                status=ProductStatus.trending,
                tiktok_data=enriched.tiktok_data,
                supplier_data=enriched.supplier_data,
                competition={**enriched.competition, "saturation_level": competition},
                pricing=enriched.pricing,
            )
            db.add(card)
            await db.flush()
            db.add(ScoreHistory(product_card_id=card.id, trend_score=score))

    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_pipeline.py -v`

Expected: All 3 tests PASS (requires running PostgreSQL test database)

- [ ] **Step 5: Commit**

```bash
git add src/pipeline/orchestrator.py tests/integration/test_pipeline.py
git commit -m "feat: pipeline orchestrator integrating collect, match, enrich, score, store"
```

---

### Task 11: Auth Service (TDD)

**Files:**
- Create: `src/services/auth_service.py`
- Create: `src/services/__init__.py`
- Test: `tests/integration/test_auth_api.py`

- [ ] **Step 1: Write failing tests**

`tests/integration/test_auth_api.py`:
```python
import pytest
from httpx import AsyncClient


class TestRegister:
    async def test_register_success(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "password": "securepass123",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["data"]["email"] == "test@example.com"
        assert data["data"]["subscription_tier"] == "free"
        assert "password" not in data["data"]

    async def test_register_duplicate_email(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "email": "dupe@example.com",
            "password": "pass123",
        })
        response = await client.post("/api/v1/auth/register", json={
            "email": "dupe@example.com",
            "password": "pass456",
        })
        assert response.status_code == 409

    async def test_register_invalid_email(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "pass123",
        })
        assert response.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "email": "login@example.com",
            "password": "mypassword",
        })
        response = await client.post("/api/v1/auth/login", json={
            "email": "login@example.com",
            "password": "mypassword",
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "email": "wrong@example.com",
            "password": "correct",
        })
        response = await client.post("/api/v1/auth/login", json={
            "email": "wrong@example.com",
            "password": "incorrect",
        })
        assert response.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        response = await client.post("/api/v1/auth/login", json={
            "email": "noone@example.com",
            "password": "anything",
        })
        assert response.status_code == 401


class TestMe:
    async def test_get_me_authenticated(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "email": "me@example.com",
            "password": "mypass",
        })
        login = await client.post("/api/v1/auth/login", json={
            "email": "me@example.com",
            "password": "mypass",
        })
        token = login.json()["data"]["access_token"]
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json()["data"]["email"] == "me@example.com"

    async def test_get_me_unauthenticated(self, client: AsyncClient):
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_auth_api.py -v`

Expected: FAIL with ImportError or 404s

- [ ] **Step 3: Implement auth service**

`src/services/__init__.py` (empty).

`src/services/auth_service.py`:
```python
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from src.models.user import User

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expire_minutes)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> str | None:
    """Decode JWT and return user_id, or None if invalid."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except JWTError:
        return None


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user and verify_password(password, user.hashed_password):
        return user
    return None


async def get_user_by_id(db: AsyncSession, user_id: str) -> User | None:
    result = await db.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()
```

- [ ] **Step 4: Implement auth API routes**

`src/api/__init__.py` (empty).
`src/api/routes/__init__.py` (empty).

`src/api/schemas.py`:
```python
from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    subscription_tier: str
    region_preference: str | None

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ApiResponse(BaseModel):
    status: str = "ok"
    data: dict | list | None = None
    meta: dict | None = None


class ErrorResponse(BaseModel):
    status: str = "error"
    error: dict
```

`src/api/dependencies.py`:
```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.models.user import SubscriptionTier, User
from src.services.auth_service import decode_access_token, get_user_by_id

security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user_id = decode_access_token(credentials.credentials)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def require_tier(minimum: SubscriptionTier):
    """Dependency that requires a minimum subscription tier."""
    tier_order = [SubscriptionTier.free, SubscriptionTier.basic, SubscriptionTier.pro, SubscriptionTier.enterprise]

    def checker(user: User = Depends(get_current_user)):
        user_level = tier_order.index(user.subscription_tier)
        required_level = tier_order.index(minimum)
        if user_level < required_level:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires {minimum.value} tier or higher",
            )
        return user

    return checker
```

`src/api/routes/auth.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.api.schemas import LoginRequest, RegisterRequest
from src.database import get_db
from src.models.user import User
from src.services.auth_service import authenticate_user, create_access_token, register_user

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, request.email, request.password)
    except IntegrityError:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    return {
        "status": "ok",
        "data": {
            "id": str(user.id),
            "email": user.email,
            "subscription_tier": user.subscription_tier.value,
            "region_preference": user.region_preference,
        },
    }


@router.post("/login")
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(str(user.id))
    return {
        "status": "ok",
        "data": {"access_token": token, "token_type": "bearer"},
    }


@router.get("/me")
async def me(user: User = Depends(get_current_user)):
    return {
        "status": "ok",
        "data": {
            "id": str(user.id),
            "email": user.email,
            "subscription_tier": user.subscription_tier.value,
            "region_preference": user.region_preference,
        },
    }
```

- [ ] **Step 5: Register auth router in main.py**

Update `src/main.py`:
```python
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
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/integration/test_auth_api.py -v`

Expected: All 7 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/services/ src/api/ src/main.py tests/integration/test_auth_api.py
git commit -m "feat: auth system with register, login, JWT, and tier checking"
```

---

### Task 12: Products API (TDD)

**Files:**
- Create: `src/services/product_service.py`
- Create: `src/api/routes/products.py`
- Test: `tests/integration/test_products_api.py`

- [ ] **Step 1: Write failing tests**

`tests/integration/test_products_api.py`:
```python
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory


@pytest.fixture
async def sample_products(db: AsyncSession):
    """Create sample product cards for testing."""
    products = [
        ProductCard(
            title="Portable Neck Fan",
            category="Electronics",
            image_urls=["https://example.com/fan.jpg"],
            trend_score=85,
            trend_velocity=TrendVelocity.accelerating,
            regions=["US", "EU", "SEA"],
            status=ProductStatus.trending,
            tiktok_data={"advertiser_count": 45, "creative_count": 120},
            supplier_data={"best_price": 4.50, "supplier_count": 5, "listings": []},
            competition={"saturation_level": "medium", "estimated_sellers": 45},
            pricing={"suggested_sell_price_min": 11.25, "estimated_margin_min": 3.69},
        ),
        ProductCard(
            title="LED Galaxy Projector",
            category="Home & Garden",
            image_urls=["https://example.com/projector.jpg"],
            trend_score=62,
            trend_velocity=TrendVelocity.stable,
            regions=["US", "EU"],
            status=ProductStatus.trending,
            tiktok_data={"advertiser_count": 28, "creative_count": 75},
            supplier_data={"best_price": 8.20, "supplier_count": 3, "listings": []},
            competition={"saturation_level": "medium", "estimated_sellers": 28},
            pricing={"suggested_sell_price_min": 20.50, "estimated_margin_min": 8.47},
        ),
        ProductCard(
            title="Old Trend Widget",
            category="Gadgets",
            image_urls=[],
            trend_score=15,
            trend_velocity=TrendVelocity.decelerating,
            regions=["US"],
            status=ProductStatus.expired,
            tiktok_data={"advertiser_count": 2, "creative_count": 3},
            supplier_data={"best_price": 2.00, "supplier_count": 1, "listings": []},
            competition={"saturation_level": "low", "estimated_sellers": 2},
            pricing={"suggested_sell_price_min": 5.00, "estimated_margin_min": 1.50},
        ),
    ]
    for p in products:
        db.add(p)
    await db.commit()
    for p in products:
        await db.refresh(p)
    return products


@pytest.fixture
async def auth_headers(client: AsyncClient):
    """Register and login, return auth headers."""
    await client.post("/api/v1/auth/register", json={
        "email": "products@test.com",
        "password": "testpass",
    })
    login = await client.post("/api/v1/auth/login", json={
        "email": "products@test.com",
        "password": "testpass",
    })
    token = login.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {token}"}


class TestListProducts:
    async def test_list_default_returns_trending(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        # Default filters to trending only
        assert all(p["status"] == "trending" for p in data["data"])

    async def test_list_with_region_filter(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products?region=SEA", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["title"] == "Portable Neck Fan"

    async def test_list_with_min_score(self, client, auth_headers, sample_products):
        response = await client.get("/api/v1/products?min_score=70", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["data"]) == 1
        assert data["data"][0]["trend_score"] >= 70

    async def test_list_sorted_by_score_desc(self, client, auth_headers, sample_products):
        response = await client.get(
            "/api/v1/products?sort=score&order=desc", headers=auth_headers
        )
        data = response.json()
        scores = [p["trend_score"] for p in data["data"]]
        assert scores == sorted(scores, reverse=True)

    async def test_list_pagination(self, client, auth_headers, sample_products):
        response = await client.get(
            "/api/v1/products?limit=1&page=1", headers=auth_headers
        )
        data = response.json()
        assert len(data["data"]) == 1
        assert data["meta"]["limit"] == 1
        assert data["meta"]["page"] == 1
        assert data["meta"]["total"] == 2  # only 2 trending

    async def test_list_requires_auth(self, client, sample_products):
        response = await client.get("/api/v1/products")
        assert response.status_code == 401


class TestGetProduct:
    async def test_get_by_id(self, client, auth_headers, sample_products):
        product_id = str(sample_products[0].id)
        response = await client.get(f"/api/v1/products/{product_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["title"] == "Portable Neck Fan"
        assert data["trend_score"] == 85

    async def test_get_nonexistent(self, client, auth_headers):
        fake_id = str(uuid.uuid4())
        response = await client.get(f"/api/v1/products/{fake_id}", headers=auth_headers)
        assert response.status_code == 404


class TestGetProductHistory:
    async def test_get_history(self, client, auth_headers, sample_products, db: AsyncSession):
        product = sample_products[0]
        # Add score history
        for i, score in enumerate([60, 70, 80, 85]):
            db.add(ScoreHistory(
                product_card_id=product.id,
                trend_score=score,
                recorded_at=datetime.now(timezone.utc) - timedelta(days=3 - i),
            ))
        await db.commit()

        response = await client.get(
            f"/api/v1/products/{product.id}/history", headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert len(data) == 4
        assert data[-1]["trend_score"] == 85
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_products_api.py -v`

Expected: FAIL with 404s or ImportError

- [ ] **Step 3: Implement product service**

`src/services/product_service.py`:
```python
import uuid

from sqlalchemy import Select, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory


def _build_product_query(
    region: str | None = None,
    category: str | None = None,
    status: str = "trending",
    min_score: int | None = None,
    velocity: str | None = None,
    saturation: str | None = None,
    min_margin: float | None = None,
    sort: str = "score",
    order: str = "desc",
) -> Select:
    query = select(ProductCard)

    # Filters
    if status:
        query = query.where(ProductCard.status == ProductStatus(status))
    if region:
        query = query.where(ProductCard.regions.any(region))
    if category:
        query = query.where(ProductCard.category == category)
    if min_score is not None:
        query = query.where(ProductCard.trend_score >= min_score)
    if velocity:
        query = query.where(ProductCard.trend_velocity == TrendVelocity(velocity))
    if saturation:
        query = query.where(
            ProductCard.competition["saturation_level"].astext == saturation
        )
    if min_margin is not None:
        query = query.where(
            ProductCard.pricing["estimated_margin_min"].astext.cast(float) >= min_margin
        )

    # Sorting
    sort_column_map = {
        "score": ProductCard.trend_score,
        "velocity": ProductCard.trend_velocity,
        "margin": ProductCard.pricing["estimated_margin_min"].astext,
        "first_seen": ProductCard.first_seen_at,
        "last_seen": ProductCard.last_seen_at,
    }
    sort_col = sort_column_map.get(sort, ProductCard.trend_score)
    if order == "asc":
        query = query.order_by(sort_col)
    else:
        query = query.order_by(desc(sort_col))

    return query


async def list_products(
    db: AsyncSession,
    page: int = 1,
    limit: int = 20,
    **filters,
) -> tuple[list[ProductCard], int]:
    """List products with filtering, sorting, and pagination."""
    query = _build_product_query(**filters)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    # Paginate
    offset = (page - 1) * limit
    query = query.offset(offset).limit(limit)

    result = await db.execute(query)
    products = list(result.scalars().all())
    return products, total


async def get_product(db: AsyncSession, product_id: uuid.UUID) -> ProductCard | None:
    result = await db.execute(select(ProductCard).where(ProductCard.id == product_id))
    return result.scalar_one_or_none()


async def get_product_history(
    db: AsyncSession, product_id: uuid.UUID
) -> list[ScoreHistory]:
    result = await db.execute(
        select(ScoreHistory)
        .where(ScoreHistory.product_card_id == product_id)
        .order_by(ScoreHistory.recorded_at.asc())
    )
    return list(result.scalars().all())
```

- [ ] **Step 4: Implement products API route**

`src/api/routes/products.py`:
```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_user
from src.database import get_db
from src.models.user import User
from src.services.product_service import get_product, get_product_history, list_products

router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _serialize_product(product) -> dict:
    return {
        "id": str(product.id),
        "title": product.title,
        "category": product.category,
        "image_urls": product.image_urls,
        "trend_score": product.trend_score,
        "trend_velocity": product.trend_velocity.value,
        "first_seen_at": product.first_seen_at.isoformat(),
        "last_seen_at": product.last_seen_at.isoformat(),
        "regions": product.regions,
        "status": product.status.value,
        "tiktok_data": product.tiktok_data,
        "supplier_data": product.supplier_data,
        "competition": product.competition,
        "pricing": product.pricing,
    }


@router.get("")
async def list_products_endpoint(
    region: str | None = Query(None),
    category: str | None = Query(None),
    status_filter: str = Query("trending", alias="status"),
    min_score: int | None = Query(None, ge=0, le=100),
    velocity: str | None = Query(None),
    saturation: str | None = Query(None),
    min_margin: float | None = Query(None),
    sort: str = Query("score"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    products, total = await list_products(
        db,
        page=page,
        limit=limit,
        region=region,
        category=category,
        status=status_filter,
        min_score=min_score,
        velocity=velocity,
        saturation=saturation,
        min_margin=min_margin,
        sort=sort,
        order=order,
    )
    return {
        "status": "ok",
        "data": [_serialize_product(p) for p in products],
        "meta": {"page": page, "limit": limit, "total": total},
    }


@router.get("/{product_id}")
async def get_product_endpoint(
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return {"status": "ok", "data": _serialize_product(product)}


@router.get("/{product_id}/history")
async def get_history_endpoint(
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await get_product(db, product_id)
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    history = await get_product_history(db, product_id)
    return {
        "status": "ok",
        "data": [
            {"trend_score": h.trend_score, "recorded_at": h.recorded_at.isoformat()}
            for h in history
        ],
    }
```

- [ ] **Step 5: Register products router in main.py**

Update `src/main.py`:
```python
from fastapi import FastAPI

from src.api.routes.auth import router as auth_router
from src.api.routes.products import router as products_router

app = FastAPI(
    title="Trending Products API",
    version="0.1.0",
    description="Discover market-validated trending products to sell",
)

app.include_router(auth_router)
app.include_router(products_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/integration/test_products_api.py -v`

Expected: All 8 tests PASS

- [ ] **Step 7: Commit**

```bash
git add src/services/product_service.py src/api/routes/products.py src/main.py tests/integration/test_products_api.py
git commit -m "feat: products API with filtering, sorting, pagination, and history"
```

---

### Task 13: Rate Limiting & Tier Gating

**Files:**
- Modify: `src/api/dependencies.py`
- Modify: `src/api/routes/products.py`
- Create: `src/api/routes/health.py`

- [ ] **Step 1: Implement Redis-based rate limiting in dependencies**

Add to `src/api/dependencies.py`:
```python
import redis.asyncio as redis
from fastapi import Request

from config.settings import settings
from src.models.user import SubscriptionTier

TIER_LIMITS = {
    SubscriptionTier.free: {"queries_per_day": 10, "products_per_query": 5, "regions": 1},
    SubscriptionTier.basic: {"queries_per_day": 100, "products_per_query": 20, "regions": 3},
    SubscriptionTier.pro: {"queries_per_day": 500, "products_per_query": 50, "regions": None},
    SubscriptionTier.enterprise: {"queries_per_day": None, "products_per_query": None, "regions": None},
}

_redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(settings.redis_url)
    return _redis_client


async def check_rate_limit(user: User = Depends(get_current_user)) -> User:
    """Check and increment the user's daily query count."""
    limits = TIER_LIMITS[user.subscription_tier]
    max_queries = limits["queries_per_day"]

    if max_queries is None:  # unlimited
        return user

    r = await get_redis()
    key = f"rate_limit:{user.id}:{datetime.now(timezone.utc).date()}"
    current = await r.incr(key)

    if current == 1:
        await r.expire(key, 86400)  # expire after 24h

    if current > max_queries:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily query limit ({max_queries}) exceeded",
        )

    return user
```

Add these imports at the top of `src/api/dependencies.py`:
```python
from datetime import datetime, timezone
import redis.asyncio as redis
```

- [ ] **Step 2: Apply rate limiting and tier limits to products route**

Update the `list_products_endpoint` in `src/api/routes/products.py` to use rate limiting:
```python
@router.get("")
async def list_products_endpoint(
    region: str | None = Query(None),
    category: str | None = Query(None),
    status_filter: str = Query("trending", alias="status"),
    min_score: int | None = Query(None, ge=0, le=100),
    velocity: str | None = Query(None),
    saturation: str | None = Query(None),
    min_margin: float | None = Query(None),
    sort: str = Query("score"),
    order: str = Query("desc"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(check_rate_limit),
    db: AsyncSession = Depends(get_db),
):
    # Enforce tier-based limit on results
    tier_limits = TIER_LIMITS[user.subscription_tier]
    max_products = tier_limits["products_per_query"]
    if max_products is not None:
        limit = min(limit, max_products)

    products, total = await list_products(
        db,
        page=page,
        limit=limit,
        region=region,
        category=category,
        status=status_filter,
        min_score=min_score,
        velocity=velocity,
        saturation=saturation,
        min_margin=min_margin,
        sort=sort,
        order=order,
    )
    return {
        "status": "ok",
        "data": [_serialize_product(p) for p in products],
        "meta": {"page": page, "limit": limit, "total": total},
    }
```

Add import at top of `src/api/routes/products.py`:
```python
from src.api.dependencies import check_rate_limit, get_current_user, TIER_LIMITS
```

- [ ] **Step 3: Create health and pipeline status endpoints**

`src/api/routes/health.py`:
```python
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
```

- [ ] **Step 4: Update main.py with health router and remove inline health endpoint**

```python
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
```

- [ ] **Step 5: Run all tests**

Run: `pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/ src/main.py
git commit -m "feat: rate limiting, tier gating, and pipeline status endpoint"
```

---

### Task 14: Custom Error Handling & API Keys

**Files:**
- Modify: `src/main.py`
- Modify: `src/api/routes/auth.py`
- Modify: `src/services/auth_service.py`

- [ ] **Step 1: Add custom exception handler to main.py for consistent error format**

Add to `src/main.py` after router registration:

```python
import uuid as uuid_mod

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    code = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
    }.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"status": "error", "error": {"code": code, "message": str(exc.detail)}},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"status": "error", "error": {"code": "VALIDATION_ERROR", "message": str(exc.errors())}},
    )
```

- [ ] **Step 2: Add API key generation and revocation to auth_service.py**

Add to `src/services/auth_service.py`:

```python
import secrets

from src.models.api_key import ApiKey


def generate_api_key() -> tuple[str, str]:
    """Generate an API key. Returns (raw_key, hashed_key)."""
    raw_key = f"tp_{secrets.token_urlsafe(32)}"
    hashed = pwd_context.hash(raw_key)
    return raw_key, hashed


async def create_api_key(db: AsyncSession, user_id: str, name: str) -> tuple[ApiKey, str]:
    """Create an API key for a user. Returns (api_key_record, raw_key)."""
    raw_key, hashed = generate_api_key()
    api_key = ApiKey(user_id=user_id, key_hash=hashed, name=name)
    db.add(api_key)
    await db.commit()
    await db.refresh(api_key)
    return api_key, raw_key


async def delete_api_key(db: AsyncSession, key_id: str, user_id: str) -> bool:
    """Delete an API key. Returns True if deleted, False if not found."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.user_id == user_id)
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        return False
    await db.delete(api_key)
    await db.commit()
    return True
```

- [ ] **Step 3: Add API key routes to auth.py**

Add to `src/api/routes/auth.py`:

```python
from src.api.dependencies import require_tier
from src.models.user import SubscriptionTier
from src.services.auth_service import create_api_key, delete_api_key


@router.post("/api-keys", status_code=status.HTTP_201_CREATED)
async def generate_api_key(
    name: str = "default",
    user: User = Depends(require_tier(SubscriptionTier.enterprise)),
    db: AsyncSession = Depends(get_db),
):
    api_key, raw_key = await create_api_key(db, str(user.id), name)
    return {
        "status": "ok",
        "data": {
            "id": str(api_key.id),
            "name": api_key.name,
            "key": raw_key,  # Only shown once
            "created_at": api_key.created_at.isoformat(),
        },
    }


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    key_id: str,
    user: User = Depends(require_tier(SubscriptionTier.enterprise)),
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_api_key(db, key_id, str(user.id))
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")
    return {"status": "ok", "data": {"deleted": True}}
```

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`

Expected: All tests PASS (error format test may need updating in auth tests to match new format)

- [ ] **Step 5: Commit**

```bash
git add src/main.py src/api/routes/auth.py src/services/auth_service.py
git commit -m "feat: custom error responses and API key generation/revocation"
```

---

### Task 15: Scheduler

**Files:**
- Create: `src/scheduler/__init__.py`
- Create: `src/scheduler/jobs.py`

- [ ] **Step 1: Implement the scheduler**

`src/scheduler/__init__.py` (empty).

`src/scheduler/jobs.py`:
```python
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


def main():
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

    # Run the event loop
    try:
        asyncio.get_event_loop().run_forever()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down scheduler")
        scheduler.shutdown()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify scheduler starts without errors**

Run: `python -c "from src.scheduler.jobs import main; print('Import OK')"`

Expected: `Import OK`

- [ ] **Step 3: Commit**

```bash
git add src/scheduler/
git commit -m "feat: APScheduler pipeline job running every 12 hours"
```

---

### Task 16: Seed Script & Final Integration

**Files:**
- Create: `scripts/seed_data.py`
- Create: `.gitignore`

- [ ] **Step 1: Create seed script for development**

`scripts/seed_data.py`:
```python
"""Insert sample product cards for local development."""
import asyncio
from datetime import datetime, timedelta, timezone

from src.database import async_session, engine
from src.models import Base, ProductCard, ProductStatus, TrendVelocity
from src.models.score_history import ScoreHistory


SAMPLE_PRODUCTS = [
    {
        "title": "Portable Neck Fan",
        "category": "Electronics",
        "image_urls": ["https://example.com/neck-fan-1.jpg"],
        "trend_score": 85,
        "trend_velocity": TrendVelocity.accelerating,
        "regions": ["US", "EU", "SEA"],
        "status": ProductStatus.trending,
        "tiktok_data": {
            "advertiser_count": 45,
            "creative_count": 120,
            "ad_duration_days": 14,
            "hashtag_views": 5200000,
            "engagement": {"likes": 320000, "shares": 45000},
        },
        "supplier_data": {
            "listings": [
                {"url": "https://aliexpress.com/item/001.html", "price": 4.50, "order_count": 15000}
            ],
            "best_price": 4.50,
            "best_margin": 7.05,
            "supplier_count": 5,
        },
        "competition": {"saturation_level": "medium", "estimated_sellers": 45, "supplier_count": 5},
        "pricing": {
            "cost_min": 4.50,
            "suggested_sell_price_min": 11.25,
            "suggested_sell_price_max": 13.50,
            "estimated_margin_min": 3.69,
            "estimated_margin_max": 7.05,
            "estimated_margin_percent_min": 32.8,
            "estimated_margin_percent_max": 52.2,
        },
    },
    {
        "title": "LED Galaxy Projector",
        "category": "Home & Garden",
        "image_urls": ["https://example.com/galaxy-1.jpg"],
        "trend_score": 72,
        "trend_velocity": TrendVelocity.stable,
        "regions": ["US", "EU"],
        "status": ProductStatus.trending,
        "tiktok_data": {
            "advertiser_count": 28,
            "creative_count": 75,
            "ad_duration_days": 21,
            "hashtag_views": 3100000,
            "engagement": {"likes": 180000, "shares": 28000},
        },
        "supplier_data": {
            "listings": [
                {"url": "https://aliexpress.com/item/003.html", "price": 8.20, "order_count": 22000}
            ],
            "best_price": 8.20,
            "best_margin": 13.44,
            "supplier_count": 3,
        },
        "competition": {"saturation_level": "medium", "estimated_sellers": 28, "supplier_count": 3},
        "pricing": {
            "cost_min": 8.20,
            "suggested_sell_price_min": 20.50,
            "suggested_sell_price_max": 24.60,
            "estimated_margin_min": 8.47,
            "estimated_margin_max": 13.44,
            "estimated_margin_percent_min": 41.3,
            "estimated_margin_percent_max": 54.6,
        },
    },
    {
        "title": "Magnetic Phone Mount for Car",
        "category": "Accessories",
        "image_urls": ["https://example.com/mount-1.jpg"],
        "trend_score": 45,
        "trend_velocity": TrendVelocity.decelerating,
        "regions": ["US"],
        "status": ProductStatus.declining,
        "tiktok_data": {
            "advertiser_count": 8,
            "creative_count": 15,
            "ad_duration_days": 30,
            "hashtag_views": 800000,
            "engagement": {"likes": 50000, "shares": 7000},
        },
        "supplier_data": {
            "listings": [
                {"url": "https://aliexpress.com/item/005.html", "price": 2.10, "order_count": 8000}
            ],
            "best_price": 2.10,
            "best_margin": 3.93,
            "supplier_count": 12,
        },
        "competition": {"saturation_level": "low", "estimated_sellers": 8, "supplier_count": 12},
        "pricing": {
            "cost_min": 2.10,
            "suggested_sell_price_min": 5.25,
            "suggested_sell_price_max": 6.30,
            "estimated_margin_min": 2.37,
            "estimated_margin_max": 3.93,
            "estimated_margin_percent_min": 45.1,
            "estimated_margin_percent_max": 62.4,
        },
    },
]


async def seed():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session() as db:
        for product_data in SAMPLE_PRODUCTS:
            card = ProductCard(**product_data)
            db.add(card)
            await db.flush()

            # Add score history
            now = datetime.now(timezone.utc)
            for i in range(5):
                base_score = product_data["trend_score"] - (5 - i) * 5
                db.add(ScoreHistory(
                    product_card_id=card.id,
                    trend_score=max(0, base_score),
                    recorded_at=now - timedelta(days=5 - i),
                ))

        await db.commit()
        print(f"Seeded {len(SAMPLE_PRODUCTS)} product cards with score history")


if __name__ == "__main__":
    asyncio.run(seed())
```

- [ ] **Step 2: Create .gitignore**

`.gitignore`:
```
__pycache__/
*.py[cod]
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.superpowers/
```

- [ ] **Step 3: Run seed script to verify it works**

Run: `python -m scripts.seed_data`

Expected: `Seeded 3 product cards with score history`

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v --tb=short`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/seed_data.py .gitignore
git commit -m "feat: seed script and gitignore for development"
```

---

### Task 17: Final Verification

- [ ] **Step 1: Start full stack**

Run: `docker compose up --build -d`

Expected: All 4 services start (api, worker, postgres, redis)

- [ ] **Step 2: Verify health endpoint**

Run: `curl http://localhost:8000/health`

Expected: `{"status":"ok"}`

- [ ] **Step 3: Test full auth + products flow**

```bash
# Register
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@test.com","password":"demo123"}'

# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@test.com","password":"demo123"}'

# Use the returned token to list products
curl http://localhost:8000/api/v1/products \
  -H "Authorization: Bearer <TOKEN>"
```

Expected: Registration returns 201, login returns token, products returns list with data.

- [ ] **Step 4: Run full test suite one final time**

Run: `pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 5: Final commit (if any cleanup needed)**

```bash
git status
# Only commit if there are changes
```
