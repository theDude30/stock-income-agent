# Data Ingestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Step 1 of the daily pipeline — populate `stocks`, `prices`, `dividend_history`, `options_chains`, `news_items`, and `pipeline_runs` from yfinance, Wikipedia, and Yahoo Finance RSS. Add an APScheduler weekday-17:15-ET cron and a `POST /pipeline/run` HTTP trigger.

**Architecture:** Five protocol-based source classes (`UniverseSource`, `PriceSource`, `DividendSource`, `OptionsSource`, `NewsSource`) decouple steps from upstream APIs. Production implementations wrap yfinance / `pandas.read_html` / `feedparser`; test doubles return canned data. Five step modules (`universe`, `prices`, `dividends`, `options`, `news`) each define `async def run(ctx) -> StepResult` and use a shared per-ticker concurrency pattern (`asyncio.Semaphore(10)` + `asyncio.to_thread`). An orchestrator records every run in `pipeline_runs`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x async + Alembic, yfinance, feedparser, pandas, APScheduler 3.x, FastAPI BackgroundTasks, pytest + pytest-asyncio, testcontainers Postgres.

**Pre-flight:** Foundation sub-project must be complete. `backend/.venv` exists with `uv pip install -e ".[dev]"` already run. Postgres reachable for tests via testcontainers.

---

## File Structure

**Backend (`backend/`)**

**New dependencies (pyproject.toml):**
- `yfinance>=0.2.50,<0.3` (production)
- `feedparser>=6.0.11,<7.0` (production)
- `pandas>=2.2,<3.0` (production — needed for `pandas.read_html` + yfinance DataFrames)
- `lxml>=5.3,<6.0` (production — pandas.read_html parser)
- `apscheduler>=3.10,<4.0` (production — 3.x has the asyncio scheduler we need)
- `freezegun>=1.5,<2.0` (dev — for time-based tests)

**New source files:**
- `backend/app/sources/__init__.py`
- `backend/app/sources/base.py` — Protocol classes + DTO dataclasses
- `backend/app/sources/fakes.py` — InMemory test doubles
- `backend/app/sources/yfinance_source.py` — production prices/dividends/options
- `backend/app/sources/wikipedia_source.py` — production S&P 500 universe scraper
- `backend/app/sources/yahoo_rss_source.py` — production RSS news

**New model files:**
- `backend/app/models/stocks.py` — `Stock`, `Price`, `DividendHistory`
- `backend/app/models/options.py` — `OptionsChainRow`
- `backend/app/models/news.py` — `NewsItem`
- `backend/app/models/pipeline.py` — `PipelineRun`

**New pipeline files:**
- `backend/app/pipeline/__init__.py`
- `backend/app/pipeline/repo.py` — `PipelineRepo` (DB writes + reads for steps)
- `backend/app/pipeline/runner.py` — `run_pipeline()`, `StepContext`, `StepResult`, `StepFailure`
- `backend/app/pipeline/scheduler.py` — APScheduler lifespan integration
- `backend/app/pipeline/cli.py` — `python -m app.pipeline {run|backfill|step}`
- `backend/app/pipeline/__main__.py` — entrypoint that calls cli.main()
- `backend/app/pipeline/steps/__init__.py` — exports `DEFAULT_STEPS`, `Step` base
- `backend/app/pipeline/steps/base.py` — `Step` ABC
- `backend/app/pipeline/steps/universe.py`
- `backend/app/pipeline/steps/prices.py`
- `backend/app/pipeline/steps/dividends.py`
- `backend/app/pipeline/steps/options.py`
- `backend/app/pipeline/steps/news.py`

**New API file:**
- `backend/app/api/pipeline.py` — `GET /pipeline/runs`, `GET /pipeline/runs/{id}`, `POST /pipeline/run`

**Modified files:**
- `backend/pyproject.toml` — new deps
- `backend/app/main.py` — register `pipeline` router, wire lifespan for scheduler
- `backend/app/db.py` — no changes; existing engine/session is reused
- `backend/app/models/__init__.py` — no behavioral changes; new models import `Base` from here

**New Alembic migration:**
- `backend/alembic/versions/0001_ingestion_tables.py` — single migration creating all six tables

**New tests:**
- `backend/tests/test_migration_ingestion.py`
- `backend/tests/sources/__init__.py`
- `backend/tests/sources/test_fakes.py`
- `backend/tests/pipeline/__init__.py`
- `backend/tests/pipeline/test_repo.py`
- `backend/tests/pipeline/test_runner.py`
- `backend/tests/pipeline/test_step_universe.py`
- `backend/tests/pipeline/test_step_prices.py`
- `backend/tests/pipeline/test_step_dividends.py`
- `backend/tests/pipeline/test_step_options.py`
- `backend/tests/pipeline/test_step_news.py`
- `backend/tests/pipeline/test_scheduler.py`
- `backend/tests/test_pipeline_api.py`
- `backend/tests/test_yfinance_integration.py` — `@pytest.mark.slow`, skipped by default

This split keeps every file focused: one source per provider, one step per pipeline phase, one model file per domain group, one test file per unit.

---

## Conventions

**TDD rhythm for every task:**
1. Write the failing test
2. Run it and confirm it fails (note the failure message)
3. Implement the minimum code to make it pass
4. Run the test and confirm it passes
5. Commit

**All shell commands run from `backend/` unless otherwise noted.** All pytest invocations use `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest ...`.

**Commit message format:** Conventional Commits — `feat:`, `chore:`, `test:`, `docs:`, `fix:`.

**Imports follow existing pattern:** stdlib → third-party (blank line) → `app.*`. ruff handles sorting.

---

### Task 1: Add new dependencies

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Update `backend/pyproject.toml`** — replace the `dependencies` and `optional-dependencies` blocks

```toml
dependencies = [
    "fastapi>=0.115,<0.116",
    "uvicorn[standard]>=0.32,<0.33",
    "sqlalchemy[asyncio]>=2.0.36,<2.1",
    "asyncpg>=0.30,<0.31",
    "alembic>=1.14,<1.15",
    "pydantic>=2.9,<3.0",
    "pydantic-settings>=2.6,<3.0",
    "httpx>=0.27,<0.28",
    "yfinance>=0.2.50,<0.3",
    "feedparser>=6.0.11,<7.0",
    "pandas>=2.2,<3.0",
    "lxml>=5.3,<6.0",
    "apscheduler>=3.10,<4.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3,<9.0",
    "pytest-asyncio>=0.24,<0.25",
    "pytest-cov>=6.0,<7.0",
    "testcontainers[postgresql]>=4.8,<5.0",
    "ruff>=0.7,<0.8",
    "freezegun>=1.5,<2.0",
]
```

Also add a `slow` marker config under the existing `[tool.pytest.ini_options]`:

```toml
markers = [
    "slow: marks tests as slow (deselect with -m 'not slow')",
]
```

- [ ] **Step 2: Install new deps**

```bash
uv pip install -e ".[dev]"
```

Expected: yfinance, feedparser, pandas, lxml, apscheduler, freezegun added; existing packages unchanged.

- [ ] **Step 3: Verify existing tests still pass**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(backend): add yfinance, feedparser, apscheduler, pandas, lxml deps"
```

---

### Task 2: Alembic migration for all six ingestion tables (test-first)

**Files:**
- Create: `backend/tests/test_migration_ingestion.py`
- Create: `backend/alembic/versions/0001_ingestion_tables.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_migration_ingestion.py`:

```python
import os
import subprocess
import sys

import pytest
from sqlalchemy import inspect


@pytest.mark.asyncio(loop_scope="session")
async def test_migration_creates_all_ingestion_tables(monkeypatch, pg_container, engine):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env={**os.environ},
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, f"alembic failed: {result.stderr}"

    expected = {
        "stocks",
        "prices",
        "dividend_history",
        "options_chains",
        "news_items",
        "pipeline_runs",
        "alembic_version",
    }
    async with engine.begin() as conn:
        tables = await conn.run_sync(lambda c: inspect(c).get_table_names())
    assert expected.issubset(set(tables)), f"missing: {expected - set(tables)}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_ingestion.py -v
```

Expected: FAIL with "missing: {'stocks', 'prices', ...}".

- [ ] **Step 3: Write the migration**

`backend/alembic/versions/0001_ingestion_tables.py`:

```python
"""ingestion tables

Revision ID: 0001
Revises:
Create Date: 2026-06-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "stocks",
        sa.Column("ticker", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("sector", sa.Text(), nullable=True),
        sa.Column("industry", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("added_at", sa.Date(), nullable=False),
        sa.Column("removed_at", sa.Date(), nullable=True),
    )
    op.create_index("ix_stocks_active", "stocks", ["active"])

    op.create_table(
        "prices",
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("open", sa.Numeric(12, 4), nullable=False),
        sa.Column("high", sa.Numeric(12, 4), nullable=False),
        sa.Column("low", sa.Numeric(12, 4), nullable=False),
        sa.Column("close", sa.Numeric(12, 4), nullable=False),
        sa.Column("adj_close", sa.Numeric(12, 4), nullable=False),
        sa.Column("volume", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "date"),
    )
    op.create_index("ix_prices_date", "prices", ["date"])

    op.create_table(
        "dividend_history",
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("ex_date", sa.Date(), nullable=False),
        sa.Column("pay_date", sa.Date(), nullable=True),
        sa.Column("amount_per_share", sa.Numeric(12, 6), nullable=False),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("ticker", "ex_date"),
    )

    op.create_table(
        "options_chains",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("expiration_date", sa.Date(), nullable=False),
        sa.Column("strike", sa.Numeric(10, 2), nullable=False),
        sa.Column("option_type", sa.Text(), nullable=False),
        sa.Column("bid", sa.Numeric(10, 4), nullable=True),
        sa.Column("ask", sa.Numeric(10, 4), nullable=True),
        sa.Column("last", sa.Numeric(10, 4), nullable=True),
        sa.Column("implied_volatility", sa.Numeric(8, 6), nullable=True),
        sa.Column("volume", sa.Integer(), nullable=True),
        sa.Column("open_interest", sa.Integer(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("option_type IN ('call', 'put')", name="ck_options_chains_type"),
    )
    op.create_index("ix_options_chains_ticker_snapshot", "options_chains", ["ticker", "snapshot_at"])
    op.create_index(
        "ix_options_chains_ticker_exp_strike_type",
        "options_chains",
        ["ticker", "expiration_date", "strike", "option_type"],
    )

    op.create_table(
        "news_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False, unique=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("sentiment_score", sa.Numeric(5, 4), nullable=True),
        sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.create_index("ix_news_items_ticker_published", "news_items", ["ticker", sa.text("published_at DESC")])

    op.create_table(
        "pipeline_runs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("steps_completed", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("llm_tokens_used", sa.Integer(), nullable=True),
        sa.Column("llm_cost_usd", sa.Numeric(10, 4), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_pipeline_runs_status",
        ),
    )
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", [sa.text("started_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_pipeline_runs_started_at", table_name="pipeline_runs")
    op.drop_table("pipeline_runs")
    op.drop_index("ix_news_items_ticker_published", table_name="news_items")
    op.drop_table("news_items")
    op.drop_index("ix_options_chains_ticker_exp_strike_type", table_name="options_chains")
    op.drop_index("ix_options_chains_ticker_snapshot", table_name="options_chains")
    op.drop_table("options_chains")
    op.drop_table("dividend_history")
    op.drop_index("ix_prices_date", table_name="prices")
    op.drop_table("prices")
    op.drop_index("ix_stocks_active", table_name="stocks")
    op.drop_table("stocks")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_ingestion.py -v
```

Expected: PASS.

- [ ] **Step 5: Run full test suite to confirm no regression**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: 8 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0001_ingestion_tables.py backend/tests/test_migration_ingestion.py
git commit -m "feat(backend): alembic migration for six ingestion tables"
```

---

### Task 3: SQLAlchemy ORM models for ingestion tables

**Files:**
- Create: `backend/app/models/stocks.py`
- Create: `backend/app/models/options.py`
- Create: `backend/app/models/news.py`
- Create: `backend/app/models/pipeline.py`
- Modify: `backend/app/models/__init__.py`

This task has no new tests — the models will be exercised by repo tests in Task 6. We only verify imports succeed and `Base.metadata` knows about them.

- [ ] **Step 1: Write `backend/app/models/stocks.py`**

```python
from datetime import date
from decimal import Decimal

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Stock(Base):
    __tablename__ = "stocks"

    ticker: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    sector: Mapped[str | None] = mapped_column(Text, nullable=True)
    industry: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    added_at: Mapped[date] = mapped_column(Date, nullable=False)
    removed_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class Price(Base):
    __tablename__ = "prices"
    __table_args__ = (PrimaryKeyConstraint("ticker", "date"),)

    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    date: Mapped[date] = mapped_column(Date)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    adj_close: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BIGINT, nullable=False)


class DividendHistory(Base):
    __tablename__ = "dividend_history"
    __table_args__ = (PrimaryKeyConstraint("ticker", "ex_date"),)

    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    ex_date: Mapped[date] = mapped_column(Date)
    pay_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_per_share: Mapped[Decimal] = mapped_column(Numeric(12, 6), nullable=False)
    frequency: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 2: Write `backend/app/models/options.py`**

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class OptionsChainRow(Base):
    __tablename__ = "options_chains"
    __table_args__ = (CheckConstraint("option_type IN ('call', 'put')", name="ck_options_chains_type"),)

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    expiration_date: Mapped[date] = mapped_column(Date, nullable=False)
    strike: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    option_type: Mapped[str] = mapped_column(Text, nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    ask: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    last: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    implied_volatility: Mapped[Decimal | None] = mapped_column(Numeric(8, 6), nullable=True)
    volume: Mapped[int | None] = mapped_column(Integer, nullable=True)
    open_interest: Mapped[int | None] = mapped_column(Integer, nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 3: Write `backend/app/models/news.py`**

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import BIGINT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 4: Write `backend/app/models/pipeline.py`**

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, BIGINT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('running', 'success', 'partial', 'failed')",
            name="ck_pipeline_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(BIGINT, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    steps_completed: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    errors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    llm_tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    llm_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
```

- [ ] **Step 5: Update `backend/app/models/__init__.py`** so `Base.metadata` discovers the new models when alembic env imports it

```python
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


# Import side-effect: register models with Base.metadata
from app.models import news, options, pipeline, stocks  # noqa: E402, F401
```

- [ ] **Step 6: Verify imports work**

```bash
.venv/bin/python -c "from app.models import Base, stocks, options, news, pipeline; \
print(sorted(Base.metadata.tables.keys()))"
```

Expected output:
```
['dividend_history', 'news_items', 'options_chains', 'pipeline_runs', 'prices', 'stocks']
```

- [ ] **Step 7: Run tests to confirm no regression**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: 8 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/app/models/stocks.py backend/app/models/options.py backend/app/models/news.py backend/app/models/pipeline.py backend/app/models/__init__.py
git commit -m "feat(backend): SQLAlchemy models for ingestion tables"
```

---

### Task 4: Source protocol definitions and DTOs

**Files:**
- Create: `backend/app/sources/__init__.py`
- Create: `backend/app/sources/base.py`

No tests in this task — protocols themselves are not callable. Behavior is tested via fakes in Task 5.

- [ ] **Step 1: Create empty `backend/app/sources/__init__.py`**

(zero bytes)

- [ ] **Step 2: Write `backend/app/sources/base.py`**

```python
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal, Protocol


@dataclass(frozen=True)
class StockMeta:
    ticker: str
    name: str
    sector: str | None
    industry: str | None


@dataclass(frozen=True)
class PriceBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    adj_close: float
    volume: int


@dataclass(frozen=True)
class DividendEvent:
    ex_date: date
    pay_date: date | None
    amount_per_share: float


@dataclass(frozen=True)
class OptionsChainRow:
    expiration_date: date
    strike: float
    option_type: Literal["call", "put"]
    bid: float | None
    ask: float | None
    last: float | None
    implied_volatility: float | None
    volume: int | None
    open_interest: int | None


@dataclass(frozen=True)
class NewsItemDTO:
    url: str
    title: str
    summary: str
    source: str
    published_at: datetime


class UniverseSource(Protocol):
    def fetch_sp500(self) -> Iterable[StockMeta]: ...


class PriceSource(Protocol):
    def fetch(self, ticker: str, since: date | None) -> Iterable[PriceBar]: ...


class DividendSource(Protocol):
    def fetch(self, ticker: str, since: date | None) -> Iterable[DividendEvent]: ...


class OptionsSource(Protocol):
    def fetch(self, ticker: str, expirations_within_days: int = 60) -> Iterable[OptionsChainRow]: ...


class NewsSource(Protocol):
    def fetch(self, ticker: str, since: datetime | None) -> Iterable[NewsItemDTO]: ...


@dataclass
class Sources:
    universe: UniverseSource
    prices: PriceSource
    dividends: DividendSource
    options: OptionsSource
    news: NewsSource
```

- [ ] **Step 3: Verify imports work**

```bash
.venv/bin/python -c "from app.sources.base import Sources, PriceBar, StockMeta, DividendEvent, OptionsChainRow, NewsItemDTO; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/sources/__init__.py backend/app/sources/base.py
git commit -m "feat(backend): source protocols and DTOs for ingestion"
```

---

### Task 5: In-memory test doubles for sources (test-first)

**Files:**
- Create: `backend/tests/sources/__init__.py`
- Create: `backend/tests/sources/test_fakes.py`
- Create: `backend/app/sources/fakes.py`

- [ ] **Step 1: Create empty `backend/tests/sources/__init__.py`**

(zero bytes)

- [ ] **Step 2: Write the failing test**

`backend/tests/sources/test_fakes.py`:

```python
from datetime import UTC, date, datetime

import pytest

from app.sources.base import DividendEvent, NewsItemDTO, OptionsChainRow, PriceBar, StockMeta


def test_inmemory_universe_returns_seeded_tickers():
    from app.sources.fakes import InMemoryUniverseSource

    src = InMemoryUniverseSource(
        [
            StockMeta("AAPL", "Apple", "Tech", "Consumer Electronics"),
            StockMeta("MSFT", "Microsoft", "Tech", "Software"),
        ]
    )
    out = list(src.fetch_sp500())
    assert [s.ticker for s in out] == ["AAPL", "MSFT"]


def test_inmemory_prices_returns_only_since_date():
    from app.sources.fakes import InMemoryPriceSource

    bars = {
        "AAPL": [
            PriceBar(date(2026, 1, 1), 100.0, 101.0, 99.0, 100.5, 100.5, 1000),
            PriceBar(date(2026, 1, 2), 100.5, 102.0, 100.0, 101.0, 101.0, 1500),
            PriceBar(date(2026, 1, 3), 101.0, 103.0, 100.5, 102.0, 102.0, 2000),
        ]
    }
    src = InMemoryPriceSource(bars)
    out = list(src.fetch("AAPL", since=date(2026, 1, 2)))
    assert [b.date for b in out] == [date(2026, 1, 2), date(2026, 1, 3)]


def test_inmemory_prices_unknown_ticker_raises():
    from app.sources.fakes import InMemoryPriceSource

    src = InMemoryPriceSource({"AAPL": []})
    with pytest.raises(KeyError):
        list(src.fetch("UNKNOWN", since=None))


def test_inmemory_dividends_returns_only_since_date():
    from app.sources.fakes import InMemoryDividendSource

    src = InMemoryDividendSource(
        {
            "KO": [
                DividendEvent(date(2026, 1, 15), date(2026, 2, 1), 0.46),
                DividendEvent(date(2026, 4, 15), date(2026, 5, 1), 0.46),
            ]
        }
    )
    out = list(src.fetch("KO", since=date(2026, 3, 1)))
    assert [d.ex_date for d in out] == [date(2026, 4, 15)]


def test_inmemory_options_returns_seeded_chain():
    from app.sources.fakes import InMemoryOptionsSource

    src = InMemoryOptionsSource(
        {
            "AAPL": [
                OptionsChainRow(date(2026, 7, 17), 200.0, "call", 5.0, 5.1, 5.05, 0.25, 100, 500),
            ]
        }
    )
    out = list(src.fetch("AAPL"))
    assert len(out) == 1
    assert out[0].strike == 200.0


def test_inmemory_news_returns_seeded_items_filtered_by_since():
    from app.sources.fakes import InMemoryNewsSource

    src = InMemoryNewsSource(
        {
            "AAPL": [
                NewsItemDTO("https://a.example/1", "T1", "S1", "yahoo", datetime(2026, 1, 1, tzinfo=UTC)),
                NewsItemDTO("https://a.example/2", "T2", "S2", "yahoo", datetime(2026, 1, 2, tzinfo=UTC)),
            ]
        }
    )
    out = list(src.fetch("AAPL", since=datetime(2026, 1, 2, tzinfo=UTC)))
    assert [n.url for n in out] == ["https://a.example/2"]
```

- [ ] **Step 3: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/sources/test_fakes.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.sources.fakes'`.

- [ ] **Step 4: Write `backend/app/sources/fakes.py`**

```python
from collections.abc import Iterable
from datetime import date, datetime

from app.sources.base import (
    DividendEvent,
    NewsItemDTO,
    OptionsChainRow,
    PriceBar,
    StockMeta,
)


class InMemoryUniverseSource:
    def __init__(self, stocks: Iterable[StockMeta]) -> None:
        self._stocks = list(stocks)

    def fetch_sp500(self) -> Iterable[StockMeta]:
        return list(self._stocks)


class InMemoryPriceSource:
    def __init__(self, bars: dict[str, list[PriceBar]]) -> None:
        self._bars = bars

    def fetch(self, ticker: str, since: date | None) -> Iterable[PriceBar]:
        rows = self._bars[ticker]
        if since is None:
            return list(rows)
        return [b for b in rows if b.date >= since]


class InMemoryDividendSource:
    def __init__(self, events: dict[str, list[DividendEvent]]) -> None:
        self._events = events

    def fetch(self, ticker: str, since: date | None) -> Iterable[DividendEvent]:
        rows = self._events.get(ticker, [])
        if since is None:
            return list(rows)
        return [d for d in rows if d.ex_date >= since]


class InMemoryOptionsSource:
    def __init__(self, chains: dict[str, list[OptionsChainRow]]) -> None:
        self._chains = chains

    def fetch(self, ticker: str, expirations_within_days: int = 60) -> Iterable[OptionsChainRow]:
        return list(self._chains.get(ticker, []))


class InMemoryNewsSource:
    def __init__(self, items: dict[str, list[NewsItemDTO]]) -> None:
        self._items = items

    def fetch(self, ticker: str, since: datetime | None) -> Iterable[NewsItemDTO]:
        rows = self._items.get(ticker, [])
        if since is None:
            return list(rows)
        return [n for n in rows if n.published_at >= since]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/sources/test_fakes.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/sources/fakes.py backend/tests/sources/__init__.py backend/tests/sources/test_fakes.py
git commit -m "feat(backend): in-memory test doubles for source protocols"
```

---

### Task 6: Pipeline repo with upsert helpers (test-first)

**Files:**
- Create: `backend/tests/pipeline/__init__.py`
- Create: `backend/tests/pipeline/test_repo.py`
- Create: `backend/app/pipeline/__init__.py`
- Create: `backend/app/pipeline/repo.py`

- [ ] **Step 1: Create empty `backend/tests/pipeline/__init__.py` and `backend/app/pipeline/__init__.py`**

Both zero bytes.

- [ ] **Step 2: Write the failing test**

`backend/tests/pipeline/test_repo.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
        env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_upsert_stocks_inserts_new_and_updates_existing(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.sources.base import StockMeta

    repo = PipelineRepo(session)
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple Inc.", "Tech", "Consumer Electronics")],
        today=date(2026, 6, 1),
    )
    # Re-run with a name change
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple", "Tech", "Consumer Electronics")],
        today=date(2026, 6, 1),
    )
    await session.commit()
    rows = await repo.list_active_tickers()
    assert rows == ["AAPL"]


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_deactivates_missing_tickers(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.sources.base import StockMeta

    repo = PipelineRepo(session)
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple", None, None), StockMeta("MSFT", "Microsoft", None, None)],
        today=date(2026, 6, 1),
    )
    await session.commit()

    # Second sync: only AAPL remains. MSFT should be deactivated.
    await repo.upsert_stocks(
        [StockMeta("AAPL", "Apple", None, None)],
        today=date(2026, 6, 2),
    )
    await session.commit()

    active = await repo.list_active_tickers()
    assert active == ["AAPL"]


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_upsert_prices_idempotent(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.sources.base import PriceBar, StockMeta

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("GOOG", "Alphabet", None, None)], today=date(2026, 6, 1))
    bars = [
        PriceBar(date(2026, 6, 1), 150.0, 151.0, 149.0, 150.5, 150.5, 1_000_000),
        PriceBar(date(2026, 6, 2), 150.5, 152.0, 150.0, 151.0, 151.0, 1_500_000),
    ]
    await repo.upsert_prices("GOOG", bars)
    await repo.upsert_prices("GOOG", bars)  # rerun
    await session.commit()

    last_date = await repo.last_price_date("GOOG")
    assert last_date == date(2026, 6, 2)


@pytest.mark.asyncio(loop_scope="session")
async def test_repo_start_and_finish_run(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo

    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=datetime(2026, 6, 1, 21, 15, tzinfo=UTC))
    await session.commit()
    assert run_id > 0

    await repo.finish_run(
        run_id,
        status="success",
        completed=["universe", "prices"],
        errors={},
        now=datetime(2026, 6, 1, 21, 17, tzinfo=UTC),
    )
    await session.commit()

    runs = await repo.recent_runs(limit=1)
    assert len(runs) == 1
    assert runs[0].status == "success"
    assert runs[0].steps_completed == ["universe", "prices"]
```

- [ ] **Step 3: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.repo'`.

- [ ] **Step 4: Write `backend/app/pipeline/repo.py`**

```python
from collections.abc import Iterable
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.news import NewsItem
from app.models.options import OptionsChainRow as OptionsChainRowORM
from app.models.pipeline import PipelineRun
from app.models.stocks import DividendHistory, Price, Stock
from app.sources.base import (
    DividendEvent,
    NewsItemDTO,
    OptionsChainRow,
    PriceBar,
    StockMeta,
)


class PipelineRepo:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ----- stocks -----

    async def upsert_stocks(self, stocks: Iterable[StockMeta], today: date) -> None:
        incoming = list(stocks)
        incoming_tickers = {s.ticker for s in incoming}
        for s in incoming:
            stmt = pg_insert(Stock).values(
                ticker=s.ticker,
                name=s.name,
                sector=s.sector,
                industry=s.industry,
                active=True,
                added_at=today,
                removed_at=None,
            ).on_conflict_do_update(
                index_elements=[Stock.ticker],
                set_={
                    "name": s.name,
                    "sector": s.sector,
                    "industry": s.industry,
                    "active": True,
                    "removed_at": None,
                },
            )
            await self.session.execute(stmt)

        # Deactivate anything no longer present
        if incoming_tickers:
            await self.session.execute(
                update(Stock)
                .where(Stock.ticker.notin_(incoming_tickers))
                .where(Stock.active.is_(True))
                .values(active=False, removed_at=today)
            )

    async def list_active_tickers(self) -> list[str]:
        rows = await self.session.execute(select(Stock.ticker).where(Stock.active.is_(True)).order_by(Stock.ticker))
        return [r[0] for r in rows.all()]

    # ----- prices -----

    async def upsert_prices(self, ticker: str, bars: Iterable[PriceBar]) -> int:
        bars = list(bars)
        if not bars:
            return 0
        values = [
            {
                "ticker": ticker,
                "date": b.date,
                "open": Decimal(str(b.open)),
                "high": Decimal(str(b.high)),
                "low": Decimal(str(b.low)),
                "close": Decimal(str(b.close)),
                "adj_close": Decimal(str(b.adj_close)),
                "volume": b.volume,
            }
            for b in bars
        ]
        stmt = pg_insert(Price).values(values).on_conflict_do_update(
            index_elements=[Price.ticker, Price.date],
            set_={
                "open": pg_insert(Price).excluded.open,
                "high": pg_insert(Price).excluded.high,
                "low": pg_insert(Price).excluded.low,
                "close": pg_insert(Price).excluded.close,
                "adj_close": pg_insert(Price).excluded.adj_close,
                "volume": pg_insert(Price).excluded.volume,
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def last_price_date(self, ticker: str) -> date | None:
        from sqlalchemy import func

        row = await self.session.execute(
            select(func.max(Price.date)).where(Price.ticker == ticker)
        )
        return row.scalar()

    # ----- dividends -----

    async def upsert_dividends(self, ticker: str, events: Iterable[DividendEvent]) -> int:
        events = list(events)
        if not events:
            return 0
        values = [
            {
                "ticker": ticker,
                "ex_date": e.ex_date,
                "pay_date": e.pay_date,
                "amount_per_share": Decimal(str(e.amount_per_share)),
            }
            for e in events
        ]
        stmt = pg_insert(DividendHistory).values(values).on_conflict_do_update(
            index_elements=[DividendHistory.ticker, DividendHistory.ex_date],
            set_={
                "pay_date": pg_insert(DividendHistory).excluded.pay_date,
                "amount_per_share": pg_insert(DividendHistory).excluded.amount_per_share,
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def last_dividend_ex_date(self, ticker: str) -> date | None:
        from sqlalchemy import func

        row = await self.session.execute(
            select(func.max(DividendHistory.ex_date)).where(DividendHistory.ticker == ticker)
        )
        return row.scalar()

    # ----- options (insert-only, daily snapshot) -----

    async def insert_options_snapshot(
        self, ticker: str, rows: Iterable[OptionsChainRow], snapshot_at: datetime
    ) -> int:
        rows = list(rows)
        if not rows:
            return 0
        values = [
            {
                "ticker": ticker,
                "expiration_date": r.expiration_date,
                "strike": Decimal(str(r.strike)),
                "option_type": r.option_type,
                "bid": Decimal(str(r.bid)) if r.bid is not None else None,
                "ask": Decimal(str(r.ask)) if r.ask is not None else None,
                "last": Decimal(str(r.last)) if r.last is not None else None,
                "implied_volatility": (
                    Decimal(str(r.implied_volatility)) if r.implied_volatility is not None else None
                ),
                "volume": r.volume,
                "open_interest": r.open_interest,
                "snapshot_at": snapshot_at,
            }
            for r in rows
        ]
        await self.session.execute(pg_insert(OptionsChainRowORM).values(values))
        return len(values)

    # ----- news -----

    async def insert_news(self, ticker: str, items: Iterable[NewsItemDTO]) -> int:
        items = list(items)
        if not items:
            return 0
        values = [
            {
                "ticker": ticker,
                "published_at": n.published_at,
                "source": n.source,
                "url": n.url,
                "title": n.title,
                "summary": n.summary,
            }
            for n in items
        ]
        stmt = pg_insert(NewsItem).values(values).on_conflict_do_nothing(index_elements=[NewsItem.url])
        result = await self.session.execute(stmt)
        return result.rowcount or 0

    # ----- yields (for options watchlist; T12M dividend / latest close) -----

    async def top_tickers_by_ttm_yield(self, limit: int, today: date) -> list[str]:
        """Trailing-12-month dividends divided by latest close. Used as a v1 watchlist proxy
        until Sub-project 3's screener provides a real ranking."""
        from sqlalchemy import func, text

        one_year_ago = date(today.year - 1, today.month, today.day) if today.month != 2 or today.day != 29 else date(today.year - 1, 2, 28)
        # latest close per ticker
        latest_close_subq = (
            select(Price.ticker, func.max(Price.date).label("max_date"))
            .group_by(Price.ticker)
            .subquery()
        )
        ttm_div_subq = (
            select(
                DividendHistory.ticker,
                func.sum(DividendHistory.amount_per_share).label("ttm"),
            )
            .where(DividendHistory.ex_date >= one_year_ago)
            .group_by(DividendHistory.ticker)
            .subquery()
        )
        stmt = (
            select(
                Stock.ticker,
                (ttm_div_subq.c.ttm / Price.close).label("yield_pct"),
            )
            .join(latest_close_subq, latest_close_subq.c.ticker == Stock.ticker)
            .join(Price, (Price.ticker == latest_close_subq.c.ticker) & (Price.date == latest_close_subq.c.max_date))
            .join(ttm_div_subq, ttm_div_subq.c.ticker == Stock.ticker)
            .where(Stock.active.is_(True))
            .order_by(text("yield_pct DESC"))
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return [r[0] for r in rows.all()]

    # ----- pipeline_runs -----

    async def start_run(self, now: datetime) -> int:
        run = PipelineRun(started_at=now, status="running", steps_completed=[], errors={})
        self.session.add(run)
        await self.session.flush()
        return run.id

    async def finish_run(
        self,
        run_id: int,
        status: str,
        completed: list[str],
        errors: dict,
        now: datetime | None = None,
    ) -> None:
        from datetime import UTC, datetime as dt

        await self.session.execute(
            update(PipelineRun)
            .where(PipelineRun.id == run_id)
            .values(
                status=status,
                steps_completed=completed,
                errors=errors,
                finished_at=now or dt.now(tz=UTC),
            )
        )

    async def recent_runs(self, limit: int) -> list[PipelineRun]:
        rows = await self.session.execute(
            select(PipelineRun).order_by(PipelineRun.started_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    async def get_run(self, run_id: int) -> PipelineRun | None:
        return await self.session.get(PipelineRun, run_id)
```

- [ ] **Step 5: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/__init__.py backend/app/pipeline/repo.py backend/tests/pipeline/__init__.py backend/tests/pipeline/test_repo.py
git commit -m "feat(backend): pipeline repo with upserts, pipeline_runs bookkeeping, TTM-yield query"
```

---

### Task 7: Step ABC and StepContext

**Files:**
- Create: `backend/app/pipeline/steps/__init__.py`
- Create: `backend/app/pipeline/steps/base.py`

No new tests — the ABC is exercised by step-specific tests in Tasks 8–12.

- [ ] **Step 1: Create empty `backend/app/pipeline/steps/__init__.py`**

(zero bytes for now; populated in Task 13 when DEFAULT_STEPS is wired)

- [ ] **Step 2: Write `backend/app/pipeline/steps/base.py`**

```python
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.pipeline.repo import PipelineRepo
from app.sources.base import Sources


class StepFailure(Exception):
    """Raised by a step when it fails at the step level (vs per-ticker failure)."""


@dataclass
class StepResult:
    """Returned by a successful step run. per_ticker_failures empty == clean run."""

    ok_count: int = 0
    per_ticker_failures: dict[str, str] = field(default_factory=dict)


@dataclass
class StepContext:
    repo: PipelineRepo
    sources: Sources
    run_id: int
    now: Callable[[], datetime] = lambda: datetime.now(tz=UTC)


class Step(ABC):
    """Base class for pipeline steps."""

    name: str = ""
    is_critical: bool = False

    def should_run(self, ctx: StepContext) -> bool:
        """Override to gate execution (e.g., universe runs only on the 1st of the month)."""
        return True

    @abstractmethod
    async def run(self, ctx: StepContext) -> StepResult: ...
```

- [ ] **Step 3: Verify imports**

```bash
.venv/bin/python -c "from app.pipeline.steps.base import Step, StepContext, StepResult, StepFailure; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/pipeline/steps/__init__.py backend/app/pipeline/steps/base.py
git commit -m "feat(backend): Step ABC, StepContext, StepResult, StepFailure"
```

---

### Task 8: Universe step (test-first)

**Files:**
- Create: `backend/tests/pipeline/test_step_universe.py`
- Create: `backend/app/pipeline/steps/universe.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_step_universe.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_universe_step_inserts_then_deactivates(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.universe import UniverseStep
    from app.sources.base import Sources, StockMeta
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    sources = Sources(
        universe=InMemoryUniverseSource(
            [
                StockMeta("AAPL", "Apple", "Tech", "Hardware"),
                StockMeta("MSFT", "Microsoft", "Tech", "Software"),
            ]
        ),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(
        repo=repo,
        sources=sources,
        run_id=0,
        now=lambda: datetime(2026, 6, 1, 21, 15, tzinfo=UTC),
    )

    result = await UniverseStep().run(ctx)
    await session.commit()
    assert result.ok_count == 2

    # Re-run with shrunk universe → MSFT deactivated.
    sources.universe = InMemoryUniverseSource([StockMeta("AAPL", "Apple", "Tech", "Hardware")])
    result = await UniverseStep().run(ctx)
    await session.commit()
    assert result.ok_count == 1

    active = await repo.list_active_tickers()
    assert active == ["AAPL"]


def test_universe_should_run_first_weekday_of_month():
    from app.pipeline.steps.universe import UniverseStep
    from app.pipeline.steps.base import StepContext

    step = UniverseStep()
    # 2026-06-01 is a Monday → first weekday of the month → run
    ctx_run = StepContext(
        repo=None, sources=None, run_id=0,
        now=lambda: datetime(2026, 6, 1, 21, 15, tzinfo=UTC),
    )
    assert step.should_run(ctx_run) is True

    # 2026-06-15 (third Monday) → skip
    ctx_skip = StepContext(
        repo=None, sources=None, run_id=0,
        now=lambda: datetime(2026, 6, 15, 21, 15, tzinfo=UTC),
    )
    assert step.should_run(ctx_skip) is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_universe.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.steps.universe'`.

- [ ] **Step 3: Write `backend/app/pipeline/steps/universe.py`**

```python
from datetime import date

from app.pipeline.steps.base import Step, StepContext, StepResult


class UniverseStep(Step):
    name = "universe"
    is_critical = False

    def should_run(self, ctx: StepContext) -> bool:
        now = ctx.now()
        # Run on the first weekday (Mon=0..Fri=4) of the month, or on an empty stocks table.
        if now.weekday() > 4:
            return False
        # First weekday of the month = day 1-3 (Mon Jun 1, or if Sat/Sun, first Monday is the 2nd or 3rd).
        return now.day <= 3 and now.weekday() <= 4 and self._is_first_weekday_of_month(now.date())

    def _is_first_weekday_of_month(self, d: date) -> bool:
        # The first weekday of the month is day 1 if Mon-Fri,
        # day 2 if d==2 and weekday()==0 (Sunday was day 1),
        # day 3 if d==3 and weekday()==0 (Saturday + Sunday were days 1-2).
        if d.weekday() > 4:
            return False
        for earlier_day in range(1, d.day):
            earlier = d.replace(day=earlier_day)
            if earlier.weekday() <= 4:
                return False
        return True

    async def run(self, ctx: StepContext) -> StepResult:
        stocks = list(ctx.sources.universe.fetch_sp500())
        today = ctx.now().date()
        await ctx.repo.upsert_stocks(stocks, today=today)
        return StepResult(ok_count=len(stocks))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_universe.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/steps/universe.py backend/tests/pipeline/test_step_universe.py
git commit -m "feat(backend): universe step refreshes stocks from S&P 500 source"
```

---

### Task 9: Prices step (test-first)

**Files:**
- Create: `backend/tests/pipeline/test_step_prices.py`
- Create: `backend/app/pipeline/steps/prices.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_step_prices.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


def _seed_stocks(repo, tickers):
    from app.sources.base import StockMeta
    return repo.upsert_stocks([StockMeta(t, t, None, None) for t in tickers], today=date(2026, 6, 1))


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_step_happy_path(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.prices import PricesStep
    from app.sources.base import PriceBar, Sources
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryPriceSource, InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    await _seed_stocks(repo, ["AAPL", "MSFT"])
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource(
            {
                "AAPL": [PriceBar(date(2026, 6, 1), 100, 101, 99, 100.5, 100.5, 1000)],
                "MSFT": [PriceBar(date(2026, 6, 1), 200, 201, 199, 200.5, 200.5, 2000)],
            }
        ),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await PricesStep(concurrency=2).run(ctx)
    await session.commit()
    assert result.ok_count == 2
    assert result.per_ticker_failures == {}
    assert await repo.last_price_date("AAPL") == date(2026, 6, 1)


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_step_isolates_per_ticker_failures(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.prices import PricesStep
    from app.sources.base import PriceBar, PriceSource, Sources
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryUniverseSource,
    )

    class FlakyPriceSource:
        def fetch(self, ticker, since):
            if ticker == "MSFT":
                raise RuntimeError("simulated yfinance failure")
            return [PriceBar(date(2026, 6, 1), 100, 101, 99, 100.5, 100.5, 1000)]

    repo = PipelineRepo(session)
    await _seed_stocks(repo, ["AAPL", "MSFT"])
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=FlakyPriceSource(),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    # Disable retries for this test by setting attempts=1
    result = await PricesStep(concurrency=2, attempts=1).run(ctx)
    await session.commit()
    assert result.ok_count == 1
    assert "MSFT" in result.per_ticker_failures
    assert "yfinance failure" in result.per_ticker_failures["MSFT"]


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_step_fails_when_below_critical_threshold(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext, StepFailure
    from app.pipeline.steps.prices import PricesStep
    from app.sources.base import Sources
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryUniverseSource,
    )

    class AlwaysFailPriceSource:
        def fetch(self, ticker, since):
            raise RuntimeError("everything is broken")

    repo = PipelineRepo(session)
    await _seed_stocks(repo, ["AAPL", "MSFT", "GOOG", "AMZN", "META"])
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=AlwaysFailPriceSource(),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    with pytest.raises(StepFailure):
        await PricesStep(concurrency=2, attempts=1, critical_success_threshold=0.8).run(ctx)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_prices.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.steps.prices'`.

- [ ] **Step 3: Write `backend/app/pipeline/steps/prices.py`**

```python
import asyncio
import logging
from collections.abc import Callable
from datetime import date

from app.pipeline.steps.base import Step, StepContext, StepFailure, StepResult

logger = logging.getLogger(__name__)


async def _retry(fn: Callable, attempts: int, base_delay: float = 1.0):
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return await asyncio.to_thread(fn)
        except Exception as e:
            last_exc = e
            if attempt == attempts - 1:
                break
            await asyncio.sleep(base_delay * (2**attempt))
    assert last_exc is not None
    raise last_exc


class PricesStep(Step):
    name = "prices"
    is_critical = True

    def __init__(
        self,
        concurrency: int = 10,
        attempts: int = 3,
        critical_success_threshold: float = 0.8,
        backfill_years: int = 5,
    ) -> None:
        self.concurrency = concurrency
        self.attempts = attempts
        self.critical_success_threshold = critical_success_threshold
        self.backfill_years = backfill_years

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult(ok_count=0)

        sem = asyncio.Semaphore(self.concurrency)
        today = ctx.now().date()

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    last = await ctx.repo.last_price_date(ticker)
                    since = self._since(last, today)
                    bars = await _retry(
                        lambda: list(ctx.sources.prices.fetch(ticker, since)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.upsert_prices(ticker, bars)
                    return ticker, None
                except Exception as e:
                    logger.warning("prices: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        success_rate = ok / len(results)
        if success_rate < self.critical_success_threshold:
            raise StepFailure(
                f"prices step success rate {success_rate:.0%} < threshold "
                f"{self.critical_success_threshold:.0%}"
            )
        return StepResult(ok_count=ok, per_ticker_failures=failures)

    def _since(self, last: date | None, today: date) -> date | None:
        if last is None:
            try:
                return date(today.year - self.backfill_years, today.month, today.day)
            except ValueError:
                # Feb 29 → Feb 28
                return date(today.year - self.backfill_years, today.month, today.day - 1)
        from datetime import timedelta

        return last + timedelta(days=1)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_prices.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/steps/prices.py backend/tests/pipeline/test_step_prices.py
git commit -m "feat(backend): prices step with per-ticker isolation and critical threshold"
```

---

### Task 10: Dividends step (test-first)

**Files:**
- Create: `backend/tests/pipeline/test_step_dividends.py`
- Create: `backend/app/pipeline/steps/dividends.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_step_dividends.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_dividends_step_upserts_and_idempotent(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.dividends import DividendsStep
    from app.sources.base import DividendEvent, Sources, StockMeta
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryPriceSource, InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", None, None)], today=date(2026, 6, 1))
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource(
            {"KO": [DividendEvent(date(2026, 1, 15), date(2026, 2, 1), 0.46)]}
        ),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    step = DividendsStep(concurrency=2, attempts=1)
    result1 = await step.run(ctx)
    await session.commit()
    assert result1.ok_count == 1
    assert await repo.last_dividend_ex_date("KO") == date(2026, 1, 15)

    # Re-run is idempotent
    result2 = await step.run(ctx)
    await session.commit()
    assert result2.ok_count == 1
    assert await repo.last_dividend_ex_date("KO") == date(2026, 1, 15)


@pytest.mark.asyncio(loop_scope="session")
async def test_dividends_step_isolates_failures(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.dividends import DividendsStep
    from app.sources.base import DividendEvent, Sources, StockMeta
    from app.sources.fakes import (
        InMemoryNewsSource, InMemoryOptionsSource, InMemoryPriceSource, InMemoryUniverseSource,
    )

    class FlakyDividendSource:
        def fetch(self, ticker, since):
            if ticker == "X":
                raise RuntimeError("nope")
            return [DividendEvent(date(2026, 1, 1), None, 0.5)]

    repo = PipelineRepo(session)
    await repo.upsert_stocks(
        [StockMeta("KO", "Coca-Cola", None, None), StockMeta("X", "X", None, None)],
        today=date(2026, 6, 1),
    )
    await session.commit()

    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=FlakyDividendSource(),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await DividendsStep(concurrency=2, attempts=1).run(ctx)
    await session.commit()
    assert result.ok_count == 1
    assert "X" in result.per_ticker_failures
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_dividends.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `backend/app/pipeline/steps/dividends.py`**

```python
import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class DividendsStep(Step):
    name = "dividends"
    is_critical = False

    def __init__(self, concurrency: int = 10, attempts: int = 3) -> None:
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult()

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    last = await ctx.repo.last_dividend_ex_date(ticker)
                    events = await _retry(
                        lambda: list(ctx.sources.dividends.fetch(ticker, last)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.upsert_dividends(ticker, events)
                    return ticker, None
                except Exception as e:
                    logger.warning("dividends: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_dividends.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/steps/dividends.py backend/tests/pipeline/test_step_dividends.py
git commit -m "feat(backend): dividends step with per-ticker isolation"
```

---

### Task 11: Options step (test-first)

**Files:**
- Create: `backend/tests/pipeline/test_step_options.py`
- Create: `backend/app/pipeline/steps/options.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_step_options.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_options_step_limits_to_top_watchlist(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.options import OptionsStep
    from app.sources.base import (
        DividendEvent, OptionsChainRow, PriceBar, Sources, StockMeta,
    )
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryPriceSource, InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    # Seed 3 tickers; only HIYIELD should have non-zero yield → watchlist of 1.
    await repo.upsert_stocks(
        [
            StockMeta("HIYIELD", "High Yield Co", None, None),
            StockMeta("NODIV", "No Div Co", None, None),
            StockMeta("LOWDIV", "Low Div Co", None, None),
        ],
        today=date(2026, 6, 1),
    )
    # Prices for all three (need close to compute yield)
    for t, close in [("HIYIELD", 100.0), ("NODIV", 100.0), ("LOWDIV", 100.0)]:
        await repo.upsert_prices(t, [PriceBar(date(2026, 6, 1), close, close, close, close, close, 1000)])
    # Dividends: HIYIELD pays 10, LOWDIV pays 0.10, NODIV nothing.
    await repo.upsert_dividends("HIYIELD", [DividendEvent(date(2026, 1, 1), None, 10.0)])
    await repo.upsert_dividends("LOWDIV", [DividendEvent(date(2026, 1, 1), None, 0.10)])
    await session.commit()

    chains = {
        "HIYIELD": [
            OptionsChainRow(date(2026, 7, 17), 110.0, "call", 1.0, 1.1, 1.05, 0.30, 50, 200),
        ],
        "NODIV": [
            OptionsChainRow(date(2026, 7, 17), 110.0, "call", 1.0, 1.1, 1.05, 0.30, 50, 200),
        ],
    }
    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource(chains),
        news=InMemoryNewsSource({}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    result = await OptionsStep(watchlist_size=1, concurrency=2, attempts=1).run(ctx)
    await session.commit()

    # Only HIYIELD should have been fetched and inserted.
    assert result.ok_count == 1
    from sqlalchemy import select
    from app.models.options import OptionsChainRow as OptionsRow
    rows = await session.execute(select(OptionsRow.ticker).distinct())
    assert {r[0] for r in rows.all()} == {"HIYIELD"}
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_options.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `backend/app/pipeline/steps/options.py`**

```python
import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class OptionsStep(Step):
    name = "options"
    is_critical = False

    def __init__(
        self,
        watchlist_size: int = 50,
        expirations_within_days: int = 60,
        concurrency: int = 10,
        attempts: int = 3,
    ) -> None:
        self.watchlist_size = watchlist_size
        self.expirations_within_days = expirations_within_days
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        today = ctx.now().date()
        # v1: watchlist = top N by trailing-12mo dividend yield.
        # Sub-project 3's screener will replace this with dividend_quality_score ranking.
        watchlist = await ctx.repo.top_tickers_by_ttm_yield(
            limit=self.watchlist_size, today=today
        )
        # Held tickers always included. None for now; placeholder for Sub-project 4.
        held: list[str] = []
        tickers = list(dict.fromkeys(list(watchlist) + held))  # preserve order, dedupe
        if not tickers:
            return StepResult()

        sem = asyncio.Semaphore(self.concurrency)
        snapshot_at = ctx.now()

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    rows = await _retry(
                        lambda: list(
                            ctx.sources.options.fetch(ticker, self.expirations_within_days)
                        ),
                        attempts=self.attempts,
                    )
                    await ctx.repo.insert_options_snapshot(ticker, rows, snapshot_at)
                    return ticker, None
                except Exception as e:
                    logger.warning("options: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_options.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/steps/options.py backend/tests/pipeline/test_step_options.py
git commit -m "feat(backend): options step with top-N-by-yield watchlist"
```

---

### Task 12: News step (test-first)

**Files:**
- Create: `backend/tests/pipeline/test_step_news.py`
- Create: `backend/app/pipeline/steps/news.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_step_news.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_news_step_dedupes_by_url_across_runs(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from sqlalchemy import func, select

    from app.models.news import NewsItem
    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.pipeline.steps.news import NewsStep
    from app.sources.base import (
        DividendEvent, NewsItemDTO, PriceBar, Sources, StockMeta,
    )
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryPriceSource, InMemoryUniverseSource,
    )

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", None, None)], today=date(2026, 6, 1))
    await repo.upsert_prices("KO", [PriceBar(date(2026, 6, 1), 60, 60, 60, 60, 60, 1000)])
    await repo.upsert_dividends("KO", [DividendEvent(date(2026, 1, 1), None, 1.84)])
    await session.commit()

    same_item = NewsItemDTO(
        url="https://example.com/ko-news-1",
        title="KO beats earnings",
        summary="...",
        source="yahoo",
        published_at=datetime(2026, 6, 1, 9, 0, tzinfo=UTC),
    )
    sources = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({"KO": [same_item]}),
    )
    ctx = StepContext(repo=repo, sources=sources, run_id=0, now=lambda: datetime(2026, 6, 1, tzinfo=UTC))

    step = NewsStep(watchlist_size=10, concurrency=2, attempts=1)
    await step.run(ctx)
    await session.commit()
    await step.run(ctx)  # rerun
    await session.commit()

    count = await session.execute(select(func.count(NewsItem.id)))
    assert count.scalar_one() == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_news.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Write `backend/app/pipeline/steps/news.py`**

```python
import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class NewsStep(Step):
    name = "news"
    is_critical = False

    def __init__(self, watchlist_size: int = 50, concurrency: int = 10, attempts: int = 2) -> None:
        self.watchlist_size = watchlist_size
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        today = ctx.now().date()
        watchlist = await ctx.repo.top_tickers_by_ttm_yield(
            limit=self.watchlist_size, today=today
        )
        held: list[str] = []
        tickers = list(dict.fromkeys(list(watchlist) + held))
        if not tickers:
            return StepResult()

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    items = await _retry(
                        lambda: list(ctx.sources.news.fetch(ticker, None)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.insert_news(ticker, items)
                    return ticker, None
                except Exception as e:
                    logger.warning("news: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        ok = len(results) - len(failures)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_news.py -v
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/steps/news.py backend/tests/pipeline/test_step_news.py
git commit -m "feat(backend): news step with URL dedupe across runs"
```

---

### Task 13: Orchestrator (`runner.py`) — test-first

**Files:**
- Create: `backend/tests/pipeline/test_runner.py`
- Create: `backend/app/pipeline/runner.py`
- Modify: `backend/app/pipeline/steps/__init__.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_runner.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        check=True,
    )


def _make_ctx(session):
    from app.pipeline.repo import PipelineRepo
    from app.pipeline.steps.base import StepContext
    from app.sources.base import Sources
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryPriceSource, InMemoryUniverseSource,
    )
    return StepContext(
        repo=PipelineRepo(session),
        sources=Sources(
            universe=InMemoryUniverseSource([]),
            prices=InMemoryPriceSource({}),
            dividends=InMemoryDividendSource({}),
            options=InMemoryOptionsSource({}),
            news=InMemoryNewsSource({}),
        ),
        run_id=0,
        now=lambda: datetime(2026, 6, 1, 21, 15, tzinfo=UTC),
    )


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_records_success(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepResult

    class OkStep(Step):
        name = "ok"
        is_critical = False

        async def run(self, ctx):
            return StepResult(ok_count=42)

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[OkStep()])
    await session.commit()
    assert summary.status == "success"
    assert summary.steps_completed == ["ok"]

    runs = await ctx.repo.recent_runs(limit=1)
    assert runs[0].status == "success"


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_records_partial_on_non_critical_failure(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepFailure, StepResult

    class OkStep(Step):
        name = "ok"
        is_critical = False
        async def run(self, ctx): return StepResult(ok_count=1)

    class FlakyStep(Step):
        name = "flaky"
        is_critical = False
        async def run(self, ctx):
            raise StepFailure("upstream returned 500")

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[OkStep(), FlakyStep()])
    await session.commit()
    assert summary.status == "partial"
    assert "flaky" in summary.errors
    assert summary.steps_completed == ["ok"]


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_stops_and_marks_failed_on_critical_failure(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepFailure, StepResult

    class CriticalFail(Step):
        name = "critical"
        is_critical = True
        async def run(self, ctx):
            raise StepFailure("prices below threshold")

    class Later(Step):
        name = "later"
        is_critical = False
        async def run(self, ctx):
            return StepResult(ok_count=999)  # should never run

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[CriticalFail(), Later()])
    await session.commit()
    assert summary.status == "failed"
    assert summary.steps_completed == []
    assert "later" not in summary.errors


@pytest.mark.asyncio(loop_scope="session")
async def test_runner_skips_steps_with_should_run_false(session, monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    from app.pipeline.runner import run_pipeline
    from app.pipeline.steps.base import Step, StepResult

    class GatedStep(Step):
        name = "gated"
        is_critical = False
        def should_run(self, ctx): return False
        async def run(self, ctx): return StepResult(ok_count=1)

    ctx = _make_ctx(session)
    summary = await run_pipeline(ctx, steps=[GatedStep()])
    await session.commit()
    assert summary.status == "success"
    assert summary.steps_completed == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.runner'`.

- [ ] **Step 3: Write `backend/app/pipeline/runner.py`**

```python
import logging
from dataclasses import dataclass

from app.pipeline.steps.base import Step, StepContext, StepFailure

logger = logging.getLogger(__name__)


@dataclass
class PipelineRunSummary:
    run_id: int
    status: str  # success | partial | failed
    steps_completed: list[str]
    errors: dict[str, dict]


async def run_pipeline(
    ctx: StepContext,
    steps: list[Step],
    existing_run_id: int | None = None,
) -> PipelineRunSummary:
    if existing_run_id is None:
        run_id = await ctx.repo.start_run(now=ctx.now())
    else:
        run_id = existing_run_id
    ctx.run_id = run_id

    completed: list[str] = []
    errors: dict[str, dict] = {}
    failed_critical = False

    for step in steps:
        if not step.should_run(ctx):
            logger.info("pipeline: skipping step %s (should_run=False)", step.name)
            continue
        try:
            logger.info("pipeline: starting step %s", step.name)
            result = await step.run(ctx)
            completed.append(step.name)
            if result.per_ticker_failures:
                errors[step.name] = {
                    "per_ticker": result.per_ticker_failures,
                    "ok_count": result.ok_count,
                }
            logger.info("pipeline: step %s ok=%d failures=%d", step.name, result.ok_count, len(result.per_ticker_failures))
        except StepFailure as e:
            logger.warning("pipeline: step %s failed: %s", step.name, e)
            errors[step.name] = {"reason": str(e)}
            if step.is_critical:
                failed_critical = True
                break

    if failed_critical:
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "success"

    await ctx.repo.finish_run(run_id, status=status, completed=completed, errors=errors, now=ctx.now())
    return PipelineRunSummary(run_id=run_id, status=status, steps_completed=completed, errors=errors)
```

- [ ] **Step 4: Populate `backend/app/pipeline/steps/__init__.py`** with `DEFAULT_STEPS`

```python
from app.pipeline.steps.base import Step, StepContext, StepFailure, StepResult
from app.pipeline.steps.dividends import DividendsStep
from app.pipeline.steps.news import NewsStep
from app.pipeline.steps.options import OptionsStep
from app.pipeline.steps.prices import PricesStep
from app.pipeline.steps.universe import UniverseStep


def default_steps() -> list[Step]:
    return [
        UniverseStep(),
        PricesStep(),
        DividendsStep(),
        OptionsStep(),
        NewsStep(),
    ]


__all__ = [
    "DividendsStep",
    "NewsStep",
    "OptionsStep",
    "PricesStep",
    "Step",
    "StepContext",
    "StepFailure",
    "StepResult",
    "UniverseStep",
    "default_steps",
]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_runner.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Full suite**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: ~22 passed (7 existing + 15 new from Tasks 2, 5, 6, 8, 9, 10, 11, 12, 13).

- [ ] **Step 7: Commit**

```bash
git add backend/app/pipeline/runner.py backend/app/pipeline/steps/__init__.py backend/tests/pipeline/test_runner.py
git commit -m "feat(backend): pipeline runner with success/partial/failed bookkeeping"
```

---

### Task 14: Production source implementations (yfinance, Wikipedia, Yahoo RSS)

**Files:**
- Create: `backend/app/sources/yfinance_source.py`
- Create: `backend/app/sources/wikipedia_source.py`
- Create: `backend/app/sources/yahoo_rss_source.py`

These are thin wrappers — no business logic. Tested only via the optional `@pytest.mark.slow` integration test added in Task 19. We don't unit-test them because the value is verifying real upstream shape, and mock-based tests of pure shape-conversion are low-signal.

- [ ] **Step 1: Write `backend/app/sources/yfinance_source.py`**

```python
from collections.abc import Iterable
from datetime import date, datetime

import yfinance as yf

from app.sources.base import DividendEvent, OptionsChainRow, PriceBar


class YFinancePriceSource:
    def fetch(self, ticker: str, since: date | None) -> Iterable[PriceBar]:
        t = yf.Ticker(ticker)
        kwargs: dict = {"auto_adjust": False, "actions": False}
        if since is not None:
            kwargs["start"] = since.isoformat()
        else:
            kwargs["period"] = "5y"
        df = t.history(**kwargs)
        for ts, row in df.iterrows():
            yield PriceBar(
                date=ts.date() if hasattr(ts, "date") else ts,
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                close=float(row["Close"]),
                adj_close=float(row.get("Adj Close", row["Close"])),
                volume=int(row["Volume"]),
            )


class YFinanceDividendSource:
    def fetch(self, ticker: str, since: date | None) -> Iterable[DividendEvent]:
        t = yf.Ticker(ticker)
        series = t.dividends  # pandas Series indexed by date
        for ts, amount in series.items():
            ex_date = ts.date() if hasattr(ts, "date") else ts
            if since is not None and ex_date < since:
                continue
            yield DividendEvent(ex_date=ex_date, pay_date=None, amount_per_share=float(amount))


class YFinanceOptionsSource:
    def fetch(
        self, ticker: str, expirations_within_days: int = 60
    ) -> Iterable[OptionsChainRow]:
        t = yf.Ticker(ticker)
        today = datetime.utcnow().date()
        for exp_str in (t.options or []):
            exp = datetime.strptime(exp_str, "%Y-%m-%d").date()
            if (exp - today).days > expirations_within_days:
                continue
            chain = t.option_chain(exp_str)
            for kind, df in (("call", chain.calls), ("put", chain.puts)):
                for _, row in df.iterrows():
                    yield OptionsChainRow(
                        expiration_date=exp,
                        strike=float(row["strike"]),
                        option_type=kind,
                        bid=_opt_float(row.get("bid")),
                        ask=_opt_float(row.get("ask")),
                        last=_opt_float(row.get("lastPrice")),
                        implied_volatility=_opt_float(row.get("impliedVolatility")),
                        volume=_opt_int(row.get("volume")),
                        open_interest=_opt_int(row.get("openInterest")),
                    )


def _opt_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # NaN guard


def _opt_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 2: Write `backend/app/sources/wikipedia_source.py`**

```python
from collections.abc import Iterable

import pandas as pd

from app.sources.base import StockMeta

SP500_WIKI_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"


class WikipediaSP500Source:
    def __init__(self, url: str = SP500_WIKI_URL) -> None:
        self.url = url

    def fetch_sp500(self) -> Iterable[StockMeta]:
        tables = pd.read_html(self.url)
        # The first table on the page is the constituents list.
        df = tables[0]
        for _, row in df.iterrows():
            ticker = str(row["Symbol"]).replace(".", "-")  # yfinance uses BRK-B not BRK.B
            yield StockMeta(
                ticker=ticker,
                name=str(row["Security"]),
                sector=str(row["GICS Sector"]) if pd.notna(row["GICS Sector"]) else None,
                industry=str(row["GICS Sub-Industry"]) if pd.notna(row["GICS Sub-Industry"]) else None,
            )
```

- [ ] **Step 3: Write `backend/app/sources/yahoo_rss_source.py`**

```python
from collections.abc import Iterable
from datetime import UTC, datetime
from time import mktime

import feedparser

from app.sources.base import NewsItemDTO

YAHOO_RSS_URL_TEMPLATE = "https://finance.yahoo.com/rss/headline?s={ticker}"


class YahooRssNewsSource:
    def __init__(self, url_template: str = YAHOO_RSS_URL_TEMPLATE) -> None:
        self.url_template = url_template

    def fetch(self, ticker: str, since: datetime | None) -> Iterable[NewsItemDTO]:
        feed = feedparser.parse(self.url_template.format(ticker=ticker))
        for entry in feed.entries:
            published_at = self._parse_dt(entry)
            if since is not None and published_at < since:
                continue
            yield NewsItemDTO(
                url=str(entry.get("link", "")).strip(),
                title=str(entry.get("title", "")),
                summary=str(entry.get("summary", "")),
                source="yahoo",
                published_at=published_at,
            )

    def _parse_dt(self, entry) -> datetime:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed is not None:
            return datetime.fromtimestamp(mktime(parsed), tz=UTC)
        return datetime.now(tz=UTC)
```

- [ ] **Step 4: Verify imports work**

```bash
.venv/bin/python -c "from app.sources.yfinance_source import YFinancePriceSource; \
from app.sources.wikipedia_source import WikipediaSP500Source; \
from app.sources.yahoo_rss_source import YahooRssNewsSource; print('ok')"
```

Expected: `ok`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/sources/yfinance_source.py backend/app/sources/wikipedia_source.py backend/app/sources/yahoo_rss_source.py
git commit -m "feat(backend): production source impls (yfinance, Wikipedia SP500, Yahoo RSS)"
```

---

### Task 15: APScheduler integration (test-first)

**Files:**
- Create: `backend/tests/pipeline/test_scheduler.py`
- Create: `backend/app/pipeline/scheduler.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/pipeline/test_scheduler.py`:

```python
def test_scheduler_job_has_weekday_17_15_eastern_cron():
    from app.pipeline.scheduler import build_cron_trigger

    trigger = build_cron_trigger()
    # CronTrigger fields are hard to introspect; sanity-check by stringifying.
    s = str(trigger)
    assert "day_of_week='mon-fri'" in s
    assert "hour='17'" in s
    assert "minute='15'" in s
    assert "America/New_York" in s


def test_scheduler_start_and_stop_idempotent():
    from app.pipeline.scheduler import PipelineScheduler

    sched = PipelineScheduler(job_callable=lambda: None)
    sched.start()
    sched.start()  # idempotent
    sched.stop()
    sched.stop()  # idempotent
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_scheduler.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.pipeline.scheduler'`.

- [ ] **Step 3: Write `backend/app/pipeline/scheduler.py`**

```python
import logging
from collections.abc import Callable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def build_cron_trigger() -> CronTrigger:
    return CronTrigger(
        day_of_week="mon-fri",
        hour=17,
        minute=15,
        timezone="America/New_York",
    )


class PipelineScheduler:
    def __init__(self, job_callable: Callable) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job_callable = job_callable
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.add_job(
            func=self._job_callable,
            trigger=build_cron_trigger(),
            id="daily_pipeline",
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=3600,
        )
        self._scheduler.start()
        self._started = True
        logger.info("pipeline scheduler started (weekdays 17:15 America/New_York)")

    def stop(self) -> None:
        if not self._started:
            return
        self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("pipeline scheduler stopped")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_scheduler.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/scheduler.py backend/tests/pipeline/test_scheduler.py
git commit -m "feat(backend): APScheduler weekday 17:15 ET cron for daily pipeline"
```

---

### Task 16: Pipeline HTTP API (test-first)

**Files:**
- Create: `backend/tests/test_pipeline_api.py`
- Create: `backend/app/api/pipeline.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_pipeline_api.py`:

```python
import os
import subprocess
import sys

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {
        **os.environ,
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        check=True,
    )


def _fresh_app():
    import sys as _sys
    for m in ("app.main", "app.api.health", "app.api.pipeline", "app.db", "app.config"):
        _sys.modules.pop(m, None)
    from app.main import create_app
    return create_app()


@pytest.mark.asyncio(loop_scope="session")
async def test_pipeline_runs_empty_initially(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    app = _fresh_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/pipeline/runs")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio(loop_scope="session")
async def test_pipeline_run_post_creates_run_row(monkeypatch, pg_container):
    monkeypatch.setenv("POSTGRES_USER", pg_container.username)
    monkeypatch.setenv("POSTGRES_PASSWORD", pg_container.password)
    monkeypatch.setenv("POSTGRES_DB", pg_container.dbname)
    monkeypatch.setenv("POSTGRES_HOST", pg_container.get_container_host_ip())
    monkeypatch.setenv("POSTGRES_PORT", str(pg_container.get_exposed_port(5432)))

    app = _fresh_app()

    # Replace production sources with fakes so the run doesn't actually call yfinance.
    from app.api import pipeline as pipeline_api
    from app.sources.base import Sources
    from app.sources.fakes import (
        InMemoryDividendSource, InMemoryNewsSource, InMemoryOptionsSource,
        InMemoryPriceSource, InMemoryUniverseSource,
    )
    pipeline_api._sources_override = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/pipeline/run")
        assert resp.status_code == 202
        run_id = resp.json()["run_id"]
        assert run_id > 0

        # Eventually visible in list (BackgroundTask should run quickly with empty sources).
        runs = (await client.get("/pipeline/runs")).json()
        assert any(r["id"] == run_id for r in runs)

    pipeline_api._sources_override = None
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_pipeline_api.py -v
```

Expected: `404 Not Found` for `/pipeline/runs`.

- [ ] **Step 3: Write `backend/app/api/pipeline.py`**

```python
import asyncio
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
from app.pipeline.runner import run_pipeline
from app.pipeline.steps import default_steps
from app.pipeline.steps.base import StepContext
from app.sources.base import Sources
from app.sources.wikipedia_source import WikipediaSP500Source
from app.sources.yahoo_rss_source import YahooRssNewsSource
from app.sources.yfinance_source import (
    YFinanceDividendSource,
    YFinanceOptionsSource,
    YFinancePriceSource,
)

router = APIRouter(prefix="/pipeline")
logger = logging.getLogger(__name__)

# Test seam: set to a Sources instance to override production wiring.
_sources_override: Sources | None = None


def _make_sources() -> Sources:
    if _sources_override is not None:
        return _sources_override
    return Sources(
        universe=WikipediaSP500Source(),
        prices=YFinancePriceSource(),
        dividends=YFinanceDividendSource(),
        options=YFinanceOptionsSource(),
        news=YahooRssNewsSource(),
    )


@router.get("/runs")
async def list_runs(limit: int = 30) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        runs = await repo.recent_runs(limit=limit)
        return [_run_to_dict(r) for r in runs]


@router.get("/runs/{run_id}")
async def get_run(run_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        run = await repo.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return _run_to_dict(run, full=True)


@router.post("/run", status_code=202)
async def trigger_run(
    background_tasks: BackgroundTasks,
    step: str | None = Query(default=None),
) -> dict:
    # Resolve step list first so unknown-step returns 400 synchronously.
    steps = default_steps()
    if step is not None:
        steps = [s for s in steps if s.name == step]
        if not steps:
            raise HTTPException(status_code=400, detail=f"unknown step: {step}")

    # Start the run synchronously so the caller has a stable run_id before
    # the background task fires.
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        run_id = await repo.start_run(now=datetime.now(tz=UTC))
        await session.commit()

    background_tasks.add_task(
        _run_in_background, run_id=run_id, step_names=[s.name for s in steps]
    )
    return {"run_id": run_id}


async def _run_in_background(run_id: int, step_names: list[str]) -> None:
    name_to_step = {s.name: s for s in default_steps()}
    steps = [name_to_step[n] for n in step_names if n in name_to_step]

    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=run_id)
        try:
            await run_pipeline(ctx, steps=steps, existing_run_id=run_id)
            await session.commit()
        except Exception:
            logger.exception("background pipeline failed")
            await session.rollback()


def _run_to_dict(run, full: bool = False) -> dict:
    out = {
        "id": run.id,
        "started_at": run.started_at.isoformat(),
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "status": run.status,
        "steps_completed": list(run.steps_completed or []),
        "error_count": len(run.errors or {}),
    }
    if full:
        out["errors"] = run.errors or {}
    return out
```

- [ ] **Step 4: Wire router in `backend/app/main.py`**

Modify `backend/app/main.py` to:

```python
from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.pipeline import router as pipeline_router


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Income Agent", version="0.1.0")
    app.include_router(health_router)
    app.include_router(pipeline_router)
    return app


app = create_app()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_pipeline_api.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/pipeline.py backend/app/main.py backend/tests/test_pipeline_api.py
git commit -m "feat(backend): /pipeline/runs and POST /pipeline/run with BackgroundTasks"
```

---

### Task 17: Scheduler wired into FastAPI lifespan

**Files:**
- Modify: `backend/app/main.py`

No new test — Task 15 already exercises the scheduler logic in isolation. We only verify the app still boots.

- [ ] **Step 1: Modify `backend/app/main.py`**

```python
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.pipeline import _make_sources, router as pipeline_router
from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
from app.pipeline.runner import run_pipeline
from app.pipeline.scheduler import PipelineScheduler
from app.pipeline.steps import default_steps
from app.pipeline.steps.base import StepContext

logger = logging.getLogger(__name__)


async def _scheduled_pipeline_job() -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        ctx = StepContext(
            repo=repo,
            sources=_make_sources(),
            run_id=0,
            now=lambda: datetime.now(tz=UTC),
        )
        try:
            await run_pipeline(ctx, steps=default_steps())
            await session.commit()
        except Exception:
            logger.exception("scheduled pipeline failed")
            await session.rollback()


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = PipelineScheduler(job_callable=_scheduled_pipeline_job)
    scheduler.start()
    try:
        yield
    finally:
        scheduler.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="Stock Income Agent", version="0.1.0", lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(pipeline_router)
    return app


app = create_app()
```

- [ ] **Step 2: Run all existing tests** (no new test here)

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: all previously-passing tests still pass.

- [ ] **Step 3: Verify the app boots locally**

```bash
POSTGRES_USER=stockagent POSTGRES_PASSWORD=devpass POSTGRES_DB=stockagent \
  POSTGRES_HOST=localhost POSTGRES_PORT=5432 \
  .venv/bin/python -c "from app.main import create_app; app = create_app(); print('ok'); print(sorted(r.path for r in app.routes))"
```

Expected output: `ok` followed by a route list that includes `/health`, `/pipeline/runs`, `/pipeline/runs/{run_id}`, `/pipeline/run`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/main.py
git commit -m "feat(backend): wire APScheduler into FastAPI lifespan"
```

---

### Task 18: CLI (`python -m app.pipeline`)

**Files:**
- Create: `backend/app/pipeline/cli.py`
- Create: `backend/app/pipeline/__main__.py`

Light testing — CLI is a thin wrapper around already-tested code paths. Verified by running it manually.

- [ ] **Step 1: Write `backend/app/pipeline/cli.py`**

```python
import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
from app.pipeline.runner import run_pipeline
from app.pipeline.steps import default_steps
from app.pipeline.steps.base import StepContext


def _make_sources():
    # Imported lazily so unit tests don't have to import yfinance.
    from app.sources.base import Sources
    from app.sources.wikipedia_source import WikipediaSP500Source
    from app.sources.yahoo_rss_source import YahooRssNewsSource
    from app.sources.yfinance_source import (
        YFinanceDividendSource,
        YFinanceOptionsSource,
        YFinancePriceSource,
    )
    return Sources(
        universe=WikipediaSP500Source(),
        prices=YFinancePriceSource(),
        dividends=YFinanceDividendSource(),
        options=YFinanceOptionsSource(),
        news=YahooRssNewsSource(),
    )


async def _run(step_filter: str | None) -> int:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        steps = default_steps()
        if step_filter is not None:
            steps = [s for s in steps if s.name == step_filter]
            if not steps:
                print(f"unknown step: {step_filter}", file=sys.stderr)
                return 2
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=0, now=lambda: datetime.now(tz=UTC))
        summary = await run_pipeline(ctx, steps=steps)
        await session.commit()
        print(f"run_id={summary.run_id} status={summary.status} steps={summary.steps_completed}")
        if summary.errors:
            print(f"errors: {summary.errors}")
        return 0 if summary.status != "failed" else 1


async def _backfill() -> int:
    """Force prices + dividends to fetch 5 years of history.

    Same as run, just runs only the prices and dividends steps. Their _since logic
    already does the right thing when DB is empty.
    """
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from app.pipeline.steps import DividendsStep, PricesStep, UniverseStep

        steps = [UniverseStep(), PricesStep(), DividendsStep()]
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=0, now=lambda: datetime.now(tz=UTC))
        summary = await run_pipeline(ctx, steps=steps)
        await session.commit()
        print(f"backfill complete: run_id={summary.run_id} status={summary.status}")
        return 0 if summary.status != "failed" else 1


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="app.pipeline")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Run the full pipeline (or one step).")
    run_p.add_argument("--step", default=None, help="Run only this step.")

    sub.add_parser("backfill", help="Backfill 5y of prices + dividends.")

    args = parser.parse_args(argv)
    if args.cmd == "run":
        return asyncio.run(_run(args.step))
    if args.cmd == "backfill":
        return asyncio.run(_backfill())
    parser.print_help()
    return 2
```

- [ ] **Step 2: Write `backend/app/pipeline/__main__.py`**

```python
import sys

from app.pipeline.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 3: Verify CLI help renders**

```bash
.venv/bin/python -m app.pipeline --help
```

Expected: two subcommands listed (`run`, `backfill`).

- [ ] **Step 4: Verify the run subcommand parses**

```bash
.venv/bin/python -m app.pipeline run --help
```

Expected: `--step` option listed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/pipeline/cli.py backend/app/pipeline/__main__.py
git commit -m "feat(backend): CLI for ad-hoc pipeline runs and backfill"
```

---

### Task 19: yfinance integration smoke test (slow, marked)

**Files:**
- Create: `backend/tests/test_yfinance_integration.py`

This test hits real yfinance. Skipped by default; opt-in via `-m slow`. Catches upstream schema breaks before they bite production runs.

- [ ] **Step 1: Write the test**

`backend/tests/test_yfinance_integration.py`:

```python
from datetime import date, timedelta

import pytest


@pytest.mark.slow
def test_yfinance_prices_returns_data_for_known_ticker():
    from app.sources.yfinance_source import YFinancePriceSource

    bars = list(
        YFinancePriceSource().fetch("KO", since=date.today() - timedelta(days=30))
    )
    assert len(bars) >= 5, f"expected at least 5 bars in last 30 days, got {len(bars)}"
    assert all(b.open > 0 for b in bars)


@pytest.mark.slow
def test_yfinance_dividends_returns_data_for_known_ticker():
    from app.sources.yfinance_source import YFinanceDividendSource

    events = list(
        YFinanceDividendSource().fetch("KO", since=date.today() - timedelta(days=400))
    )
    assert len(events) >= 1, "KO should have at least one dividend in the last 400 days"


@pytest.mark.slow
def test_yahoo_rss_returns_items_for_known_ticker():
    from app.sources.yahoo_rss_source import YahooRssNewsSource

    items = list(YahooRssNewsSource().fetch("KO", since=None))
    assert len(items) >= 1
    assert items[0].url.startswith("http")


@pytest.mark.slow
def test_wikipedia_sp500_returns_around_500_tickers():
    from app.sources.wikipedia_source import WikipediaSP500Source

    stocks = list(WikipediaSP500Source().fetch_sp500())
    assert 480 <= len(stocks) <= 520, f"expected ~500, got {len(stocks)}"
    assert all(s.ticker for s in stocks)
```

- [ ] **Step 2: Verify slow tests are skipped by default**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: all previous tests pass; 4 new ones marked as skipped (or simply not collected because of the marker; behavior depends on `addopts`). The key invariant: total non-slow pass count is unchanged.

- [ ] **Step 3: Optional: run the slow integration tests once (network required)**

```bash
.venv/bin/pytest tests/test_yfinance_integration.py -v -m slow
```

Expected: 4 passed (or skipped if outside network access; document failure).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_yfinance_integration.py
git commit -m "test(backend): slow integration smoke tests for yfinance, RSS, Wikipedia"
```

---

### Task 20: Default pytest selection — skip slow

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Modify `[tool.pytest.ini_options]` in `backend/pyproject.toml`** to add `addopts`

Replace the existing `[tool.pytest.ini_options]` block with:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
addopts = "-m 'not slow'"
markers = [
    "slow: marks tests as slow (deselect with -m 'not slow')",
]
filterwarnings = [
    "error",
    "ignore::DeprecationWarning:pydantic",
    "ignore::ResourceWarning:asyncpg",
    "ignore::pytest.PytestUnraisableExceptionWarning",
]
```

- [ ] **Step 2: Verify default run excludes slow tests**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -q
```

Expected: previous count of non-slow tests; the four `@pytest.mark.slow` tests are deselected.

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(backend): default pytest run excludes slow integration tests"
```

---

### Task 21: Full suite, lint, smoke

- [ ] **Step 1: Full backend test suite**

```bash
TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -v
```

Expected count: 7 foundation + 1 migration + 6 fake-source + 4 repo + 2 universe + 3 prices + 2 dividends + 1 options + 1 news + 4 runner + 2 scheduler + 2 api = **35 tests passing** (slow deselected).

- [ ] **Step 2: Ruff lint**

```bash
.venv/bin/ruff check .
```

Expected: `All checks passed!`. Fix any issues with `.venv/bin/ruff check --fix .` and reread before committing.

- [ ] **Step 3: Frontend tests unchanged** (sanity)

```bash
cd ../frontend && npm test -- --run
```

Expected: 4 passed (no regression — this sub-project touches no frontend code).

- [ ] **Step 4: If any lint fixes were applied, commit them**

```bash
cd /Users/tbergman/Documents/Workspace/stock-income-agent
git status
# If non-empty:
git add backend/
git commit -m "chore(backend): ruff lint cleanups"
```

---

### Task 22: Update CI workflow to include the slow-test job (optional)

**Files:**
- Modify: `.github/workflows/ci.yml`

CI gets a second job that runs slow tests on a nightly schedule, so upstream API breaks get caught early without polluting PR runs.

- [ ] **Step 1: Modify `.github/workflows/ci.yml`** — add a third top-level job `nightly-yfinance`:

```yaml
  nightly-yfinance:
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule'
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
      - name: Slow integration tests
        working-directory: backend
        env:
          POSTGRES_USER: stockagent
          POSTGRES_PASSWORD: ci_password
          POSTGRES_DB: stockagent
          POSTGRES_HOST: localhost
          POSTGRES_PORT: 5432
          APP_ENV: test
        run: pytest -v -m slow
```

Also add a `schedule:` trigger at the top of the file:

```yaml
on:
  push:
    branches: [main, master]
  pull_request:
  schedule:
    - cron: "0 6 * * *"   # daily at 06:00 UTC
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: nightly job for slow yfinance integration tests"
```

---

## Self-review checklist

After completing all 22 tasks:

- [ ] All 22 tasks have a green checkmark on every step.
- [ ] `pytest -v` shows 35 tests passing (slow deselected).
- [ ] `pytest -v -m slow` shows 4 additional integration tests passing (requires network).
- [ ] `ruff check .` is clean.
- [ ] `POST /pipeline/run` returns 202 + `run_id`; the run row's `status` becomes `success`/`partial`/`failed` shortly after.
- [ ] `GET /pipeline/runs` returns a list; `GET /pipeline/runs/{id}` returns a single record.
- [ ] `python -m app.pipeline run --step prices` runs only the prices step.
- [ ] `python -m app.pipeline backfill` runs universe + prices + dividends with the 5y backfill `_since` rule.
- [ ] No file references types/methods/properties defined in another task with a different name. (Type-consistency check.)
- [ ] No `Sub-project 3` features have leaked in (no screener, no `screenings` table, no LLM calls).

When all checks pass, Sub-project 2 (Data Ingestion) is complete and ready for Sub-project 3 (Analysis & Recommendations).
