# Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the containerized foundation — FastAPI + PostgreSQL + React — that the rest of the stock income agent will build on. One `docker compose up` produces a healthy stack with database migrations applied, the API reachable at localhost:8000, and the React skeleton at localhost:3000.

**Architecture:** Three-container Docker Compose stack. Python 3.12 / FastAPI service uses SQLAlchemy 2.x async + Alembic migrations against PostgreSQL 16. React 18 / Vite / TypeScript frontend served by nginx in production-mode container; dev mode via Vite dev server. Configuration via `.env.local` (not committed); pydantic-settings loads it. Every step is TDD — write the failing test, watch it fail, implement, watch it pass, commit.

**Tech Stack:** Python 3.12, FastAPI 0.115+, SQLAlchemy 2.x (async), Alembic, asyncpg, pydantic-settings, pytest, pytest-asyncio, testcontainers, ruff, React 18, Vite 5, TypeScript 5, TanStack Query, Docker Compose v2, PostgreSQL 16, nginx.

---

## File Structure

This sub-project creates the project skeleton. Files created:

**Repo root**
- `README.md` — minimal project overview
- `.gitignore` — Python, Node, env, IDE
- `.env.example` — committed template with all required env vars
- `docker-compose.yml` — three services: api, web, db
- `Makefile` — common dev commands

**Backend (`backend/`)**
- `backend/Dockerfile` — multi-stage Python image
- `backend/pyproject.toml` — project metadata + deps (uv-managed)
- `backend/uv.lock` — generated lockfile
- `backend/ruff.toml` — linter config
- `backend/alembic.ini` — Alembic config
- `backend/alembic/env.py` — async-aware Alembic env
- `backend/alembic/versions/` — migrations directory (empty for now)
- `backend/app/__init__.py`
- `backend/app/main.py` — FastAPI app factory + `/health` endpoint
- `backend/app/config.py` — pydantic-settings configuration
- `backend/app/db.py` — async SQLAlchemy engine + session factory
- `backend/app/models/__init__.py` — declarative base
- `backend/app/api/__init__.py`
- `backend/app/api/health.py` — health router (db ping)
- `backend/tests/__init__.py`
- `backend/tests/conftest.py` — pytest fixtures (testcontainers Postgres)
- `backend/tests/test_config.py`
- `backend/tests/test_health.py`
- `backend/tests/test_db.py`

**Frontend (`frontend/`)**
- `frontend/Dockerfile` — multi-stage node-builder + nginx-server
- `frontend/nginx.conf` — proxies `/api/*` to the api container
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx` — single-page skeleton that calls `/api/health` and renders status
- `frontend/src/api/client.ts` — fetch wrapper
- `frontend/src/api/health.ts` — typed health endpoint
- `frontend/tests/App.test.tsx` — vitest component test
- `frontend/vitest.config.ts`

This file structure locks in the responsibilities: `config.py` owns environment loading, `db.py` owns the engine, `main.py` owns the app wiring, `api/health.py` owns the health endpoint. Adding new endpoints later adds new files in `api/` without touching `main.py` beyond router registration.

---

## Conventions

**TDD rhythm for every code task:**
1. Write the failing test
2. Run it and confirm it fails (note the failure message)
3. Implement the minimum code to make it pass
4. Run the test and confirm it passes
5. Commit

**Commit message format:** Conventional Commits — `feat:`, `chore:`, `test:`, `docs:`, `ci:`, `fix:`.

**Git identity for this repo:** already set repo-local to `theDude30 / tzahib@gmail.com` during spec phase. Do not change.

---

### Task 1: Project skeleton files

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `.env.example`
- Create: `Makefile`

- [ ] **Step 1: Create `.gitignore`**

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage
htmlcov/
backend/.venv/
backend/uv.lock-journal

# Node
node_modules/
frontend/dist/
frontend/.vite/

# Env / local
.env.local
.env.*.local
*.local

# OS / IDE
.DS_Store
.idea/
.vscode/

# Postgres data (mounted volume)
data/postgres/

# Backups
backups/
```

- [ ] **Step 2: Create `README.md`**

```markdown
# Stock Income Agent

Personal, self-hosted agent that generates monthly income from a paper-traded S&P 500 portfolio using dividends + covered calls.

See `docs/superpowers/specs/2026-05-28-stock-income-agent-design.md` for the full design.

## Local development

Copy `.env.example` to `.env.local` and fill in values. Then:

```
make up        # start all containers
make logs      # follow logs
make down      # stop everything
make test      # run all tests
```

Dashboard: http://localhost:3000
API: http://localhost:8000
Health: http://localhost:8000/health
```

- [ ] **Step 3: Create `.env.example`**

```
# Postgres
POSTGRES_USER=stockagent
POSTGRES_PASSWORD=changeme
POSTGRES_DB=stockagent
POSTGRES_HOST=db
POSTGRES_PORT=5432

# Backend
APP_ENV=development
LOG_LEVEL=INFO

# Anthropic (used in later sub-projects; placeholder okay for now)
ANTHROPIC_API_KEY=
```

- [ ] **Step 4: Create `Makefile`**

```makefile
.PHONY: up down logs build test test-backend test-frontend lint migrate shell-api shell-db

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

test: test-backend test-frontend

test-backend:
	docker compose run --rm api pytest

test-frontend:
	docker compose run --rm web npm test -- --run

lint:
	docker compose run --rm api ruff check .
	docker compose run --rm web npm run lint

migrate:
	docker compose run --rm api alembic upgrade head

shell-api:
	docker compose exec api bash

shell-db:
	docker compose exec db psql -U $${POSTGRES_USER} -d $${POSTGRES_DB}
```

- [ ] **Step 5: Commit**

```bash
git add .gitignore README.md .env.example Makefile
git commit -m "chore: project skeleton (gitignore, readme, env example, makefile)"
```

---

### Task 2: Backend project setup with pyproject.toml

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/ruff.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/tests/__init__.py`

- [ ] **Step 1: Create `backend/pyproject.toml`**

```toml
[project]
name = "stock-income-agent"
version = "0.1.0"
description = "Self-hosted dividend + covered-call income agent for S&P 500"
requires-python = ">=3.12,<3.13"
dependencies = [
    "fastapi>=0.115,<0.116",
    "uvicorn[standard]>=0.32,<0.33",
    "sqlalchemy[asyncio]>=2.0.36,<2.1",
    "asyncpg>=0.30,<0.31",
    "alembic>=1.14,<1.15",
    "pydantic>=2.9,<3.0",
    "pydantic-settings>=2.6,<3.0",
    "httpx>=0.27,<0.28",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.24,<0.25",
    "pytest-cov>=6.0,<7.0",
    "testcontainers[postgresql]>=4.8,<5.0",
    "ruff>=0.7,<0.8",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
filterwarnings = [
    "error",
    "ignore::DeprecationWarning:pydantic",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]
```

- [ ] **Step 2: Create `backend/ruff.toml`**

```toml
line-length = 100
target-version = "py312"

[lint]
select = ["E", "F", "I", "B", "UP", "N", "RUF"]
ignore = ["E501"]

[lint.per-file-ignores]
"tests/**" = ["B011"]
```

- [ ] **Step 3: Create empty `backend/app/__init__.py` and `backend/tests/__init__.py`**

Both files are empty (zero bytes).

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/ruff.toml backend/app/__init__.py backend/tests/__init__.py
git commit -m "chore(backend): project setup (pyproject, ruff config, package init)"
```

---

### Task 3: Configuration module (test-first)

**Files:**
- Test: `backend/tests/test_config.py`
- Create: `backend/app/config.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_config.py`:

```python
import pytest


def test_settings_loads_postgres_url_from_components(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")
    monkeypatch.setenv("APP_ENV", "test")

    s = Settings()
    assert s.postgres_url == "postgresql+asyncpg://u:p@h:5432/d"
    assert s.app_env == "test"


def test_settings_requires_postgres_password(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("APP_ENV", "test")

    with pytest.raises(Exception):
        Settings()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.config'`.

- [ ] **Step 3: Write minimal implementation**

`backend/app/config.py`:

```python
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    postgres_user: str = Field(...)
    postgres_password: str = Field(...)
    postgres_db: str = Field(...)
    postgres_host: str = Field(...)
    postgres_port: int = Field(...)

    app_env: str = Field(default="development")
    log_level: str = Field(default="INFO")
    anthropic_api_key: str = Field(default="")

    @property
    def postgres_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_config.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/config.py backend/tests/test_config.py
git commit -m "feat(backend): pydantic settings module with postgres url builder"
```

---

### Task 4: Database engine and session factory (test-first, with testcontainers)

**Files:**
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_db.py`
- Create: `backend/app/db.py`
- Create: `backend/app/models/__init__.py`

- [ ] **Step 1: Write `backend/tests/conftest.py`**

```python
import asyncio
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def pg_container():
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest_asyncio.fixture(scope="session")
async def engine(pg_container) -> AsyncGenerator[AsyncEngine, None]:
    url = pg_container.get_connection_url().replace("psycopg2", "asyncpg")
    eng = create_async_engine(url, echo=False, future=True)
    try:
        yield eng
    finally:
        await eng.dispose()


@pytest_asyncio.fixture()
async def session(engine) -> AsyncGenerator[AsyncSession, None]:
    factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
```

- [ ] **Step 2: Write the failing test**

`backend/tests/test_db.py`:

```python
import pytest
from sqlalchemy import text


@pytest.mark.asyncio
async def test_engine_can_execute_select_one(session):
    result = await session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1


@pytest.mark.asyncio
async def test_app_db_module_provides_get_session(monkeypatch, pg_container):
    url = pg_container.get_connection_url().replace("psycopg2", "asyncpg")
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.db import get_engine, get_session_factory

    eng = get_engine()
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
    await eng.dispose()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_db.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 4: Write minimal implementation**

`backend/app/models/__init__.py`:

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
```

`backend/app/db.py`:

```python
from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.config import get_settings


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    settings = get_settings()
    return create_async_engine(settings.postgres_url, echo=False, future=True)


@lru_cache(maxsize=1)
def get_session_factory() -> sessionmaker:
    return sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        yield session
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_db.py -v
```

Expected: both tests pass. (First run pulls the postgres image; allow 1–2 min.)

- [ ] **Step 6: Commit**

```bash
git add backend/tests/conftest.py backend/tests/test_db.py backend/app/db.py backend/app/models/__init__.py
git commit -m "feat(backend): async sqlalchemy engine, session factory, declarative base"
```

---

### Task 5: Alembic migrations setup

**Files:**
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/.gitkeep`
- Test: extend `backend/tests/test_db.py`

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_db.py`)

```python
@pytest.mark.asyncio
async def test_alembic_can_upgrade_head(monkeypatch, pg_container):
    import subprocess
    import os

    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env={**os.environ},
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, f"alembic failed: {result.stderr}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_db.py::test_alembic_can_upgrade_head -v
```

Expected: `alembic: command not found` or `Path doesn't exist`.

- [ ] **Step 3: Create `backend/alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = driver://user:pass@localhost/dbname

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

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
datefmt = %H:%M:%S
```

- [ ] **Step 4: Create `backend/alembic/env.py`**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    settings = get_settings()
    context.configure(
        url=settings.postgres_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    settings = get_settings()
    connectable = create_async_engine(settings.postgres_url, future=True)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 5: Create `backend/alembic/script.py.mako`**

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 6: Create `backend/alembic/versions/.gitkeep`** (empty file)

- [ ] **Step 7: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_db.py::test_alembic_can_upgrade_head -v
```

Expected: PASS. Alembic upgrades to head (currently no-op, no migrations yet).

- [ ] **Step 8: Commit**

```bash
git add backend/alembic.ini backend/alembic/ backend/tests/test_db.py
git commit -m "feat(backend): alembic async migrations infrastructure"
```

---

### Task 6: FastAPI app with /health endpoint (test-first)

**Files:**
- Test: `backend/tests/test_health.py`
- Create: `backend/app/api/__init__.py`
- Create: `backend/app/api/health.py`
- Create: `backend/app/main.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_health.py`:

```python
import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200_and_status_ok(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    # Re-import after env set so settings cache picks it up.
    import importlib

    from app import config as config_mod
    from app import db as db_mod

    importlib.reload(config_mod)
    importlib.reload(db_mod)

    from app.main import create_app

    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "ok"


@pytest.mark.asyncio
async def test_health_reports_db_down_when_db_unreachable(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "1")  # nothing on port 1

    import importlib

    from app import config as config_mod
    from app import db as db_mod

    importlib.reload(config_mod)
    importlib.reload(db_mod)

    from app.main import create_app

    app = create_app()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")

    assert resp.status_code == 503
    body = resp.json()
    assert body["database"] == "down"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.api'`.

- [ ] **Step 3: Create `backend/app/api/__init__.py`** (empty file)

- [ ] **Step 4: Create `backend/app/api/health.py`**

```python
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.db import get_session_factory

router = APIRouter()


@router.get("/health")
async def health(response: Response) -> dict:
    factory = get_session_factory()
    db_status = "ok"
    try:
        async with factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        db_status = "down"

    if db_status != "ok":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if db_status == "ok" else "degraded", "database": db_status}
```

- [ ] **Step 5: Create `backend/app/main.py`**

```python
from fastapi import FastAPI

from app.api.health import router as health_router


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Income Agent", version="0.1.0")
    app.include_router(health_router)
    return app


app = create_app()
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd backend && uv run pytest tests/test_health.py -v
```

Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/ backend/app/main.py backend/tests/test_health.py
git commit -m "feat(backend): fastapi app factory and /health endpoint with db ping"
```

---

### Task 7: Backend Dockerfile

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

- [ ] **Step 1: Create `backend/.dockerignore`**

```
__pycache__
.pytest_cache
.ruff_cache
.venv
*.pyc
.coverage
htmlcov
tests/
.env
.env.local
```

- [ ] **Step 2: Create `backend/Dockerfile`**

```dockerfile
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv==0.5.4

COPY pyproject.toml ./
RUN uv pip install --system --no-cache -e ".[dev]"

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Build the image to verify it works**

```bash
cd backend && docker build -t stock-income-agent-backend:dev .
```

Expected: image builds successfully without errors.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "chore(backend): dockerfile with python 3.12 + uv"
```

---

### Task 8: Frontend project setup (package.json, tsconfig, vite)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/index.html`

- [ ] **Step 1: Create `frontend/package.json`**

```json
{
  "name": "stock-income-agent-web",
  "version": "0.1.0",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "lint": "eslint . --ext ts,tsx",
    "test": "vitest"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "@tanstack/react-query": "^5.59.20"
  },
  "devDependencies": {
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "@vitejs/plugin-react": "^4.3.3",
    "jsdom": "^25.0.1",
    "msw": "^2.6.4",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "vitest": "^2.1.4"
  }
}
```

- [ ] **Step 2: Create `frontend/tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3: Create `frontend/tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 4: Create `frontend/vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 3000,
    proxy: {
      "/api": {
        target: "http://api:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
```

- [ ] **Step 5: Create `frontend/vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.ts"],
  },
});
```

- [ ] **Step 6: Create `frontend/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Stock Income Agent</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/tsconfig.json frontend/tsconfig.node.json frontend/vite.config.ts frontend/vitest.config.ts frontend/index.html
git commit -m "chore(frontend): vite + react + typescript + vitest scaffold"
```

---

### Task 9: Frontend API client and health module (test-first)

**Files:**
- Create: `frontend/tests/setup.ts`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/api/health.ts`
- Test: `frontend/tests/api/health.test.ts`

- [ ] **Step 1: Create `frontend/tests/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 2: Write the failing test**

`frontend/tests/api/health.test.ts`:

```ts
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

describe("api/health", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed health response when api returns 200", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", database: "ok" }),
    });

    const { fetchHealth } = await import("../../src/api/health");
    const result = await fetchHealth();
    expect(result).toEqual({ status: "ok", database: "ok" });
  });

  it("throws when api returns non-2xx", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ status: "degraded", database: "down" }),
    });

    const { fetchHealth } = await import("../../src/api/health");
    await expect(fetchHealth()).rejects.toThrow(/503/);
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd frontend && npm install && npm test -- --run
```

Expected: `Failed to resolve import "../../src/api/health"`.

- [ ] **Step 4: Create `frontend/src/api/client.ts`**

```ts
export async function apiGet<T>(path: string): Promise<T> {
  const response = await fetch(`/api${path}`);
  if (!response.ok) {
    throw new Error(`API ${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}
```

- [ ] **Step 5: Create `frontend/src/api/health.ts`**

```ts
import { apiGet } from "./client";

export type HealthResponse = {
  status: "ok" | "degraded";
  database: "ok" | "down";
};

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}
```

- [ ] **Step 6: Run test to verify it passes**

```bash
cd frontend && npm test -- --run
```

Expected: both tests pass.

- [ ] **Step 7: Commit**

```bash
git add frontend/tests/setup.ts frontend/src/api/ frontend/tests/api/
git commit -m "feat(frontend): typed api client and health endpoint module"
```

---

### Task 10: App component (test-first)

**Files:**
- Test: `frontend/tests/App.test.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/main.tsx`

- [ ] **Step 1: Write the failing test**

`frontend/tests/App.test.tsx`:

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "../src/App";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders title and healthy status", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", database: "ok" }),
    });

    renderWithClient(<App />);

    expect(screen.getByRole("heading", { name: /stock income agent/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/api: ok/i)).toBeInTheDocument();
      expect(screen.getByText(/database: ok/i)).toBeInTheDocument();
    });
  });

  it("renders error state when health fetch fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("boom"));

    renderWithClient(<App />);

    await waitFor(() => {
      expect(screen.getByText(/unreachable/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd frontend && npm test -- --run tests/App.test.tsx
```

Expected: `Failed to resolve import "../src/App"`.

- [ ] **Step 3: Create `frontend/src/App.tsx`**

```tsx
import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "./api/health";

export default function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Stock Income Agent</h1>
      {isLoading && <p>Checking health...</p>}
      {isError && <p>API unreachable.</p>}
      {data && (
        <ul>
          <li>API: {data.status}</li>
          <li>Database: {data.database}</li>
        </ul>
      )}
    </main>
  );
}
```

- [ ] **Step 4: Create `frontend/src/main.tsx`**

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd frontend && npm test -- --run tests/App.test.tsx
```

Expected: both tests pass.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx frontend/src/main.tsx frontend/tests/App.test.tsx
git commit -m "feat(frontend): app skeleton with health check and react-query"
```

---

### Task 11: Frontend Dockerfile and nginx config

**Files:**
- Create: `frontend/nginx.conf`
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`

- [ ] **Step 1: Create `frontend/.dockerignore`**

```
node_modules
dist
.vite
tests
*.log
.DS_Store
```

- [ ] **Step 2: Create `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_http_version 1.1;
    }

    location / {
        try_files $uri /index.html;
    }
}
```

- [ ] **Step 3: Create `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS server

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
```

- [ ] **Step 4: Build the image to verify**

```bash
cd frontend && docker build -t stock-income-agent-frontend:dev .
```

Expected: builds successfully (may take 2–4 min on first run).

- [ ] **Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/nginx.conf frontend/.dockerignore
git commit -m "chore(frontend): dockerfile (node builder + nginx server) and proxy config"
```

---

### Task 12: Docker Compose orchestration

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

  api:
    build: ./backend
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_HOST: db
      POSTGRES_PORT: 5432
      APP_ENV: ${APP_ENV}
      LOG_LEVEL: ${LOG_LEVEL}
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    ports:
      - "8000:8000"
    volumes:
      - ./backend:/app
    depends_on:
      db:
        condition: service_healthy
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

  web:
    build: ./frontend
    ports:
      - "3000:80"
    depends_on:
      - api

networks:
  default:
    name: stock-income-agent
```

- [ ] **Step 2: Create `.env.local` for local dev**

```bash
cp .env.example .env.local
```

Edit `.env.local` and set `POSTGRES_PASSWORD` to something other than `changeme`.

Note: this file is gitignored. Do not commit.

- [ ] **Step 3: Start the stack**

```bash
docker compose --env-file .env.local up -d --build
```

- [ ] **Step 4: Verify all services are healthy**

```bash
docker compose ps
```

Expected: `db` shows `healthy`, `api` and `web` show `running`.

- [ ] **Step 5: Verify /health responds**

```bash
curl -s http://localhost:8000/health
```

Expected: `{"status":"ok","database":"ok"}`.

- [ ] **Step 6: Verify frontend loads**

```bash
curl -s http://localhost:3000 | grep -i "stock income agent"
```

Expected: the HTML contains the title (loaded from React after JS bootstraps; or open http://localhost:3000 in a browser to visually confirm the page shows "API: ok" and "Database: ok").

- [ ] **Step 7: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: docker compose orchestration for api, web, db"
```

---

### Task 13: GitHub Actions CI (lint + test)

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:

jobs:
  backend:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: stockagent
          POSTGRES_PASSWORD: ci_password
          POSTGRES_DB: stockagent
        ports: ["5432:5432"]
        options: >-
          --health-cmd "pg_isready -U stockagent"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install uv
        run: pip install uv==0.5.4
      - name: Install backend deps
        working-directory: backend
        run: uv pip install --system -e ".[dev]"
      - name: Lint
        working-directory: backend
        run: ruff check .
      - name: Test
        working-directory: backend
        env:
          POSTGRES_USER: stockagent
          POSTGRES_PASSWORD: ci_password
          POSTGRES_DB: stockagent
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          APP_ENV: test
        run: pytest -v

  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Install frontend deps
        working-directory: frontend
        run: npm install
      - name: Build
        working-directory: frontend
        run: npm run build
      - name: Test
        working-directory: frontend
        run: npm test -- --run
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: lint + test for backend and frontend"
```

---

### Task 14: Smoke verification documentation

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Replace `README.md` contents**

```markdown
# Stock Income Agent

Personal, self-hosted agent that generates monthly income from a paper-traded S&P 500 portfolio using dividends + covered calls.

See `docs/superpowers/specs/2026-05-28-stock-income-agent-design.md` for the full design.

## Stack

- **Backend:** Python 3.12 / FastAPI / SQLAlchemy 2.x async / Alembic
- **Frontend:** React 18 / Vite / TypeScript / TanStack Query
- **Database:** PostgreSQL 16
- **Orchestration:** Docker Compose

## Local development

```bash
cp .env.example .env.local
# Edit .env.local; set POSTGRES_PASSWORD to something other than `changeme`.

make up         # build + start all containers
make logs       # follow logs
```

Then visit:
- Dashboard: http://localhost:3000
- API:       http://localhost:8000
- Health:    http://localhost:8000/health

## Common commands

```bash
make up                  # start
make down                # stop
make test                # run all tests (backend + frontend)
make test-backend        # backend only
make test-frontend       # frontend only
make lint                # ruff + eslint
make migrate             # apply alembic migrations
make shell-api           # bash inside api container
make shell-db            # psql inside db container
```

## Project structure

```
backend/
  app/             # FastAPI application
    api/           # HTTP endpoints
    models/        # SQLAlchemy models
    config.py      # pydantic-settings config
    db.py          # async engine + sessions
    main.py        # app factory
  alembic/         # database migrations
  tests/           # pytest suite
frontend/
  src/
    api/           # API client modules
    App.tsx
    main.tsx
  tests/           # vitest suite
docs/
  superpowers/
    specs/         # design specs
    plans/         # implementation plans
docker-compose.yml
Makefile
```
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: expand readme with stack, commands, structure"
```

---

### Task 15: End-to-end manual verification

This is a manual checklist, no code changes. The agent should perform it and report results.

- [ ] **Step 1: Clean state**

```bash
docker compose down -v
rm -rf data/postgres
```

- [ ] **Step 2: Fresh build and up**

```bash
docker compose --env-file .env.local up -d --build
```

Expected: all three containers start; `docker compose ps` shows them running and `db` healthy.

- [ ] **Step 3: Wait for api to apply migrations and start**

```bash
docker compose logs api | grep -i "uvicorn running"
```

Expected: log line `Uvicorn running on http://0.0.0.0:8000`.

- [ ] **Step 4: Hit /health from host**

```bash
curl -s -w "\n%{http_code}\n" http://localhost:8000/health
```

Expected: body `{"status":"ok","database":"ok"}` and status `200`.

- [ ] **Step 5: Open browser**

Visit `http://localhost:3000`. Expected: page shows "Stock Income Agent" heading, "API: ok", "Database: ok".

- [ ] **Step 6: Verify db ping fails gracefully**

```bash
docker compose stop db
sleep 2
curl -s -w "\n%{http_code}\n" http://localhost:8000/health
docker compose start db
```

Expected: while db is stopped, `/health` returns `{"status":"degraded","database":"down"}` with status `503`.

- [ ] **Step 7: Verify tests still pass against fresh build**

```bash
make test
```

Expected: backend + frontend test suites both pass.

- [ ] **Step 8: Final commit (if any cleanup needed)**

If everything passed, no commit needed. If you fixed anything along the way, commit it now.

---

## Self-review checklist

Run this after completing all tasks:

- All 15 tasks have ✅ on every step
- `docker compose ps` shows `db` (healthy), `api` (running), `web` (running)
- `curl http://localhost:8000/health` returns 200 with `{"status":"ok","database":"ok"}`
- `http://localhost:3000` renders the skeleton with healthy API + DB indicators
- `make test` passes both suites
- `make lint` passes
- `git log --oneline` shows ~15 atomic commits, each conventional-style
- No `.env.local` committed (verify with `git ls-files | grep env`)

When all of the above are green, Sub-project 1 is complete and you're ready to start Sub-project 2 (Data Ingestion).
