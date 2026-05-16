# Railway Deployment — Design Spec

## Overview

Deploy the trending products backend to Railway for live testing. Full stack: API, Worker, PostgreSQL, Redis — accessible via public URL.

## Decisions

- **Provider:** Railway (fastest path to live, managed Postgres/Redis, GitHub deploy)
- **Repo:** Public GitHub repository
- **Services:** 4 (API, Worker, Postgres, Redis)
- **Migrations:** Run via one-off Railway command after deploy
- **Cost:** ~$5 trial credit covers initial testing

## Architecture on Railway

```
GitHub Repo (push) → Railway Project
                        ├── PostgreSQL (managed add-on)
                        ├── Redis (managed add-on)
                        ├── API service (Dockerfile target: api, port 8000)
                        └── Worker service (Dockerfile target: worker)
```

Railway injects `DATABASE_URL` and `REDIS_URL` as environment variables into each service automatically when you reference the add-on.

## Codebase Changes

### 1. Dockerfile adjustment

The existing multi-stage Dockerfile works as-is. Railway builds each service by specifying the target stage. No changes needed.

### 2. Railway configuration

No `railway.toml` needed — configure via dashboard (simpler for a first deploy). Settings per service:

**API service:**
- Build: Dockerfile, target `api`
- Port: 8000 (Railway auto-detects from `CMD`)
- Health check: `GET /health`
- Public networking: enabled (generates public URL)

**Worker service:**
- Build: Dockerfile, target `worker`
- No port (background process, no inbound traffic)
- Public networking: disabled

### 3. Environment variables

Railway provides `DATABASE_URL` and `REDIS_URL` from the managed add-ons. Additional variables to set manually on both API and Worker:

```
JWT_SECRET=<generate a secure random string>
PIPELINE_SCHEDULE_HOURS=12
SCORING_WEIGHTS_PATH=config/scoring_weights.yml
TIKTOK_BASE_URL=https://ads.tiktok.com/creative_radar_api/v1/
ALIEXPRESS_API_KEY=<placeholder>
```

### 4. Database migrations

Run as a one-off command via Railway CLI after first deploy:
```
railway run alembic upgrade head
```

Or use Railway's "Run Command" feature in the dashboard.

### 5. Seed data (optional)

```
railway run python -m scripts.seed_data
```

## Deployment Steps

1. Create GitHub repo `trending-products` (public)
2. Push existing code
3. Sign up at railway.app (GitHub OAuth)
4. Create new project from the GitHub repo
5. Add PostgreSQL and Redis add-ons
6. Create API service (set Dockerfile target, enable public URL)
7. Create Worker service (set Dockerfile target)
8. Configure shared environment variables
9. Deploy (automatic on push)
10. Run migrations via Railway CLI or dashboard
11. Verify: hit public URL `/health`, register user, list products

## Known Constraints

- **Trial credit:** $5 lasts ~2-4 weeks with minimal traffic. After that, pay-as-you-go.
- **Sleep:** Railway does not sleep free-tier services (unlike Render), so the API stays responsive.
- **DATABASE_URL format:** Railway provides a standard `postgresql://` URL. Our app expects `postgresql+asyncpg://`. We'll need to handle this — either transform it in settings.py or set the variable manually with the `+asyncpg` driver prefix.

## DATABASE_URL Driver Prefix

Railway provides: `postgresql://user:pass@host:port/db`
Our app needs: `postgresql+asyncpg://user:pass@host:port/db`

**Decision:** Handle in code so Railway's auto-injected URL works without manual editing.

Add a computed property to `config/settings.py`:
```python
@property
def async_database_url(self) -> str:
    url = self.database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url
```

Update consumers to use `settings.async_database_url`:
- `src/database.py` — engine creation
- `alembic/env.py` — migration connection
