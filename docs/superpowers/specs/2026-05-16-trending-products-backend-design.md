# Trending Products Backend API — Design Spec

## Overview

A batch-processing backend API that collects trending product data from TikTok Creative Center and AliExpress twice daily, scores and enriches it, and serves pre-computed product cards via a REST API. Built for e-commerce sellers (dropshippers, FBA, store owners, agencies) to discover market-validated niche products to sell.

## Decisions

- **Scope:** Backend API only (frontend is a separate future project)
- **Tech stack:** Python, FastAPI, PostgreSQL, Redis, Docker Compose
- **Data sources (MVP):** TikTok Creative Center + AliExpress (Meta Ad Library next)
- **Data freshness:** 2x daily uniform schedule across all sources
- **Monetization:** SaaS subscription tiers (free/basic/pro/enterprise), API-as-a-service tier added later
- **Regional:** Products tagged with regions where they're trending, users filter by region or view global
- **Seasonality:** Deferred to a later phase
- **Hosting:** Containerized, cloud-agnostic (Docker Compose for dev, deploy wherever)

## Pipeline Architecture

Batch pipeline runs 2x/day: Collect → Match → Enrich → Score → Store.

```
[Scheduler] → [TikTok Collector] → [Matcher] → [Enricher] → [Scoring Engine] → [PostgreSQL]
              [AliExpress Collector] ↗                                                 ↓
                                                                                [FastAPI] → Users
                                                                                [Redis cache]
```

### Pipeline Stages

1. **Collect** — TikTok collector fetches trending products, hashtags, and ad creatives. AliExpress collector fetches product listings, pricing, shipping, and order counts.
2. **Match** — Cross-reference TikTok trends with AliExpress products by keyword Jaccard similarity (>0.6) or image perceptual hash match (Hamming distance <10). Unmatched trends stored but flagged as "unsourceable."
3. **Enrich** — For matched products: pull supplier options, shipping times per region, calculate margins at suggested sell prices, estimate competition.
4. **Score** — Compute trend score (0-100) based on weighted signals. Tag with regions. Calculate velocity.
5. **Store** — Write product cards to PostgreSQL. Update existing cards to track velocity.

### Components

| Component | Responsibility |
|-----------|---------------|
| Scheduler (APScheduler) | Triggers pipeline runs every 12 hours |
| TikTok Collector | Fetches trending data from TikTok Creative Center internal API |
| AliExpress Collector | Fetches product/supplier data via Affiliate API or Playwright fallback |
| Matcher | Links trend signals to sourceable products |
| Enricher | Adds margins, competition, shipping data |
| Scoring Engine | Computes trend score, velocity, region tags |
| PostgreSQL | Stores product cards, score history, users |
| Redis | Caches frequent API queries, rate limiting |
| FastAPI | Serves product cards with filtering/sorting/pagination |

## Data Model

### product_cards

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | Primary key |
| title | VARCHAR | Product name |
| category | VARCHAR | Product category |
| image_urls | ARRAY | Product images |
| trend_score | INTEGER | 0-100, computed |
| trend_velocity | ENUM | accelerating / stable / decelerating |
| first_seen_at | TIMESTAMP | When first detected |
| last_seen_at | TIMESTAMP | Last pipeline update |
| regions | ARRAY | Region tags (US, EU, SEA, etc.) |
| status | ENUM | trending / declining / expired |
| tiktok_data | JSONB | Creative count, advertiser count, ad duration, hashtag views, sample creatives, engagement metrics |
| supplier_data | JSONB | AliExpress listings array (url, price, shipping_cost, shipping_days, order_count, seller_rating, variants), best_price, best_margin, supplier_count |
| competition | JSONB | Estimated sellers, saturation level (low/medium/high), market entry difficulty |
| pricing | JSONB | Cost range, suggested sell price, estimated margin percent and absolute |
| created_at | TIMESTAMP | |
| updated_at | TIMESTAMP | |

JSONB fields are used for evolving data structures (source-specific data changes as we add providers). Stable fields used for filtering remain as indexed columns.

### score_history

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | |
| product_card_id | UUID | FK to product_cards |
| trend_score | INTEGER | Score at this point in time |
| recorded_at | TIMESTAMP | |

### collection_runs

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | |
| source | VARCHAR | tiktok / aliexpress |
| started_at | TIMESTAMP | |
| completed_at | TIMESTAMP | |
| status | ENUM | success / partial / failed |
| items_collected | INTEGER | |
| errors | JSONB | Error details if any |

### users

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | |
| email | VARCHAR | Unique |
| hashed_password | VARCHAR | |
| subscription_tier | ENUM | free / basic / pro / enterprise |
| region_preference | VARCHAR | Default region filter |
| created_at | TIMESTAMP | |

### api_keys

| Column | Type | Notes |
|--------|------|-------|
| id | UUID | |
| user_id | UUID | FK to users |
| key_hash | VARCHAR | Hashed API key |
| name | VARCHAR | User-given name |
| rate_limit | INTEGER | Requests per day |
| created_at | TIMESTAMP | |
| last_used_at | TIMESTAMP | |

## API Endpoints

Base: `/api/v1`

### Product Discovery

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/products` | List trending products (filtered, sorted, paginated) |
| GET | `/products/{id}` | Full product card detail |
| GET | `/products/{id}/history` | Score history for velocity visualization |

**`/products` query parameters:** region, category, status (default: trending), min_score, velocity, saturation, min_margin, sort (score/velocity/margin/first_seen/last_seen), order (asc/desc), page, limit (default: 20).

### Auth & User Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/register` | Create account |
| POST | `/auth/login` | Get JWT token |
| GET | `/auth/me` | Current user profile |
| POST | `/api-keys` | Generate API key |
| DELETE | `/api-keys/{id}` | Revoke API key |

### System

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Service health check |
| GET | `/status/pipeline` | Last collection run status |

### Subscription Tier Limits

| Feature | Free | Basic | Pro | Enterprise |
|---------|------|-------|-----|------------|
| Products per query | 5 | 20 | 50 | unlimited |
| Queries per day | 10 | 100 | 500 | unlimited |
| Score history | none | 7 days | 30 days | full |
| Supplier details | hidden | basic | full | full + API |
| Regions | 1 | 3 | all | all |
| API key access | no | no | no | yes |

### Response Format

```json
{
  "data": [...],
  "meta": { "page": 1, "limit": 20, "total": 342 },
  "status": "ok"
}
```

Error responses:
```json
{
  "status": "error",
  "error": { "code": "RATE_LIMITED", "message": "Daily query limit exceeded" }
}
```

## Scoring Engine

### Trend Score (0-100)

Weighted signals, percentile-ranked against all products in the current batch:

| Signal | Weight | Source | Measures |
|--------|--------|--------|----------|
| Advertiser count | 25% | TikTok | Distinct sellers running ads |
| Ad duration | 20% | TikTok | How long ads have been running |
| Creative volume | 15% | TikTok | Unique ad creatives |
| Engagement velocity | 15% | TikTok | Rate of hashtag views / engagement growth |
| Order volume growth | 15% | AliExpress | Acceleration in orders |
| Supplier availability | 10% | AliExpress | Number of suppliers with stock |

Formula: `raw_score = sum(normalized_signal * weight)`, then `trend_score = min(100, raw_score * calibration_factor)`. Calibration factor starts at 1.0 and is adjusted based on observed score distributions to ensure good spread across the 0-100 range.

Weights are stored in `config/scoring_weights.yml` for tuning without code changes.

### Velocity

```
velocity = (current_score - score_from_2_runs_ago) / 2
```

- `|velocity| < 3` → stable
- Positive above threshold → accelerating
- Negative below threshold → decelerating

### Status Transitions

- **trending** — score >= 30 and velocity >= -5
- **declining** — score >= 30 but velocity < -5 for 3 consecutive runs
- **expired** — score < 30 for 3 consecutive runs (hidden from default queries, kept for history)

### Competition Estimate

- **Low** — < 10 advertisers, < 20 suppliers
- **Medium** — 10-50 advertisers, 20-100 suppliers
- **High** — 50+ advertisers, 100+ suppliers

### Margin Calculation

```
suggested_sell_price = best_supplier_price * 2.5 to 3.0
estimated_margin = suggested_sell_price - (supplier_price + shipping_cost + platform_fees_5%)
```

## Data Collection Details

### TikTok Creative Center

**Method:** HTTP requests (httpx) to internal API endpoints powering the public Creative Center pages. No auth required for public browsing data. Rotating headers.

**Extracts:** Product name, category, thumbnail, advertiser count, creative samples, region breakdown, engagement metrics, ad duration.

**Risk:** Undocumented endpoints can change. Mitigation: isolated collector module, schema validation on responses, alerting on failures.

### AliExpress

**Primary method:** AliExpress Affiliate API (official, requires approval).

**Fallback:** Playwright headless browser with proxy rotation for scraping product pages.

**Extracts:** Product URL, title, images, price, variants, shipping cost/time by region, order count, seller rating, similar products.

### Matching Logic

1. Extract keywords from TikTok creative (title, hashtags, visible text)
2. Search AliExpress with those keywords
3. Match criteria: keyword Jaccard similarity > 0.6 (tokenized title words intersection / union) OR image perceptual hash Hamming distance < 10 (out of 64 bits)
4. Matched products get full product cards; unmatched flagged as "unsourceable"

### Region Tagging

TikTok provides ad targeting regions directly. AliExpress shipping data confirms practical shippability (reasonable cost and delivery time to region).

## Project Structure

```
trending-products/
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic/                    # DB migrations
│   └── versions/
├── config/
│   ├── settings.py             # App config (env-based)
│   └── scoring_weights.yml     # Tunable scoring config
├── src/
│   ├── main.py                 # FastAPI app entry
│   ├── api/
│   │   ├── routes/
│   │   │   ├── products.py
│   │   │   ├── auth.py
│   │   │   └── health.py
│   │   ├── dependencies.py     # Auth, rate limiting
│   │   └── schemas.py          # Pydantic response models
│   ├── collectors/
│   │   ├── base.py             # Abstract collector interface
│   │   ├── tiktok.py
│   │   └── aliexpress.py
│   ├── pipeline/
│   │   ├── orchestrator.py     # Runs the full pipeline
│   │   ├── matcher.py          # Links TikTok → AliExpress
│   │   ├── enricher.py         # Adds margins, competition
│   │   └── scorer.py           # Computes trend scores
│   ├── models/
│   │   ├── product_card.py     # SQLAlchemy models
│   │   ├── user.py
│   │   └── collection_run.py
│   ├── services/
│   │   ├── product_service.py  # Business logic for API
│   │   └── auth_service.py
│   └── scheduler/
│       └── jobs.py             # APScheduler job definitions
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/               # Sample API responses
└── scripts/
    └── seed_data.py            # Dev helpers
```

### Docker Compose Services

- **api** — FastAPI app (uvicorn)
- **worker** — Pipeline scheduler + jobs (same codebase, different entrypoint)
- **postgres** — PostgreSQL 16
- **redis** — Caching + rate limiting

API and worker are split so pipeline jobs don't block API responsiveness and can scale independently.

### Key Libraries

| Purpose | Library |
|---------|---------|
| API framework | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy 2.0 + Alembic |
| HTTP client | httpx (async) |
| Headless browser | Playwright |
| Scheduling | APScheduler |
| Cache / rate limit | redis-py |
| Auth | python-jose (JWT) + passlib |
| Validation | Pydantic v2 |
| Config | pydantic-settings |
| Testing | pytest + pytest-asyncio + httpx test client |

### Configuration

All config via environment variables (12-factor), `.env` file for local dev:

```
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/trending
REDIS_URL=redis://redis:6379/0
TIKTOK_BASE_URL=https://ads.tiktok.com/creative_radar_api/v1/
ALIEXPRESS_API_KEY=...
JWT_SECRET=...
PIPELINE_SCHEDULE_HOURS=12
SCORING_WEIGHTS_PATH=config/scoring_weights.yml
```

## Error Handling

### Pipeline Failures

- Each collector runs independently. TikTok failure doesn't block AliExpress (and vice versa).
- Each stage logs to `collection_runs` with status and error details.
- If both collectors fail, previous data remains — API serves stale-but-existing cards.
- Retry: 3x with exponential backoff before marking as failed.

### API Errors

Standard HTTP codes: 400 (validation), 401 (unauthorized), 403 (tier limit), 404 (not found), 429 (rate limited), 500 (internal).

### Data Quality

- Products must pass validation before becoming cards (must have title, at least one price, at least one trend signal).
- Malformed data logged and skipped.
- Low-confidence matches (below thresholds) stored separately, not surfaced to users.

## Testing Strategy

### Unit Tests

- Scoring engine: fixed inputs → expected scores/velocity/status
- Matcher: sample data → correct matches
- Enricher: margin calculations, competition classification
- API routes with mocked services

### Integration Tests

- Full pipeline run with fixture data (saved real API responses)
- API endpoints against real PostgreSQL (test container)
- Auth flow: register → login → gated endpoints → rate limiting

### Collector Tests (Fixture-Based)

- Real responses saved as JSON fixtures
- Collectors parse fixtures correctly
- When source format changes, tests break immediately (early warning)

No live API calls in CI — too flaky. Manual smoke tests against live sources during development.

## Future Phases (Out of Scope for This Spec)

- Meta Ad Library integration (next data source)
- Seasonality detection (Google Trends, historical pattern analysis)
- Frontend application
- Payment processing (Stripe integration for subscriptions)
- Notification system (email/push alerts for new trends)
- Image similarity matching (ML-based product matching)
