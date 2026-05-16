# Railway Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the trending products backend to Railway with a public URL.

**Architecture:** Push to GitHub, Railway auto-deploys API + Worker services from Dockerfile targets, with managed PostgreSQL and Redis add-ons.

**Tech Stack:** Railway, GitHub, Docker, existing FastAPI stack

---

### Task 1: Add async_database_url Property

**Files:**
- Modify: `config/settings.py`
- Modify: `src/database.py`
- Modify: `alembic/env.py`

- [ ] **Step 1: Add the computed property to settings**

Replace `config/settings.py` with:
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

    @property
    def async_database_url(self) -> str:
        """Convert postgresql:// to postgresql+asyncpg:// for SQLAlchemy async driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
```

- [ ] **Step 2: Update database.py to use the new property**

Replace `src/database.py` with:
```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config.settings import settings

engine = create_async_engine(settings.async_database_url, echo=False)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
```

- [ ] **Step 3: Update alembic/env.py to use the new property**

Change line 15 and line 37 in `alembic/env.py`:

Replace:
```python
config.set_main_option("sqlalchemy.url", settings.database_url)
```
With:
```python
config.set_main_option("sqlalchemy.url", settings.async_database_url)
```

Replace:
```python
    connectable = create_async_engine(settings.database_url)
```
With:
```python
    connectable = create_async_engine(settings.async_database_url)
```

- [ ] **Step 4: Verify everything still works locally**

Run: `pytest tests/unit/ -v`

Expected: All 46 tests pass (no DB connection needed for unit tests)

Run: `alembic upgrade head`

Expected: `INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.` (no errors)

- [ ] **Step 5: Commit**

```bash
git add config/settings.py src/database.py alembic/env.py
git commit -m "feat: async_database_url property for Railway compatibility"
```

---

### Task 2: Prepare Repository for GitHub

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: Ensure .gitignore covers deployment artifacts**

Replace `.gitignore` with:
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
.claude/
```

- [ ] **Step 2: Verify no secrets are tracked**

Run: `git status`

Confirm `.env` is NOT tracked (it should already be in .gitignore).

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: update gitignore for deployment"
```

---

### Task 3: Create GitHub Repository and Push

- [ ] **Step 1: Create the repo on GitHub**

Run:
```bash
gh repo create trending-products --public --source=. --remote=origin --push
```

This creates the repo, sets it as the `origin` remote, and pushes all commits.

If `gh` CLI is not installed, do it manually:
1. Go to https://github.com/new
2. Name: `trending-products`, Public, no README
3. Then run:
```bash
git remote add origin https://github.com/<YOUR_USERNAME>/trending-products.git
git push -u origin master
```

- [ ] **Step 2: Verify on GitHub**

Open `https://github.com/<YOUR_USERNAME>/trending-products` in a browser.

Expected: All project files visible, latest commit message matches.

---

### Task 4: Railway Setup

This task is manual (Railway dashboard + CLI). Follow these steps exactly.

- [ ] **Step 1: Sign up for Railway**

1. Go to https://railway.app
2. Click "Login" → "Login with GitHub"
3. Authorize Railway to access your GitHub account
4. You'll get $5 in trial credits automatically

- [ ] **Step 2: Install Railway CLI**

Run:
```bash
npm install -g @railway/cli
```

Or on Windows with PowerShell:
```bash
powershell -Command "iwr https://raw.githubusercontent.com/railwayapp/cli/master/install.ps1 -useb | iex"
```

Then authenticate:
```bash
railway login
```

- [ ] **Step 3: Create Railway project**

1. In Railway dashboard: click "New Project"
2. Select "Deploy from GitHub repo"
3. Choose your `trending-products` repository
4. Railway will create a service — this becomes the API service

- [ ] **Step 4: Add PostgreSQL**

1. In the project canvas, click "New" → "Database" → "Add PostgreSQL"
2. Railway provisions a PostgreSQL instance and makes `DATABASE_URL` available as a variable

- [ ] **Step 5: Add Redis**

1. In the project canvas, click "New" → "Database" → "Add Redis"
2. Railway provisions Redis and makes `REDIS_URL` available as a variable

- [ ] **Step 6: Configure the API service**

1. Click on the service that was created from your repo
2. Go to "Settings" tab:
   - Under "Build", set Docker build target: `api`
   - Under "Networking", click "Generate Domain" to get a public URL
3. Go to "Variables" tab:
   - Click "Add Reference Variable" → select `DATABASE_URL` from the PostgreSQL service
   - Click "Add Reference Variable" → select `REDIS_URL` from the Redis service
   - Add these manually:
     ```
     JWT_SECRET=<click "Generate" or type a random 32-char string>
     PIPELINE_SCHEDULE_HOURS=12
     SCORING_WEIGHTS_PATH=config/scoring_weights.yml
     TIKTOK_BASE_URL=https://ads.tiktok.com/creative_radar_api/v1/
     ALIEXPRESS_API_KEY=placeholder
     PORT=8000
     ```

- [ ] **Step 7: Create the Worker service**

1. In the project canvas, click "New" → "GitHub Repo" → select `trending-products` again
2. This creates a second service from the same repo
3. Rename it to "Worker" (click the service name)
4. Go to "Settings" tab:
   - Under "Build", set Docker build target: `worker`
   - Under "Networking", do NOT generate a domain (worker has no HTTP traffic)
5. Go to "Variables" tab:
   - Add the same reference variables (DATABASE_URL, REDIS_URL)
   - Add the same manual variables as the API service

- [ ] **Step 8: Deploy**

Railway auto-deploys when you push to GitHub. If the services aren't deploying yet:
1. Click on each service → "Deploy" tab → "Deploy Now"

Wait for both services to show "Active" status (green).

---

### Task 5: Run Migrations and Seed

- [ ] **Step 1: Link Railway CLI to project**

Run:
```bash
railway link
```

Select your project and the API service when prompted.

- [ ] **Step 2: Run database migrations**

Run:
```bash
railway run alembic upgrade head
```

Expected:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Running upgrade -> d724a768d536, initial schema
```

- [ ] **Step 3: Seed sample data**

Run:
```bash
railway run python -m scripts.seed_data
```

Expected: `Seeded 3 product cards with score history`

---

### Task 6: Verify Live Deployment

- [ ] **Step 1: Test health endpoint**

Get your public URL from Railway dashboard (looks like `https://trending-products-production-xxxx.up.railway.app`).

Run:
```bash
curl https://<YOUR_RAILWAY_URL>/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: Test registration**

```bash
curl -X POST https://<YOUR_RAILWAY_URL>/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"live@test.com","password":"testpass123"}'
```

Expected: 201 response with user data.

- [ ] **Step 3: Test login and product listing**

```bash
TOKEN=$(curl -s -X POST https://<YOUR_RAILWAY_URL>/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"live@test.com","password":"testpass123"}' | python -c "import sys,json; print(json.load(sys.stdin)['data']['access_token'])")

curl -s https://<YOUR_RAILWAY_URL>/api/v1/products \
  -H "Authorization: Bearer $TOKEN" | python -m json.tool
```

Expected: 200 response with seeded product data.

- [ ] **Step 4: Add Railway URL to api.http for REST Client testing**

Add to the top of `api.http`:
```
@host = https://<YOUR_RAILWAY_URL>

### Health Check (Railway)
GET {{host}}/health

###
```

- [ ] **Step 5: Commit api.http update**

```bash
git add api.http
git commit -m "docs: add Railway URL to api.http"
git push
```
