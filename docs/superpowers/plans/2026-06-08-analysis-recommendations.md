# Analysis & Recommendations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Steps 2–5 of the daily pipeline — DividendScreener, DividendSafetyAnalyst (LLM), OptionsRecommender (LLM, dormant), and Recommender — plus the fundamentals data they need, an LLM client seam, and read/approve/reject HTTP for recommendations.

**Architecture:** Four new pipeline steps slot into `default_steps()` between ingestion and the LLM analysts (`… → fundamentals → screener → options → news → safety → options_recommender → recommender`). All scoring math lives in a pure `app/analysis/` package (no DB, no network). The Anthropic call is isolated behind an `LLMClient` protocol exactly as upstream data is isolated behind source protocols; steps receive it via `StepContext.llm`. Tests inject `FakeLLMClient` + `InMemoryFundamentalsSource`.

**Tech Stack:** Python 3.12, SQLAlchemy 2.x async + Alembic, `anthropic` SDK (Sonnet 4.6, structured outputs via `messages.parse`), yfinance, pytest + pytest-asyncio, testcontainers Postgres.

**Pre-flight:** Sub-projects 1 & 2 complete. `backend/.venv` exists with `uv pip install -e ".[dev]"` run. Postgres reachable for tests via testcontainers. Spec: [`docs/superpowers/specs/2026-06-08-analysis-recommendations-design.md`](../specs/2026-06-08-analysis-recommendations-design.md).

---

## Conventions

**TDD rhythm for every task:** write the failing test → run it and confirm it fails → implement the minimum → run and confirm it passes → commit.

**All shell commands run from `backend/`.** All pytest invocations use `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest …`. Lint with `.venv/bin/ruff check .`.

**Commit format:** Conventional Commits (`feat:`, `test:`, `chore:`, `docs:`).

**Imports:** stdlib → third-party (blank line) → `app.*`; ruff sorts.

**Add the `anthropic` dependency first:** this is Task 0.

---

## File Structure

**New dependency (`backend/pyproject.toml`):** `anthropic>=0.40,<1.0` (production).

**New source files**
- `backend/app/sources/fundamentals_yfinance.py` — production fundamentals (yfinance quarterly statements)
- (modify) `backend/app/sources/base.py` — `FundamentalsSnapshot` DTO, `FundamentalsSource` protocol, `Sources.fundamentals`
- (modify) `backend/app/sources/fakes.py` — `InMemoryFundamentalsSource`

**New LLM package**
- `backend/app/llm/__init__.py`
- `backend/app/llm/schemas.py` — `SafetyAssessment`, `CallPick` Pydantic models
- `backend/app/llm/base.py` — `LLMUsage`, `LLMClient` protocol, `FakeLLMClient`
- `backend/app/llm/prompts.py` — versioned prompt builders
- `backend/app/llm/anthropic_client.py` — production `AnthropicLLMClient`

**New analysis package**
- `backend/app/analysis/__init__.py`
- `backend/app/analysis/screener.py` — pure scoring functions + `ScreenerSignals`
- `backend/app/analysis/options_scoring.py` — pure OTM filter / scoring

**New model files**
- `backend/app/models/fundamentals.py` — `Fundamentals`
- `backend/app/models/screening.py` — `Screening`
- `backend/app/models/safety.py` — `DividendSafetyScore`
- `backend/app/models/recommendation.py` — `Recommendation`
- (modify) `backend/app/models/__init__.py` — register new modules

**New pipeline files**
- `backend/app/pipeline/steps/fundamentals.py`
- `backend/app/pipeline/steps/screener.py`
- `backend/app/pipeline/steps/safety.py`
- `backend/app/pipeline/steps/options_recommender.py`
- `backend/app/pipeline/steps/recommender.py`
- (modify) `backend/app/pipeline/steps/base.py` — `StepContext.llm`
- (modify) `backend/app/pipeline/steps/__init__.py` — `default_steps()` ordering
- (modify) `backend/app/pipeline/steps/options.py` — screener-driven watchlist
- (modify) `backend/app/pipeline/repo.py` — reads/writes for the four tables + LLM cost
- (modify) `backend/app/main.py`, `backend/app/api/pipeline.py` — wire `llm` + `fundamentals`

**New API files**
- `backend/app/api/recommendations.py`
- `backend/app/api/stocks.py`

**New migration**
- `backend/alembic/versions/0002_analysis_tables.py`

**New config**
- (modify) `backend/app/config.py` — `llm_model`

**New tests** — one per unit (paths shown inline in each task).

---

### Task 0: Add the `anthropic` dependency

**Files:** Modify `backend/pyproject.toml`

- [ ] **Step 1:** In the `dependencies` list, add after the existing `apscheduler` line:

```toml
    "anthropic>=0.40,<1.0",
```

- [ ] **Step 2: Install**

Run: `.venv/bin/uv pip install -e ".[dev]"`
Expected: resolves and installs `anthropic`.

- [ ] **Step 3: Verify import**

Run: `.venv/bin/python -c "import anthropic; print(anthropic.__version__)"`
Expected: prints a version, no error.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "chore(backend): add anthropic SDK dependency"
```

---

### Task 1: Config — `llm_model`

**Files:** Modify `backend/app/config.py`; Test `backend/tests/test_config.py`

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_config.py`:

```python
def test_llm_model_default(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    from app.config import Settings

    assert Settings().llm_model == "claude-sonnet-4-6"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_config.py::test_llm_model_default -v`
Expected: FAIL (`AttributeError`/validation: no `llm_model`).

- [ ] **Step 3: Implement** — in `backend/app/config.py`, add below the `anthropic_api_key` field:

```python
    llm_model: str = Field(default="claude-sonnet-4-6")
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat(backend): llm_model setting (default claude-sonnet-4-6)"
```

---

### Task 2: ORM models for the four new tables

**Files:** Create `backend/app/models/{fundamentals,screening,safety,recommendation}.py`; Modify `backend/app/models/__init__.py`; Test `backend/tests/test_models_import.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_models_import.py`:

```python
def test_new_models_registered():
    from app.models import Base
    import app.models  # noqa: F401

    tables = set(Base.metadata.tables)
    assert {"fundamentals", "screenings", "dividend_safety_scores", "recommendations"} <= tables
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_models_import.py -v`
Expected: FAIL (tables absent).

- [ ] **Step 3: Implement** — create `backend/app/models/fundamentals.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, PrimaryKeyConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Fundamentals(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (PrimaryKeyConstraint("ticker", "fiscal_period"),)

    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    fiscal_period: Mapped[str] = mapped_column(Text)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    eps: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    fcf: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    net_income: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_debt: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_equity: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    dividends_paid: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Create `backend/app/models/screening.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Screening(Base):
    __tablename__ = "screenings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    dividend_quality_score: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    signals: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    passed_screen: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Create `backend/app/models/safety.py`:

```python
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class DividendSafetyScore(Base):
    __tablename__ = "dividend_safety_scores"

    id: Mapped[int] = mapped_column(SmallInteger().with_variant(__import__("sqlalchemy").Integer, "postgresql"), primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    payout_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    fcf_coverage: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    debt_to_equity: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    consecutive_years_paid: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    concerns: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)
    llm_reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    llm_model: Mapped[str] = mapped_column(Text, nullable=False)
    llm_prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    scored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

> Simplify the `id` line to a plain `Integer` PK — drop the `with_variant` cleverness:

```python
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
```

and add `Integer` to the import. The final `safety.py` import line is:
`from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, SmallInteger, Text`.

Create `backend/app/models/recommendation.py`:

```python
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Recommendation(Base):
    __tablename__ = "recommendations"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'superseded', 'executed')",
            name="ck_recommendations_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"))
    confidence: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    reasoning: Mapped[str] = mapped_column(Text, nullable=False)
    signals_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    llm_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_prompt_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")
    approval_mode: Mapped[str] = mapped_column(Text, nullable=False, default="manual")
    decided_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

Modify `backend/app/models/__init__.py` — extend the import line:

```python
from app.models import (  # noqa: E402, F401
    fundamentals,
    news,
    options,
    pipeline,
    recommendation,
    safety,
    screening,
    stocks,
)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_models_import.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/models/
git commit -m "feat(backend): ORM models for fundamentals, screenings, safety, recommendations"
```

---

### Task 3: Alembic migration `0002`

**Files:** Create `backend/alembic/versions/0002_analysis_tables.py`; Test `backend/tests/test_migration_analysis.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_migration_analysis.py`:

```python
import os
import subprocess
import sys

import pytest
from sqlalchemy import text

from app.db import get_session_factory


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
        capture_output=True, text=True, env=env,
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_analysis_tables_exist(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username,
        "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname,
        "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    for tbl in ("fundamentals", "screenings", "dividend_safety_scores", "recommendations"):
        row = await session.execute(text(f"SELECT to_regclass('{tbl}')"))
        assert row.scalar() == tbl
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_analysis.py -v`
Expected: FAIL (tables missing).

- [ ] **Step 3: Implement** — create `backend/alembic/versions/0002_analysis_tables.py`:

```python
"""analysis tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-08

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fundamentals",
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("fiscal_period", sa.Text(), nullable=False),
        sa.Column("revenue", sa.Numeric(18, 2), nullable=True),
        sa.Column("eps", sa.Numeric(12, 4), nullable=True),
        sa.Column("fcf", sa.Numeric(18, 2), nullable=True),
        sa.Column("net_income", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_debt", sa.Numeric(18, 2), nullable=True),
        sa.Column("total_equity", sa.Numeric(18, 2), nullable=True),
        sa.Column("dividends_paid", sa.Numeric(18, 2), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("ticker", "fiscal_period"),
    )

    op.create_table(
        "screenings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("dividend_quality_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("signals", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("passed_screen", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_screenings_run_id", "screenings", ["run_id"])
    op.create_index("ix_screenings_ticker_created", "screenings", ["ticker", "created_at"])

    op.create_table(
        "dividend_safety_scores",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("payout_ratio", sa.Numeric(8, 4), nullable=True),
        sa.Column("fcf_coverage", sa.Numeric(8, 4), nullable=True),
        sa.Column("debt_to_equity", sa.Numeric(8, 4), nullable=True),
        sa.Column("consecutive_years_paid", sa.SmallInteger(), nullable=True),
        sa.Column("concerns", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("ARRAY[]::text[]")),
        sa.Column("llm_reasoning", sa.Text(), nullable=False),
        sa.Column("llm_model", sa.Text(), nullable=False),
        sa.Column("llm_prompt_version", sa.Text(), nullable=False),
        sa.Column("scored_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_safety_ticker_scored", "dividend_safety_scores", ["ticker", "scored_at"])

    op.create_table(
        "recommendations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("signals_snapshot", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("llm_model", sa.Text(), nullable=True),
        sa.Column("llm_prompt_version", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("approval_mode", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'superseded', 'executed')",
            name="ck_recommendations_status",
        ),
    )
    op.create_index("ix_recommendations_status", "recommendations", ["status"])
    op.create_index("ix_recommendations_run_id", "recommendations", ["run_id"])
    op.create_index("ix_recommendations_ticker_created", "recommendations", ["ticker", "created_at"])


def downgrade() -> None:
    op.drop_table("recommendations")
    op.drop_table("dividend_safety_scores")
    op.drop_table("screenings")
    op.drop_table("fundamentals")
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_analysis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/0002_analysis_tables.py tests/test_migration_analysis.py
git commit -m "feat(backend): alembic migration for analysis tables"
```

---

### Task 4: FundamentalsSource protocol, DTO, and fake

**Files:** Modify `backend/app/sources/base.py`, `backend/app/sources/fakes.py`; Test `backend/tests/sources/test_fundamentals_fake.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/sources/test_fundamentals_fake.py`:

```python
from app.sources.base import FundamentalsSnapshot
from app.sources.fakes import InMemoryFundamentalsSource


def test_fake_fundamentals_returns_snapshots():
    snap = FundamentalsSnapshot(
        fiscal_period="2026Q1", revenue=100.0, eps=2.0, fcf=30.0,
        net_income=20.0, total_debt=50.0, total_equity=80.0, dividends_paid=10.0,
    )
    src = InMemoryFundamentalsSource({"KO": [snap]})
    assert list(src.fetch("KO")) == [snap]
    assert list(src.fetch("MISSING")) == []
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/sources/test_fundamentals_fake.py -v`
Expected: FAIL (`ImportError`).

- [ ] **Step 3: Implement** — in `backend/app/sources/base.py`, add the DTO after `NewsItemDTO`:

```python
@dataclass(frozen=True)
class FundamentalsSnapshot:
    fiscal_period: str
    revenue: float | None
    eps: float | None
    fcf: float | None
    net_income: float | None
    total_debt: float | None
    total_equity: float | None
    dividends_paid: float | None
```

add the protocol after `NewsSource`:

```python
class FundamentalsSource(Protocol):
    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]: ...
```

and add a field to `Sources` (with a default so existing constructions keep working):

```python
@dataclass
class Sources:
    universe: UniverseSource
    prices: PriceSource
    dividends: DividendSource
    options: OptionsSource
    news: NewsSource
    fundamentals: "FundamentalsSource | None" = None
```

In `backend/app/sources/fakes.py`, add the import `FundamentalsSnapshot` to the existing `from app.sources.base import (...)` block, then append:

```python
class InMemoryFundamentalsSource:
    def __init__(self, data: dict[str, list[FundamentalsSnapshot]]) -> None:
        self._data = data

    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]:
        return list(self._data.get(ticker, []))
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/sources/test_fundamentals_fake.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/sources/base.py app/sources/fakes.py tests/sources/test_fundamentals_fake.py
git commit -m "feat(backend): FundamentalsSource protocol, DTO, in-memory fake"
```

---

### Task 5: Pure screener scoring (`analysis/screener.py`)

**Files:** Create `backend/app/analysis/__init__.py`, `backend/app/analysis/screener.py`; Test `backend/tests/analysis/test_screener.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/analysis/__init__.py` (empty) and `backend/tests/analysis/test_screener.py`:

```python
from app.analysis.screener import (
    ScreenerSignals,
    compute_debt_to_equity,
    compute_fcf_coverage,
    compute_payout_ratio,
    compute_quality_score,
    compute_ttm_yield,
)


def test_ttm_yield():
    assert compute_ttm_yield(2.0, 50.0) == 0.04
    assert compute_ttm_yield(2.0, 0.0) is None
    assert compute_ttm_yield(2.0, None) is None


def test_payout_ratio():
    assert compute_payout_ratio(10.0, 20.0) == 0.5
    assert compute_payout_ratio(10.0, 0.0) is None
    assert compute_payout_ratio(10.0, None) is None


def test_fcf_coverage():
    assert compute_fcf_coverage(30.0, 10.0) == 3.0
    assert compute_fcf_coverage(30.0, 0.0) is None


def test_debt_to_equity():
    assert compute_debt_to_equity(50.0, 100.0) == 0.5
    assert compute_debt_to_equity(50.0, 0.0) is None


def test_quality_score_rewards_safe_dividend():
    safe = ScreenerSignals(
        ttm_yield=0.04, payout_ratio=0.4, fcf_coverage=3.0,
        debt_to_equity=0.3, consecutive_years_paid=30, earnings_growth_5y=0.08,
    )
    risky = ScreenerSignals(
        ttm_yield=0.09, payout_ratio=0.95, fcf_coverage=0.8,
        debt_to_equity=3.0, consecutive_years_paid=1, earnings_growth_5y=-0.1,
    )
    assert compute_quality_score(safe) > compute_quality_score(risky)
    assert 0.0 <= compute_quality_score(safe) <= 100.0
    assert 0.0 <= compute_quality_score(risky) <= 100.0


def test_quality_score_handles_missing_data():
    empty = ScreenerSignals(None, None, None, None, None, None)
    assert compute_quality_score(empty) == 0.0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/analysis/test_screener.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** — create `backend/app/analysis/__init__.py` (empty) and `backend/app/analysis/screener.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenerSignals:
    ttm_yield: float | None
    payout_ratio: float | None
    fcf_coverage: float | None
    debt_to_equity: float | None
    consecutive_years_paid: int | None
    earnings_growth_5y: float | None


def compute_ttm_yield(ttm_dividends: float | None, price: float | None) -> float | None:
    if not ttm_dividends or not price:
        return None
    return ttm_dividends / price


def compute_payout_ratio(dividends_paid: float | None, net_income: float | None) -> float | None:
    if dividends_paid is None or not net_income:
        return None
    return dividends_paid / net_income


def compute_fcf_coverage(fcf: float | None, dividends_paid: float | None) -> float | None:
    if fcf is None or not dividends_paid:
        return None
    return fcf / dividends_paid


def compute_debt_to_equity(total_debt: float | None, total_equity: float | None) -> float | None:
    if total_debt is None or not total_equity:
        return None
    return total_debt / total_equity


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def compute_quality_score(s: ScreenerSignals) -> float:
    """Composite 0–100. Each sub-score is 0–1; weighted, scaled to 100.
    Missing inputs contribute 0 to their component."""
    # Payout ratio: best at/below 0.5, unsustainable above ~0.7.
    payout = 0.0 if s.payout_ratio is None else _clamp(1.0 - (s.payout_ratio - 0.5) / 0.5) if s.payout_ratio > 0.5 else 1.0
    # FCF coverage: safe at >= 1.5; linear up to 1.5.
    coverage = 0.0 if s.fcf_coverage is None else _clamp(s.fcf_coverage / 1.5)
    # Debt/equity: lower is better; 0 -> 1, >= 2 -> 0.
    leverage = 0.0 if s.debt_to_equity is None else _clamp(1.0 - s.debt_to_equity / 2.0)
    # Track record: 25 years -> 1.0.
    track = 0.0 if s.consecutive_years_paid is None else _clamp(s.consecutive_years_paid / 25.0)
    # Growth: -10% -> 0, +10% -> 1.
    growth = 0.0 if s.earnings_growth_5y is None else _clamp((s.earnings_growth_5y + 0.1) / 0.2)

    weighted = 0.30 * payout + 0.25 * coverage + 0.20 * leverage + 0.15 * track + 0.10 * growth
    return round(weighted * 100.0, 2)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/analysis/test_screener.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/analysis/__init__.py app/analysis/screener.py tests/analysis/
git commit -m "feat(backend): pure dividend screener scoring functions"
```

---

### Task 6: Pure options scoring (`analysis/options_scoring.py`)

**Files:** Create `backend/app/analysis/options_scoring.py`; Test `backend/tests/analysis/test_options_scoring.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/analysis/test_options_scoring.py`:

```python
from datetime import date

from app.analysis.options_scoring import CandidateCall, filter_otm_calls, score_call
from app.sources.base import OptionsChainRow


def _row(strike, opt_type="call", iv=0.3, bid=2.0, ask=2.2):
    return OptionsChainRow(
        expiration_date=date(2026, 7, 17), strike=strike, option_type=opt_type,
        bid=bid, ask=ask, last=2.1, implied_volatility=iv, volume=100, open_interest=500,
    )


def test_filter_otm_calls_keeps_3_to_7_pct():
    price = 100.0
    rows = [_row(95), _row(103), _row(105), _row(110), _row(103, opt_type="put")]
    out = filter_otm_calls(rows, price, min_pct=0.03, max_pct=0.07)
    strikes = sorted(c.strike for c in out)
    assert strikes == [103.0, 105.0]  # 95 ITM, 110 too far, put excluded


def test_score_call_prefers_higher_premium_yield():
    price = 100.0
    high = score_call(CandidateCall(strike=105.0, premium=3.0, iv=0.3,
                                    expiration_date=date(2026, 7, 17)), price)
    low = score_call(CandidateCall(strike=105.0, premium=1.0, iv=0.3,
                                   expiration_date=date(2026, 7, 17)), price)
    assert high.score > low.score
    assert 0.0 <= high.prob_assignment <= 1.0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/analysis/test_options_scoring.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/analysis/options_scoring.py`:

```python
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from app.sources.base import OptionsChainRow


@dataclass(frozen=True)
class CandidateCall:
    strike: float
    premium: float
    iv: float | None
    expiration_date: date


@dataclass(frozen=True)
class ScoredCall:
    candidate: CandidateCall
    premium_yield: float
    prob_assignment: float
    score: float


def filter_otm_calls(
    rows: Iterable[OptionsChainRow], price: float, min_pct: float = 0.03, max_pct: float = 0.07
) -> list[CandidateCall]:
    out: list[CandidateCall] = []
    for r in rows:
        if r.option_type != "call":
            continue
        moneyness = (r.strike - price) / price
        if min_pct <= moneyness <= max_pct:
            premium = r.bid if r.bid is not None else (r.last or 0.0)
            out.append(CandidateCall(strike=r.strike, premium=premium, iv=r.implied_volatility,
                                     expiration_date=r.expiration_date))
    return out


def _prob_assignment(strike: float, price: float, iv: float | None) -> float:
    """Rough proxy: closer-to-the-money and higher-IV calls are likelier to be assigned.
    Bounded 0–1. Not Black–Scholes; good enough for ranking."""
    moneyness = (strike - price) / price  # positive for OTM
    iv = iv if iv else 0.3
    raw = 0.5 - moneyness / (iv if iv > 0 else 0.3)
    return max(0.0, min(1.0, raw))


def score_call(c: CandidateCall, price: float) -> ScoredCall:
    premium_yield = c.premium / price if price else 0.0
    prob = _prob_assignment(c.strike, price, c.iv)
    # Reward premium income, penalize assignment probability (regret).
    score = premium_yield * 100.0 - prob * 2.0
    return ScoredCall(candidate=c, premium_yield=premium_yield, prob_assignment=prob, score=score)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/analysis/test_options_scoring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/analysis/options_scoring.py tests/analysis/test_options_scoring.py
git commit -m "feat(backend): pure covered-call scoring functions"
```

---

### Task 7: LLM schemas + `FakeLLMClient`

**Files:** Create `backend/app/llm/{__init__.py,schemas.py,base.py}`; Test `backend/tests/llm/test_fake_llm.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/llm/__init__.py` (empty) and `backend/tests/llm/test_fake_llm.py`:

```python
import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import SafetyAssessment


def test_fake_returns_canned_and_usage():
    canned = SafetyAssessment(score=80, concerns=["payout rising"], outlook="stable", reasoning="ok")
    client = FakeLLMClient(by_key={"KO": canned}, usage=LLMUsage(100, 50, 0.001))

    parsed, usage = client.complete_structured(
        system="s", prompt="p", schema=SafetyAssessment, prompt_version="safety-v1", key="KO",
    )
    assert parsed == canned
    assert usage == LLMUsage(100, 50, 0.001)


def test_fake_invalid_mode_raises():
    client = FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0), raise_for={"BAD"})
    with pytest.raises(ValueError):
        client.complete_structured(
            system="s", prompt="p", schema=SafetyAssessment, prompt_version="v", key="BAD",
        )
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/llm/test_fake_llm.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/llm/__init__.py` (empty), `backend/app/llm/schemas.py`:

```python
from datetime import date
from typing import Literal

from pydantic import BaseModel


class SafetyAssessment(BaseModel):
    score: int
    concerns: list[str]
    outlook: Literal["improving", "stable", "deteriorating"]
    reasoning: str


class CallPick(BaseModel):
    strike: float
    expiration_date: date
    expected_premium: float
    prob_assignment: float
    reasoning: str
```

create `backend/app/llm/base.py`:

```python
from collections.abc import Set
from dataclasses import dataclass, field
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float


class LLMClient(Protocol):
    def complete_structured(
        self, *, system: str, prompt: str, schema: type[T], prompt_version: str, key: str,
    ) -> tuple[T, LLMUsage]: ...


@dataclass
class FakeLLMClient:
    """Deterministic test double. Returns canned schema instances keyed by `key`."""

    by_key: dict[str, BaseModel]
    usage: LLMUsage
    raise_for: Set[str] = field(default_factory=set)

    def complete_structured(self, *, system, prompt, schema, prompt_version, key):
        if key in self.raise_for:
            raise ValueError(f"fake LLM forced failure for {key}")
        value = self.by_key[key]
        if not isinstance(value, schema):
            raise TypeError(f"canned value for {key} is not {schema.__name__}")
        return value, self.usage
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/llm/test_fake_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/llm/__init__.py app/llm/schemas.py app/llm/base.py tests/llm/
git commit -m "feat(backend): LLM schemas, LLMClient protocol, FakeLLMClient"
```

---

### Task 8: Production `AnthropicLLMClient`

**Files:** Create `backend/app/llm/anthropic_client.py`; Test `backend/tests/llm/test_anthropic_client.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/llm/test_anthropic_client.py` (mocks the SDK; no network):

```python
from types import SimpleNamespace

import pytest

from app.llm.anthropic_client import AnthropicLLMClient, compute_cost_usd
from app.llm.schemas import SafetyAssessment


def test_compute_cost_sonnet():
    # 1M input @ $3, 1M output @ $15
    assert compute_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000) == pytest.approx(18.0)


def test_complete_structured_parses_and_computes_usage(monkeypatch):
    parsed = SafetyAssessment(score=70, concerns=[], outlook="stable", reasoning="r")
    fake_response = SimpleNamespace(
        parsed_output=parsed,
        usage=SimpleNamespace(input_tokens=1000, output_tokens=500),
    )

    class FakeMessages:
        def parse(self, **kwargs):
            assert kwargs["model"] == "claude-sonnet-4-6"
            assert kwargs["output_format"] is SafetyAssessment
            return fake_response

    client = AnthropicLLMClient(model="claude-sonnet-4-6", api_key="x")
    client._client = SimpleNamespace(messages=FakeMessages())  # inject fake SDK

    out, usage = client.complete_structured(
        system="s", prompt="p", schema=SafetyAssessment, prompt_version="safety-v1", key="KO",
    )
    assert out == parsed
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 500
    assert usage.cost_usd == pytest.approx(1000 / 1e6 * 3 + 500 / 1e6 * 15)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/llm/test_anthropic_client.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/llm/anthropic_client.py`:

```python
import logging

import anthropic

from app.llm.base import LLMUsage

logger = logging.getLogger(__name__)

# ($ per 1M input tokens, $ per 1M output tokens)
_PRICING: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

_MAX_TOKENS = 1024


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = _PRICING.get(model, (3.0, 15.0))
    return input_tokens / 1_000_000 * in_price + output_tokens / 1_000_000 * out_price


class AnthropicLLMClient:
    def __init__(self, model: str, api_key: str) -> None:
        self.model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete_structured(self, *, system, prompt, schema, prompt_version, key):
        response = self._client.messages.parse(
            model=self.model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_format=schema,
        )
        parsed = response.parsed_output
        if parsed is None:
            raise ValueError(f"LLM returned no parsable output for {key} (prompt {prompt_version})")
        usage = LLMUsage(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cost_usd=compute_cost_usd(self.model, response.usage.input_tokens, response.usage.output_tokens),
        )
        return parsed, usage
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/llm/test_anthropic_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/llm/anthropic_client.py tests/llm/test_anthropic_client.py
git commit -m "feat(backend): production AnthropicLLMClient with structured outputs + cost"
```

---

### Task 9: Versioned prompts

**Files:** Create `backend/app/llm/prompts.py`; Test `backend/tests/llm/test_prompts.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/llm/test_prompts.py`:

```python
from app.llm.prompts import (
    SAFETY_PROMPT_VERSION,
    SAFETY_SYSTEM,
    build_safety_prompt,
)


def test_build_safety_prompt_includes_metrics_and_empty_lessons():
    prompt = build_safety_prompt(
        ticker="KO",
        metrics={"payout_ratio": 0.5, "fcf_coverage": 2.0, "debt_to_equity": 0.4},
        recent_dividends=["2026-03-15: 0.46"],
        recent_news=["Coca-Cola raises guidance"],
        active_lessons=[],  # empty until Sub-project 5
    )
    assert "KO" in prompt
    assert "payout_ratio" in prompt
    assert "Coca-Cola raises guidance" in prompt
    assert SAFETY_PROMPT_VERSION == "safety-v1"
    assert "safety analyst" in SAFETY_SYSTEM.lower()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/llm/test_prompts.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/llm/prompts.py`:

```python
import json

SAFETY_PROMPT_VERSION = "safety-v1"

SAFETY_SYSTEM = (
    "You are a conservative dividend safety analyst. Given fundamentals, recent "
    "dividend history, and news for a single stock, assess the likelihood that the "
    "company sustains (and ideally grows) its dividend over the next 12 months. "
    "Be skeptical: weight payout ratio, free-cash-flow coverage, leverage, and any "
    "deteriorating news heavily. Return a calibrated score from 0 (imminent cut risk) "
    "to 100 (rock-solid)."
)


def build_safety_prompt(
    *, ticker: str, metrics: dict, recent_dividends: list[str],
    recent_news: list[str], active_lessons: list[str],
) -> str:
    lessons_block = "\n".join(f"- {x}" for x in active_lessons) or "(none yet)"
    news_block = "\n".join(f"- {x}" for x in recent_news) or "(no recent news)"
    divs_block = "\n".join(f"- {x}" for x in recent_dividends) or "(no recent dividends)"
    return (
        f"Ticker: {ticker}\n\n"
        f"Computed safety metrics:\n{json.dumps(metrics, indent=2, default=str)}\n\n"
        f"Recent dividend declarations:\n{divs_block}\n\n"
        f"Recent news headlines:\n{news_block}\n\n"
        f"Active learned lessons (apply if relevant):\n{lessons_block}\n"
    )


OPTIONS_PROMPT_VERSION = "options-v1"

OPTIONS_SYSTEM = (
    "You are an options income analyst. Given a holding's price and a short list of "
    "pre-scored out-of-the-money call candidates, pick the single best covered call to "
    "sell: maximize premium income while keeping the probability of assignment modest. "
    "Prefer 30–45 days to expiration."
)


def build_options_prompt(*, ticker: str, price: float, candidates: list[dict]) -> str:
    return (
        f"Ticker: {ticker}\nCurrent price: {price}\n\n"
        f"Candidate calls (pre-scored):\n{json.dumps(candidates, indent=2, default=str)}\n\n"
        "Pick the best one and explain why."
    )
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/llm/test_prompts.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/llm/prompts.py tests/llm/test_prompts.py
git commit -m "feat(backend): versioned safety and options prompt builders"
```

---

### Task 10: `StepContext.llm` field

**Files:** Modify `backend/app/pipeline/steps/base.py`; Test `backend/tests/pipeline/test_step_context_llm.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_step_context_llm.py`:

```python
from app.llm.base import FakeLLMClient, LLMUsage
from app.pipeline.steps.base import StepContext


def test_step_context_accepts_llm():
    llm = FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0))
    ctx = StepContext(repo=None, sources=None, run_id=1, llm=llm)
    assert ctx.llm is llm


def test_step_context_llm_defaults_none():
    ctx = StepContext(repo=None, sources=None, run_id=1)
    assert ctx.llm is None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_context_llm.py -v`
Expected: FAIL (`TypeError`: unexpected kwarg `llm`).

- [ ] **Step 3: Implement** — in `backend/app/pipeline/steps/base.py`, add the import and field. Add to the top imports:

```python
from app.llm.base import LLMClient
```

and add the field to `StepContext` (after `now`, since it has a default):

```python
@dataclass
class StepContext:
    repo: PipelineRepo
    sources: Sources
    run_id: int
    now: Callable[[], datetime] = field(default=_utc_now)
    llm: LLMClient | None = None
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_context_llm.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/base.py tests/pipeline/test_step_context_llm.py
git commit -m "feat(backend): StepContext gains optional llm client"
```

---

### Task 11: Repo methods for the new tables + LLM cost

**Files:** Modify `backend/app/pipeline/repo.py`; Test `backend/tests/pipeline/test_repo_analysis.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_repo_analysis.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.pipeline.repo import PipelineRepo
from app.sources.base import FundamentalsSnapshot, StockMeta


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
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_fundamentals_and_recs_roundtrip(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "Staples", "Beverages")], today=_now().date())

    await repo.upsert_fundamentals("KO", [FundamentalsSnapshot(
        "2026Q1", revenue=100.0, eps=2.0, fcf=30.0, net_income=20.0,
        total_debt=50.0, total_equity=80.0, dividends_paid=10.0)])
    funds = await repo.latest_fundamentals("KO")
    assert funds is not None and float(funds.net_income) == 20.0

    run_id = await repo.start_run(now=_now())
    await repo.insert_screening(run_id, "KO", score=82.5, signals={"ttm_yield": 0.03}, passed=True, now=_now())
    screenings = await repo.get_screenings(run_id)
    assert len(screenings) == 1 and screenings[0].ticker == "KO"
    top = await repo.top_screened_tickers(run_id, limit=10)
    assert top == ["KO"]

    await repo.insert_safety_score("KO", score=80, payout_ratio=0.5, fcf_coverage=3.0,
                                   debt_to_equity=0.4, consecutive_years_paid=30, concerns=["x"],
                                   reasoning="r", model="claude-sonnet-4-6", prompt_version="safety-v1", now=_now())
    latest = await repo.latest_safety_score("KO")
    assert latest is not None and latest.score == 80

    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_shares": 10}, reasoning="solid", signals_snapshot={"score": 82.5},
        model="claude-sonnet-4-6", prompt_version="safety-v1", now=_now())
    rec = await repo.get_recommendation(rec_id)
    assert rec.status == "pending" and rec.type == "add_position"

    listed = await repo.list_recommendations(status="pending", type_=None)
    assert any(r.id == rec_id for r in listed)

    await repo.add_llm_usage(run_id, tokens=1500, cost=0.012)
    run = await repo.get_run(run_id)
    assert run.llm_tokens_used == 1500
    await session.commit()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo_analysis.py -v`
Expected: FAIL (methods missing).

- [ ] **Step 3: Implement** — in `backend/app/pipeline/repo.py`, extend the imports:

```python
from app.models.fundamentals import Fundamentals
from app.models.recommendation import Recommendation
from app.models.safety import DividendSafetyScore
from app.models.screening import Screening
from app.sources.base import FundamentalsSnapshot
```

(add `FundamentalsSnapshot` to the existing `from app.sources.base import (...)` block instead of a duplicate line if you prefer — either is fine.)

Append these methods to `PipelineRepo`:

```python
    # ----- fundamentals -----

    async def upsert_fundamentals(self, ticker: str, snaps: Iterable[FundamentalsSnapshot]) -> int:
        snaps = list(snaps)
        if not snaps:
            return 0
        now = datetime.now(tz=UTC)

        def dec(x):
            return Decimal(str(x)) if x is not None else None

        values = [
            {
                "ticker": ticker, "fiscal_period": s.fiscal_period,
                "revenue": dec(s.revenue), "eps": dec(s.eps), "fcf": dec(s.fcf),
                "net_income": dec(s.net_income), "total_debt": dec(s.total_debt),
                "total_equity": dec(s.total_equity), "dividends_paid": dec(s.dividends_paid),
                "snapshot_at": now,
            }
            for s in snaps
        ]
        stmt = pg_insert(Fundamentals).values(values).on_conflict_do_update(
            index_elements=[Fundamentals.ticker, Fundamentals.fiscal_period],
            set_={
                "revenue": pg_insert(Fundamentals).excluded.revenue,
                "eps": pg_insert(Fundamentals).excluded.eps,
                "fcf": pg_insert(Fundamentals).excluded.fcf,
                "net_income": pg_insert(Fundamentals).excluded.net_income,
                "total_debt": pg_insert(Fundamentals).excluded.total_debt,
                "total_equity": pg_insert(Fundamentals).excluded.total_equity,
                "dividends_paid": pg_insert(Fundamentals).excluded.dividends_paid,
                "snapshot_at": pg_insert(Fundamentals).excluded.snapshot_at,
            },
        )
        await self.session.execute(stmt)
        return len(values)

    async def latest_fundamentals(self, ticker: str) -> Fundamentals | None:
        row = await self.session.execute(
            select(Fundamentals).where(Fundamentals.ticker == ticker)
            .order_by(Fundamentals.fiscal_period.desc()).limit(1)
        )
        return row.scalar_one_or_none()

    async def fundamentals_history(self, ticker: str, limit: int = 8) -> list[Fundamentals]:
        rows = await self.session.execute(
            select(Fundamentals).where(Fundamentals.ticker == ticker)
            .order_by(Fundamentals.fiscal_period.desc()).limit(limit)
        )
        return list(rows.scalars().all())

    # ----- screenings -----

    async def insert_screening(self, run_id, ticker, score, signals, passed, now) -> None:
        self.session.add(Screening(
            run_id=run_id, ticker=ticker, dividend_quality_score=Decimal(str(score)),
            signals=signals, passed_screen=passed, created_at=now,
        ))
        await self.session.flush()

    async def get_screenings(self, run_id: int) -> list[Screening]:
        rows = await self.session.execute(
            select(Screening).where(Screening.run_id == run_id)
            .order_by(Screening.dividend_quality_score.desc())
        )
        return list(rows.scalars().all())

    async def top_screened_tickers(self, run_id: int, limit: int) -> list[str]:
        rows = await self.session.execute(
            select(Screening.ticker).where(Screening.run_id == run_id)
            .order_by(Screening.dividend_quality_score.desc()).limit(limit)
        )
        return [r[0] for r in rows.all()]

    async def latest_screening_run_id(self) -> int | None:
        row = await self.session.execute(select(func.max(Screening.run_id)))
        return row.scalar()

    # ----- safety scores -----

    async def insert_safety_score(self, ticker, score, payout_ratio, fcf_coverage,
                                  debt_to_equity, consecutive_years_paid, concerns,
                                  reasoning, model, prompt_version, now) -> None:
        def dec(x):
            return Decimal(str(x)) if x is not None else None

        self.session.add(DividendSafetyScore(
            ticker=ticker, score=score, payout_ratio=dec(payout_ratio),
            fcf_coverage=dec(fcf_coverage), debt_to_equity=dec(debt_to_equity),
            consecutive_years_paid=consecutive_years_paid, concerns=list(concerns),
            llm_reasoning=reasoning, llm_model=model, llm_prompt_version=prompt_version,
            scored_at=now,
        ))
        await self.session.flush()

    async def latest_safety_score(self, ticker: str) -> DividendSafetyScore | None:
        row = await self.session.execute(
            select(DividendSafetyScore).where(DividendSafetyScore.ticker == ticker)
            .order_by(DividendSafetyScore.scored_at.desc()).limit(1)
        )
        return row.scalar_one_or_none()

    # ----- recommendations -----

    async def insert_recommendation(self, run_id, type, ticker, confidence, payload,
                                    reasoning, signals_snapshot, model, prompt_version, now) -> int:
        rec = Recommendation(
            run_id=run_id, type=type, ticker=ticker, confidence=confidence, payload=payload,
            reasoning=reasoning, signals_snapshot=signals_snapshot, llm_model=model,
            llm_prompt_version=prompt_version, status="pending", approval_mode="manual",
            created_at=now,
        )
        self.session.add(rec)
        await self.session.flush()
        return rec.id

    async def list_recommendations(self, status: str | None, type_: str | None) -> list[Recommendation]:
        stmt = select(Recommendation)
        if status is not None:
            stmt = stmt.where(Recommendation.status == status)
        if type_ is not None:
            stmt = stmt.where(Recommendation.type == type_)
        stmt = stmt.order_by(Recommendation.created_at.desc())
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def get_recommendation(self, rec_id: int) -> Recommendation | None:
        return await self.session.get(Recommendation, rec_id)

    async def set_recommendation_status(self, rec_id, status, decided_by, now,
                                        reject_reason: str | None = None) -> bool:
        rec = await self.session.get(Recommendation, rec_id)
        if rec is None or rec.status != "pending":
            return False
        rec.status = status
        rec.decided_by = decided_by
        rec.decided_at = now
        if reject_reason is not None:
            payload = dict(rec.payload or {})
            payload["reject_reason"] = reject_reason
            rec.payload = payload
        await self.session.flush()
        return True

    # ----- LLM cost bookkeeping -----

    async def add_llm_usage(self, run_id: int, tokens: int, cost: float) -> None:
        await self.session.execute(
            update(PipelineRun).where(PipelineRun.id == run_id).values(
                llm_tokens_used=func.coalesce(PipelineRun.llm_tokens_used, 0) + tokens,
                llm_cost_usd=func.coalesce(PipelineRun.llm_cost_usd, 0) + Decimal(str(cost)),
            )
        )
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo_analysis.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/repo.py tests/pipeline/test_repo_analysis.py
git commit -m "feat(backend): repo CRUD for fundamentals, screenings, safety, recommendations, llm cost"
```

---

### Task 12: Fundamentals ingestion step

**Files:** Create `backend/app/pipeline/steps/fundamentals.py`; Test `backend/tests/pipeline/test_step_fundamentals.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_step_fundamentals.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.fundamentals import FundamentalsStep
from app.sources.base import FundamentalsSnapshot, Sources
from app.sources.fakes import InMemoryFundamentalsSource


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


def _ctx(session, fundamentals):
    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None,
                      fundamentals=fundamentals)
    return StepContext(repo=PipelineRepo(session), sources=sources, run_id=1,
                       now=_now, llm=FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0)))


@pytest.mark.asyncio(loop_scope="session")
async def test_fundamentals_step_upserts(session):
    repo = PipelineRepo(session)
    from app.sources.base import StockMeta
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_now().date())
    await session.commit()

    src = InMemoryFundamentalsSource({"KO": [FundamentalsSnapshot(
        "2026Q1", 100.0, 2.0, 30.0, 20.0, 50.0, 80.0, 10.0)]})
    result = await FundamentalsStep().run(_ctx(session, src))
    await session.commit()

    assert result.ok_count == 1
    assert await repo.latest_fundamentals("KO") is not None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_fundamentals.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/pipeline/steps/fundamentals.py`:

```python
import asyncio
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.prices import _retry

logger = logging.getLogger(__name__)


class FundamentalsStep(Step):
    name = "fundamentals"
    is_critical = False

    def __init__(self, concurrency: int = 10, attempts: int = 3) -> None:
        self.concurrency = concurrency
        self.attempts = attempts

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult(ok_count=0)

        sem = asyncio.Semaphore(self.concurrency)

        async def fetch_one(ticker: str) -> tuple[str, str | None]:
            async with sem:
                try:
                    snaps = await _retry(
                        lambda: list(ctx.sources.fundamentals.fetch(ticker)),
                        attempts=self.attempts,
                    )
                    await ctx.repo.upsert_fundamentals(ticker, snaps)
                    return ticker, None
                except Exception as e:
                    logger.warning("fundamentals: %s failed: %s", ticker, e)
                    return ticker, str(e)

        results = await asyncio.gather(*(fetch_one(t) for t in tickers))
        failures = {t: e for t, e in results if e is not None}
        return StepResult(ok_count=len(results) - len(failures), per_ticker_failures=failures)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_fundamentals.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/fundamentals.py tests/pipeline/test_step_fundamentals.py
git commit -m "feat(backend): fundamentals ingestion step"
```

---

### Task 13: Screener step

**Files:** Create `backend/app/pipeline/steps/screener.py`; add repo helpers `ttm_dividends` and `consecutive_years_paid` to `repo.py`; Test `backend/tests/pipeline/test_step_screener.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_step_screener.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest

from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.screener import ScreenerStep
from app.sources.base import (
    DividendEvent, FundamentalsSnapshot, PriceBar, Sources, StockMeta,
)


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_screener_writes_rows_and_passes_quality_names(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_now().date())
    await repo.upsert_prices("KO", [PriceBar(date(2026, 6, 5), 60, 61, 59, 60, 60, 1000)])
    await repo.upsert_dividends("KO", [DividendEvent(date(2026, 3, 15), date(2026, 4, 1), 0.46)])
    await repo.upsert_fundamentals("KO", [FundamentalsSnapshot(
        "2026Q1", 100.0, 2.0, 30.0, 20.0, 50.0, 80.0, 10.0)])
    run_id = await repo.start_run(now=_now())
    await session.commit()

    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None,
                      fundamentals=None)
    ctx = StepContext(repo=repo, sources=sources, run_id=run_id, now=_now)
    result = await ScreenerStep().run(ctx)
    await session.commit()

    assert result.ok_count == 1
    screenings = await repo.get_screenings(run_id)
    assert len(screenings) == 1
    assert "ttm_yield" in screenings[0].signals
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_screener.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — first add two repo helpers to `backend/app/pipeline/repo.py` (after `latest_fundamentals`):

```python
    async def ttm_dividends(self, ticker: str, today: date) -> float:
        one_year_ago = (
            date(today.year - 1, today.month, today.day)
            if not (today.month == 2 and today.day == 29) else date(today.year - 1, 2, 28)
        )
        row = await self.session.execute(
            select(func.coalesce(func.sum(DividendHistory.amount_per_share), 0))
            .where(DividendHistory.ticker == ticker)
            .where(DividendHistory.ex_date >= one_year_ago)
        )
        return float(row.scalar() or 0.0)

    async def consecutive_years_paid(self, ticker: str) -> int:
        row = await self.session.execute(
            select(
                func.count(func.distinct(func.extract("year", DividendHistory.ex_date)))
            ).where(DividendHistory.ticker == ticker)
        )
        return int(row.scalar() or 0)

    async def latest_close(self, ticker: str) -> float | None:
        row = await self.session.execute(
            select(Price.close).where(Price.ticker == ticker)
            .order_by(Price.date.desc()).limit(1)
        )
        v = row.scalar()
        return float(v) if v is not None else None
```

Then create `backend/app/pipeline/steps/screener.py`:

```python
import logging

from app.analysis.screener import (
    ScreenerSignals,
    compute_debt_to_equity,
    compute_fcf_coverage,
    compute_payout_ratio,
    compute_quality_score,
    compute_ttm_yield,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

SCREENER_FINALIST_COUNT = 30
PASS_THRESHOLD = 50.0


class ScreenerStep(Step):
    name = "screener"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        tickers = await ctx.repo.list_active_tickers()
        if not tickers:
            return StepResult(ok_count=0)

        today = ctx.now().date()
        failures: dict[str, str] = {}
        ok = 0
        for ticker in tickers:
            try:
                price = await ctx.repo.latest_close(ticker)
                ttm = await ctx.repo.ttm_dividends(ticker, today)
                years = await ctx.repo.consecutive_years_paid(ticker)
                f = await ctx.repo.latest_fundamentals(ticker)

                def fv(x):
                    return float(x) if x is not None else None

                signals = ScreenerSignals(
                    ttm_yield=compute_ttm_yield(ttm, price),
                    payout_ratio=compute_payout_ratio(
                        fv(f.dividends_paid) if f else None, fv(f.net_income) if f else None),
                    fcf_coverage=compute_fcf_coverage(
                        fv(f.fcf) if f else None, fv(f.dividends_paid) if f else None),
                    debt_to_equity=compute_debt_to_equity(
                        fv(f.total_debt) if f else None, fv(f.total_equity) if f else None),
                    consecutive_years_paid=years,
                    earnings_growth_5y=None,  # requires 5y of fundamentals; filled in later
                )
                score = compute_quality_score(signals)
                await ctx.repo.insert_screening(
                    run_id=ctx.run_id, ticker=ticker, score=score,
                    signals={
                        "ttm_yield": signals.ttm_yield,
                        "payout_ratio": signals.payout_ratio,
                        "fcf_coverage": signals.fcf_coverage,
                        "debt_to_equity": signals.debt_to_equity,
                        "consecutive_years_paid": signals.consecutive_years_paid,
                    },
                    passed=score >= PASS_THRESHOLD, now=ctx.now(),
                )
                ok += 1
            except Exception as e:
                logger.warning("screener: %s failed: %s", ticker, e)
                failures[ticker] = str(e)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_screener.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/screener.py app/pipeline/repo.py tests/pipeline/test_step_screener.py
git commit -m "feat(backend): dividend screener step writes screenings"
```

---

### Task 14: Safety step (LLM)

**Files:** Create `backend/app/pipeline/steps/safety.py`; Test `backend/tests/pipeline/test_step_safety.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_step_safety.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import SafetyAssessment
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.safety import SafetyStep
from app.sources.base import Sources, StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


def _ctx(session, llm):
    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None,
                      fundamentals=None)
    return StepContext(repo=PipelineRepo(session), sources=sources, run_id=_RUN, now=_now, llm=llm)


_RUN = None


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_writes_scores_and_skips_bad(session):
    global _RUN
    repo = PipelineRepo(session)
    for t in ("KO", "BAD"):
        await repo.upsert_stocks([StockMeta(t, t, "S", "B")], today=_now().date())
    _RUN = await repo.start_run(now=_now())
    await repo.insert_screening(_RUN, "KO", 82.0, {"ttm_yield": 0.03}, True, _now())
    await repo.insert_screening(_RUN, "BAD", 70.0, {"ttm_yield": 0.05}, True, _now())
    await session.commit()

    llm = FakeLLMClient(
        by_key={"KO": SafetyAssessment(score=85, concerns=[], outlook="stable", reasoning="ok")},
        usage=LLMUsage(1000, 200, 0.006), raise_for={"BAD"},
    )
    result = await SafetyStep().run(_ctx(session, llm))
    await session.commit()

    assert result.ok_count == 1
    assert "BAD" in result.per_ticker_failures
    assert (await repo.latest_safety_score("KO")).score == 85
    run = await repo.get_run(_RUN)
    assert run.llm_tokens_used == 1200  # only KO succeeded
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_safety.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/pipeline/steps/safety.py`:

```python
import asyncio
import logging

from app.llm.prompts import SAFETY_PROMPT_VERSION, SAFETY_SYSTEM, build_safety_prompt
from app.llm.schemas import SafetyAssessment
from app.pipeline.steps.base import Step, StepContext, StepResult
from app.pipeline.steps.screener import SCREENER_FINALIST_COUNT

logger = logging.getLogger(__name__)


class SafetyStep(Step):
    name = "safety"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        finalists = await ctx.repo.top_screened_tickers(ctx.run_id, limit=SCREENER_FINALIST_COUNT)
        if not finalists:
            return StepResult(ok_count=0)

        failures: dict[str, str] = {}
        ok = 0
        for ticker in finalists:
            try:
                screening = next(
                    (s for s in await ctx.repo.get_screenings(ctx.run_id) if s.ticker == ticker), None)
                signals = screening.signals if screening else {}
                prompt = build_safety_prompt(
                    ticker=ticker, metrics=signals, recent_dividends=[], recent_news=[],
                    active_lessons=[],  # empty until Sub-project 5
                )
                assessment, usage = await asyncio.to_thread(
                    ctx.llm.complete_structured,
                    system=SAFETY_SYSTEM, prompt=prompt, schema=SafetyAssessment,
                    prompt_version=SAFETY_PROMPT_VERSION, key=ticker,
                )
                await ctx.repo.insert_safety_score(
                    ticker=ticker, score=assessment.score,
                    payout_ratio=signals.get("payout_ratio"),
                    fcf_coverage=signals.get("fcf_coverage"),
                    debt_to_equity=signals.get("debt_to_equity"),
                    consecutive_years_paid=signals.get("consecutive_years_paid"),
                    concerns=assessment.concerns, reasoning=assessment.reasoning,
                    model=ctx.llm.model if hasattr(ctx.llm, "model") else "fake",
                    prompt_version=SAFETY_PROMPT_VERSION, now=ctx.now(),
                )
                await ctx.repo.add_llm_usage(
                    ctx.run_id, tokens=usage.input_tokens + usage.output_tokens, cost=usage.cost_usd)
                ok += 1
            except Exception as e:
                logger.warning("safety: %s skipped: %s", ticker, e)
                failures[ticker] = str(e)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_safety.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/safety.py tests/pipeline/test_step_safety.py
git commit -m "feat(backend): dividend safety LLM step with cost tracking and skip-on-bad-output"
```

---

### Task 15: Options recommender step (dormant)

**Files:** Create `backend/app/pipeline/steps/options_recommender.py`; add repo helper `held_tickers()` returning `[]` (placeholder until Sub-project 4); Test `backend/tests/pipeline/test_step_options_recommender.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_step_options_recommender.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import CallPick
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.options_recommender import OptionsRecommenderStep
from app.sources.base import Sources


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_options_recommender_dormant_when_no_holdings(session):
    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=_now())
    await session.commit()
    llm = FakeLLMClient(by_key={}, usage=LLMUsage(0, 0, 0.0))
    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None)
    ctx = StepContext(repo=repo, sources=sources, run_id=run_id, now=_now, llm=llm)

    result = await OptionsRecommViaHelper(ctx)
    assert result.ok_count == 0
    recs = await repo.list_recommendations(status="pending", type_="sell_covered_call")
    assert recs == []


async def OptionsRecommViaHelper(ctx):
    return await OptionsRecommenderStep().run(ctx)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_options_recommender.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — add a placeholder repo helper to `backend/app/pipeline/repo.py` (after `list_active_tickers`):

```python
    async def held_tickers(self) -> list[str]:
        """No positions table until Sub-project 4. Returns [] so the options recommender
        and sell_position logic stay dormant but wired."""
        return []
```

create `backend/app/pipeline/steps/options_recommender.py`:

```python
import asyncio
import logging

from app.analysis.options_scoring import filter_otm_calls, score_call
from app.llm.prompts import OPTIONS_PROMPT_VERSION, OPTIONS_SYSTEM, build_options_prompt
from app.llm.schemas import CallPick
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)


class OptionsRecommenderStep(Step):
    name = "options_recommender"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        holdings = await ctx.repo.held_tickers()  # [] until Sub-project 4
        if not holdings:
            return StepResult(ok_count=0)

        failures: dict[str, str] = {}
        ok = 0
        for ticker in holdings:
            try:
                price = await ctx.repo.latest_close(ticker)
                rows = list(ctx.sources.options.fetch(ticker)) if ctx.sources.options else []
                candidates = filter_otm_calls(rows, price or 0.0)
                scored = sorted((score_call(c, price or 0.0) for c in candidates),
                                key=lambda s: s.score, reverse=True)[:5]
                if not scored:
                    continue
                payload = [
                    {"strike": s.candidate.strike, "premium": s.candidate.premium,
                     "premium_yield": s.premium_yield, "prob_assignment": s.prob_assignment,
                     "expiration_date": s.candidate.expiration_date}
                    for s in scored
                ]
                pick, usage = await asyncio.to_thread(
                    ctx.llm.complete_structured,
                    system=OPTIONS_SYSTEM,
                    prompt=build_options_prompt(ticker=ticker, price=price or 0.0, candidates=payload),
                    schema=CallPick, prompt_version=OPTIONS_PROMPT_VERSION, key=ticker,
                )
                await ctx.repo.insert_recommendation(
                    run_id=ctx.run_id, type="sell_covered_call", ticker=ticker, confidence="med",
                    payload={"strike": pick.strike, "expiration_date": str(pick.expiration_date),
                             "expected_premium": pick.expected_premium,
                             "prob_assignment": pick.prob_assignment},
                    reasoning=pick.reasoning, signals_snapshot={"candidates": payload},
                    model=getattr(ctx.llm, "model", "fake"),
                    prompt_version=OPTIONS_PROMPT_VERSION, now=ctx.now(),
                )
                await ctx.repo.add_llm_usage(
                    ctx.run_id, tokens=usage.input_tokens + usage.output_tokens, cost=usage.cost_usd)
                ok += 1
            except Exception as e:
                logger.warning("options_recommender: %s skipped: %s", ticker, e)
                failures[ticker] = str(e)
        return StepResult(ok_count=ok, per_ticker_failures=failures)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_options_recommender.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/options_recommender.py app/pipeline/repo.py tests/pipeline/test_step_options_recommender.py
git commit -m "feat(backend): options recommender LLM step (dormant until holdings exist)"
```

---

### Task 16: Recommender step

**Files:** Create `backend/app/pipeline/steps/recommender.py`; Test `backend/tests/pipeline/test_step_recommender.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_step_recommender.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest

from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.recommender import RecommenderStep
from app.sources.base import Sources, StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


def _now():
    return datetime(2026, 6, 8, tzinfo=UTC)


@pytest.mark.asyncio(loop_scope="session")
async def test_recommender_emits_add_position_for_safe_unheld(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_now().date())
    run_id = await repo.start_run(now=_now())
    await repo.insert_screening(run_id, "KO", 85.0, {"ttm_yield": 0.03}, True, _now())
    await repo.insert_safety_score("KO", 80, 0.5, 3.0, 0.4, 30, [], "solid",
                                   "claude-sonnet-4-6", "safety-v1", _now())
    await session.commit()

    sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None)
    ctx = StepContext(repo=repo, sources=sources, run_id=run_id, now=_now)
    result = await RecommenderStep().run(ctx)
    await session.commit()

    assert result.ok_count >= 1
    recs = await repo.list_recommendations(status="pending", type_="add_position")
    assert any(r.ticker == "KO" for r in recs)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_recommender.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/pipeline/steps/recommender.py`:

```python
import logging

from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

SAFETY_ADD_THRESHOLD = 70  # min safety score to recommend a new position


class RecommenderStep(Step):
    name = "recommender"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        held = set(await ctx.repo.held_tickers())  # empty until Sub-project 4
        finalists = await ctx.repo.top_screened_tickers(ctx.run_id, limit=30)
        screenings = {s.ticker: s for s in await ctx.repo.get_screenings(ctx.run_id)}

        ok = 0
        for ticker in finalists:
            if ticker in held:
                continue  # sell_position / sell_covered_call paths are dormant (Sub-project 4)
            safety = await ctx.repo.latest_safety_score(ticker)
            if safety is None or safety.score < SAFETY_ADD_THRESHOLD:
                continue
            screening = screenings.get(ticker)
            confidence = "high" if safety.score >= 85 else "med"
            await ctx.repo.insert_recommendation(
                run_id=ctx.run_id, type="add_position", ticker=ticker, confidence=confidence,
                payload={"target_shares": None, "target_price": "market",
                         "expected_yield": (screening.signals.get("ttm_yield") if screening else None)},
                reasoning=safety.llm_reasoning,
                signals_snapshot={
                    "quality_score": float(screening.dividend_quality_score) if screening else None,
                    "safety_score": safety.score,
                    "signals": screening.signals if screening else {},
                },
                model=safety.llm_model, prompt_version=safety.llm_prompt_version, now=ctx.now(),
            )
            ok += 1
        return StepResult(ok_count=ok)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_recommender.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/recommender.py tests/pipeline/test_step_recommender.py
git commit -m "feat(backend): recommender step emits add_position recs (sell paths dormant)"
```

---

### Task 17: Wire `default_steps()` ordering + screener-driven options watchlist

**Files:** Modify `backend/app/pipeline/steps/__init__.py`, `backend/app/pipeline/steps/options.py`; Test `backend/tests/pipeline/test_default_steps_order.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_default_steps_order.py`:

```python
from app.pipeline.steps import default_steps


def test_default_steps_order():
    names = [s.name for s in default_steps()]
    assert names == [
        "universe", "prices", "dividends", "fundamentals", "screener",
        "options", "news", "safety", "options_recommender", "recommender",
    ]
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_default_steps_order.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — rewrite `backend/app/pipeline/steps/__init__.py`:

```python
from app.pipeline.steps.base import Step, StepContext, StepFailure, StepResult
from app.pipeline.steps.dividends import DividendsStep
from app.pipeline.steps.fundamentals import FundamentalsStep
from app.pipeline.steps.news import NewsStep
from app.pipeline.steps.options import OptionsStep
from app.pipeline.steps.options_recommender import OptionsRecommenderStep
from app.pipeline.steps.prices import PricesStep
from app.pipeline.steps.recommender import RecommenderStep
from app.pipeline.steps.safety import SafetyStep
from app.pipeline.steps.screener import ScreenerStep
from app.pipeline.steps.universe import UniverseStep


def default_steps() -> list[Step]:
    return [
        UniverseStep(),
        PricesStep(),
        DividendsStep(),
        FundamentalsStep(),
        ScreenerStep(),
        OptionsStep(),
        NewsStep(),
        SafetyStep(),
        OptionsRecommenderStep(),
        RecommenderStep(),
    ]


__all__ = [
    "DividendsStep",
    "FundamentalsStep",
    "NewsStep",
    "OptionsRecommenderStep",
    "OptionsStep",
    "PricesStep",
    "RecommenderStep",
    "SafetyStep",
    "ScreenerStep",
    "Step",
    "StepContext",
    "StepFailure",
    "StepResult",
    "UniverseStep",
    "default_steps",
]
```

Then make the options step prefer the screener ranking. In `backend/app/pipeline/steps/options.py`, find where it builds the watchlist via `top_tickers_by_ttm_yield(...)` and replace that lookup with a screener-first version. Add this helper call at the top of `run` where the watchlist is resolved:

```python
        run_id = await ctx.repo.latest_screening_run_id()
        if run_id is not None:
            watchlist = await ctx.repo.top_screened_tickers(run_id, limit=self.watchlist_size)
        else:
            watchlist = await ctx.repo.top_tickers_by_ttm_yield(self.watchlist_size, ctx.now().date())
```

> If `OptionsStep` does not already have a `watchlist_size` attribute / `top_tickers_by_ttm_yield` call, read the file first and adapt: the rule is "use `top_screened_tickers(latest_screening_run_id)` when a screening run exists, else fall back to the existing yield-based call." Keep the union-with-holdings logic intact.

- [ ] **Step 4: Run — expect PASS** (and confirm the existing options step test still passes)

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_default_steps_order.py tests/pipeline/test_step_options.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/__init__.py app/pipeline/steps/options.py tests/pipeline/test_default_steps_order.py
git commit -m "feat(backend): wire analysis steps into default pipeline; screener-driven options watchlist"
```

---

### Task 18: Wire `llm` + `fundamentals` into production (main.py, pipeline.py)

**Files:** Modify `backend/app/api/pipeline.py`, `backend/app/main.py`; Test `backend/tests/test_llm_wiring.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_llm_wiring.py`:

```python
def test_make_llm_returns_client(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    from app.api.pipeline import _make_llm

    llm = _make_llm()
    assert llm.model == "claude-sonnet-4-6"


def test_make_sources_includes_fundamentals(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")

    from app.api.pipeline import _make_sources

    assert _make_sources().fundamentals is not None
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_llm_wiring.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — in `backend/app/api/pipeline.py`:

Add imports:

```python
from app.config import get_settings
from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.base import LLMClient
from app.sources.fundamentals_yfinance import YFinanceFundamentalsSource
```

Add an LLM override seam + factory next to `_sources_override`:

```python
_llm_override: LLMClient | None = None


def _make_llm() -> LLMClient:
    if _llm_override is not None:
        return _llm_override
    settings = get_settings()
    return AnthropicLLMClient(model=settings.llm_model, api_key=settings.anthropic_api_key)
```

Add `fundamentals=YFinanceFundamentalsSource()` to the `Sources(...)` constructed in `_make_sources()`.

In `_run_in_background`, pass the llm into the context:

```python
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=run_id, llm=_make_llm())
```

In `backend/app/main.py`, update `_scheduled_pipeline_job` to import and pass the llm:

```python
from app.api.pipeline import _make_llm, _make_sources, router as pipeline_router
```

(merge with the existing `_make_sources` import) and:

```python
        ctx = StepContext(
            repo=repo,
            sources=_make_sources(),
            run_id=0,
            now=lambda: datetime.now(tz=UTC),
            llm=_make_llm(),
        )
```

> `YFinanceFundamentalsSource` is created in Task 19. Implement Task 19 before running this task's test, or temporarily stub the import. Recommended: do Task 19 first, then Task 18. (They are split so the source has its own focused test.)

- [ ] **Step 4: Run — expect PASS** (after Task 19 exists)

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_llm_wiring.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/pipeline.py app/main.py tests/test_llm_wiring.py
git commit -m "feat(backend): wire AnthropicLLMClient and fundamentals source into pipeline"
```

---

### Task 19: Production `YFinanceFundamentalsSource`

**Files:** Create `backend/app/sources/fundamentals_yfinance.py`; Test `backend/tests/sources/test_fundamentals_yfinance.py`

> Do this task **before** Task 18 (Task 18 imports this class).

- [ ] **Step 1: Write the failing test** — create `backend/tests/sources/test_fundamentals_yfinance.py` (unit test with an injected fake yfinance Ticker; no network):

```python
import pandas as pd

from app.sources.fundamentals_yfinance import YFinanceFundamentalsSource


class _FakeTicker:
    def __init__(self, ticker):
        cols = [pd.Timestamp("2026-03-31")]
        self.quarterly_income_stmt = pd.DataFrame(
            {cols[0]: {"Total Revenue": 100.0, "Net Income": 20.0, "Diluted EPS": 2.0}}
        )
        self.quarterly_cashflow = pd.DataFrame(
            {cols[0]: {"Free Cash Flow": 30.0, "Cash Dividends Paid": -10.0}}
        )
        self.quarterly_balance_sheet = pd.DataFrame(
            {cols[0]: {"Total Debt": 50.0, "Stockholders Equity": 80.0}}
        )


def test_yf_fundamentals_normalizes():
    src = YFinanceFundamentalsSource(ticker_factory=_FakeTicker)
    snaps = list(src.fetch("KO"))
    assert len(snaps) == 1
    s = snaps[0]
    assert s.fiscal_period == "2026Q1"
    assert s.revenue == 100.0
    assert s.net_income == 20.0
    assert s.fcf == 30.0
    assert s.dividends_paid == 10.0  # absolute value
    assert s.total_debt == 50.0
    assert s.total_equity == 80.0
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/sources/test_fundamentals_yfinance.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/sources/fundamentals_yfinance.py`:

```python
from collections.abc import Callable, Iterable

import yfinance as yf

from app.sources.base import FundamentalsSnapshot


def _get(df, row_label, col):
    try:
        val = df.loc[row_label, col]
    except (KeyError, AttributeError):
        return None
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _fiscal_period(ts) -> str:
    q = (ts.month - 1) // 3 + 1
    return f"{ts.year}Q{q}"


class YFinanceFundamentalsSource:
    def __init__(self, ticker_factory: Callable[[str], object] = yf.Ticker) -> None:
        self._ticker_factory = ticker_factory

    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]:
        t = self._ticker_factory(ticker)
        income = getattr(t, "quarterly_income_stmt", None)
        cashflow = getattr(t, "quarterly_cashflow", None)
        balance = getattr(t, "quarterly_balance_sheet", None)
        if income is None or income.empty:
            return []

        out: list[FundamentalsSnapshot] = []
        for col in income.columns:
            divs = _get(cashflow, "Cash Dividends Paid", col)
            out.append(FundamentalsSnapshot(
                fiscal_period=_fiscal_period(col),
                revenue=_get(income, "Total Revenue", col),
                eps=_get(income, "Diluted EPS", col),
                fcf=_get(cashflow, "Free Cash Flow", col),
                net_income=_get(income, "Net Income", col),
                total_debt=_get(balance, "Total Debt", col),
                total_equity=_get(balance, "Stockholders Equity", col),
                dividends_paid=abs(divs) if divs is not None else None,
            ))
        return out
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/sources/test_fundamentals_yfinance.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/sources/fundamentals_yfinance.py tests/sources/test_fundamentals_yfinance.py
git commit -m "feat(backend): production yfinance fundamentals source"
```

---

### Task 20: Recommendations API

**Files:** Create `backend/app/api/recommendations.py`; register router in `backend/app/main.py`; Test `backend/tests/test_recommendations_api.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_recommendations_api.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.pipeline.repo import PipelineRepo
from app.sources.base import StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_list_get_approve_reject(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=datetime(2026, 6, 8).date())
    run_id = await repo.start_run(now=datetime(2026, 6, 8, tzinfo=UTC))
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_price": "market"}, reasoning="solid", signals_snapshot={"safety_score": 80},
        model="claude-sonnet-4-6", prompt_version="safety-v1", now=datetime(2026, 6, 8, tzinfo=UTC))
    rec2 = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="med",
        payload={}, reasoning="ok", signals_snapshot={}, model="m", prompt_version="v",
        now=datetime(2026, 6, 8, tzinfo=UTC))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/recommendations")
        assert r.status_code == 200
        assert any(item["id"] == rec_id for item in r.json())

        r = await client.get(f"/recommendations/{rec_id}")
        assert r.json()["reasoning"] == "solid"

        r = await client.post(f"/recommendations/{rec_id}/approve")
        assert r.status_code == 200 and r.json()["status"] == "approved"

        r = await client.post(f"/recommendations/{rec_id}/approve")
        assert r.status_code == 409  # already decided

        r = await client.post(f"/recommendations/{rec2}/reject", json={"reason": "too pricey"})
        assert r.status_code == 200 and r.json()["status"] == "rejected"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_recommendations_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/api/recommendations.py`:

```python
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/recommendations")


class RejectBody(BaseModel):
    reason: str | None = None


def _summary(r) -> dict:
    return {
        "id": r.id, "run_id": r.run_id, "type": r.type, "ticker": r.ticker,
        "confidence": r.confidence, "status": r.status,
        "created_at": r.created_at.isoformat(),
    }


def _full(r) -> dict:
    out = _summary(r)
    out.update({
        "payload": r.payload, "reasoning": r.reasoning,
        "signals_snapshot": r.signals_snapshot, "llm_model": r.llm_model,
        "llm_prompt_version": r.llm_prompt_version,
        "approval_mode": r.approval_mode, "decided_by": r.decided_by,
        "decided_at": r.decided_at.isoformat() if r.decided_at else None,
    })
    return out


@router.get("")
async def list_recommendations(status: str | None = "pending", type: str | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_recommendations(status=status, type_=type)
        return [_summary(r) for r in rows]


@router.get("/{rec_id}")
async def get_recommendation(rec_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rec = await repo.get_recommendation(rec_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="recommendation not found")
        return _full(rec)


@router.post("/{rec_id}/approve")
async def approve(rec_id: int) -> dict:
    return await _decide(rec_id, status="approved")


@router.post("/{rec_id}/reject")
async def reject(rec_id: int, body: RejectBody | None = None) -> dict:
    return await _decide(rec_id, status="rejected", reason=(body.reason if body else None))


async def _decide(rec_id: int, status: str, reason: str | None = None) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rec = await repo.get_recommendation(rec_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="recommendation not found")
        ok = await repo.set_recommendation_status(
            rec_id, status=status, decided_by="user", now=datetime.now(tz=UTC), reject_reason=reason)
        if not ok:
            raise HTTPException(status_code=409, detail=f"recommendation is not pending (status={rec.status})")
        await session.commit()
        updated = await repo.get_recommendation(rec_id)
        return _full(updated)
```

Register in `backend/app/main.py` — add import and `include_router`:

```python
from app.api.recommendations import router as recommendations_router
```

```python
    app.include_router(recommendations_router)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_recommendations_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/recommendations.py app/main.py tests/test_recommendations_api.py
git commit -m "feat(backend): recommendations API (list, detail, approve, reject)"
```

---

### Task 21: Stocks API (safety-score, screenings)

**Files:** Create `backend/app/api/stocks.py`; register router in `backend/app/main.py`; Test `backend/tests/test_stocks_api.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_stocks_api.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.pipeline.repo import PipelineRepo
from app.sources.base import StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    assert r.returncode == 0, r.stderr


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_score_and_screenings(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=datetime(2026, 6, 8).date())
    run_id = await repo.start_run(now=datetime(2026, 6, 8, tzinfo=UTC))
    await repo.insert_screening(run_id, "PG", 77.0, {"ttm_yield": 0.025}, True, datetime(2026, 6, 8, tzinfo=UTC))
    await repo.insert_safety_score("PG", 88, 0.55, 2.5, 0.5, 60, ["none"], "rock solid",
                                   "claude-sonnet-4-6", "safety-v1", datetime(2026, 6, 8, tzinfo=UTC))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/stocks/PG/safety-score")
        assert r.status_code == 200 and r.json()["score"] == 88

        r = await client.get("/stocks/NOPE/safety-score")
        assert r.status_code == 404

        r = await client.get(f"/screenings?run_id={run_id}")
        assert r.status_code == 200 and any(s["ticker"] == "PG" for s in r.json())
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_stocks_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement** — create `backend/app/api/stocks.py`:

```python
from fastapi import APIRouter, HTTPException

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter()


@router.get("/stocks/{ticker}/safety-score")
async def safety_score(ticker: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        s = await repo.latest_safety_score(ticker)
        if s is None:
            raise HTTPException(status_code=404, detail="no safety score for ticker")
        return {
            "ticker": s.ticker, "score": s.score,
            "payout_ratio": float(s.payout_ratio) if s.payout_ratio is not None else None,
            "fcf_coverage": float(s.fcf_coverage) if s.fcf_coverage is not None else None,
            "debt_to_equity": float(s.debt_to_equity) if s.debt_to_equity is not None else None,
            "consecutive_years_paid": s.consecutive_years_paid,
            "concerns": list(s.concerns or []),
            "reasoning": s.llm_reasoning, "llm_model": s.llm_model,
            "llm_prompt_version": s.llm_prompt_version, "scored_at": s.scored_at.isoformat(),
        }


@router.get("/screenings")
async def screenings(run_id: int | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        if run_id is None:
            run_id = await repo.latest_screening_run_id()
        if run_id is None:
            return []
        rows = await repo.get_screenings(run_id)
        return [
            {"ticker": r.ticker, "dividend_quality_score": float(r.dividend_quality_score),
             "passed_screen": r.passed_screen, "signals": r.signals,
             "created_at": r.created_at.isoformat()}
            for r in rows
        ]
```

Register in `backend/app/main.py`:

```python
from app.api.stocks import router as stocks_router
```

```python
    app.include_router(stocks_router)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_stocks_api.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/api/stocks.py app/main.py tests/test_stocks_api.py
git commit -m "feat(backend): stocks API for latest safety score and screenings"
```

---

### Task 22: Slow Anthropic integration smoke test

**Files:** Test `backend/tests/test_anthropic_integration.py`

- [ ] **Step 1: Write the test** (marked slow, skipped unless `ANTHROPIC_API_KEY` set) — create `backend/tests/test_anthropic_integration.py`:

```python
import os

import pytest

from app.llm.anthropic_client import AnthropicLLMClient
from app.llm.prompts import SAFETY_PROMPT_VERSION, SAFETY_SYSTEM, build_safety_prompt
from app.llm.schemas import SafetyAssessment


@pytest.mark.slow
@pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="no ANTHROPIC_API_KEY")
def test_real_safety_call_returns_valid_schema():
    client = AnthropicLLMClient(model="claude-sonnet-4-6", api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = build_safety_prompt(
        ticker="KO",
        metrics={"payout_ratio": 0.68, "fcf_coverage": 1.4, "debt_to_equity": 1.6},
        recent_dividends=["2026-03-15: 0.485"],
        recent_news=["Coca-Cola reports steady volume growth"],
        active_lessons=[],
    )
    assessment, usage = client.complete_structured(
        system=SAFETY_SYSTEM, prompt=prompt, schema=SafetyAssessment,
        prompt_version=SAFETY_PROMPT_VERSION, key="KO",
    )
    assert isinstance(assessment, SafetyAssessment)
    assert 0 <= assessment.score <= 100
    assert usage.input_tokens > 0
    assert usage.cost_usd > 0
```

- [ ] **Step 2: Verify it is skipped by default**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_anthropic_integration.py -v`
Expected: SKIPPED (no key) or deselected by `-m "not slow"`.

- [ ] **Step 3: (optional) Run live**

Run: `ANTHROPIC_API_KEY=sk-... TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -m slow tests/test_anthropic_integration.py -v`
Expected: PASS with a real call.

- [ ] **Step 4: Commit**

```bash
git add tests/test_anthropic_integration.py
git commit -m "test(backend): slow live Anthropic safety-call smoke test"
```

---

### Task 23: Full suite, lint, and CI slow-job parity

**Files:** Modify `.github/workflows/*` only if the slow job filter needs the new test; verify everything.

- [ ] **Step 1: Run the full default suite (slow deselected)**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -m "not slow" -q`
Expected: all pass.

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check .`
Expected: no errors. (Fix any import-order or unused-import findings, then re-run.)

- [ ] **Step 3: Confirm the nightly slow job picks up the new test.** Open the nightly workflow added in Sub-project 2 (the `ci: nightly job for slow yfinance integration tests` commit). It runs `pytest -m slow`. The new `test_anthropic_integration.py` is `@pytest.mark.slow` and self-skips without `ANTHROPIC_API_KEY`, so no workflow change is required unless you want to inject the key as a secret. If you do, add `ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}` to that job's `env`.

- [ ] **Step 4: Commit any workflow/lint fixes**

```bash
git add -A
git commit -m "chore(backend): lint clean + analysis sub-project test suite green"
```

---

## Self-Review

**Spec coverage check (spec §→ task):**
- §1.1 fundamentals table + ingestion → Tasks 2, 3, 4, 12, 19 ✓
- §1.2 screener + screenings → Tasks 5, 11, 13 ✓
- §1.3 safety analyst → Tasks 7, 8, 9, 14 ✓
- §1.4 options recommender (dormant) → Tasks 6, 15 ✓
- §1.5 recommender → Task 16 ✓
- §1.6 read/approve/reject HTTP → Tasks 20, 21 ✓
- §1.7 LLM cost tracking → Tasks 8, 11 (`add_llm_usage`), 14 ✓
- §3.3 LLM seam + prompt versioning → Tasks 7, 8, 9 ✓
- §4 pipeline ordering + screener-driven watchlist → Task 17 ✓
- §6 schema (4 tables) → Tasks 2, 3 ✓
- Key decision #4 (Sonnet 4.6, config-flippable) → Task 1 + Task 8 `_PRICING` includes Haiku ✓

**Type consistency:** `LLMClient.complete_structured(*, system, prompt, schema, prompt_version, key)` — same signature in protocol (Task 7), `FakeLLMClient` (Task 7), `AnthropicLLMClient` (Task 8), and both call sites (Tasks 14, 15). `LLMUsage(input_tokens, output_tokens, cost_usd)` consistent. Repo method names (`insert_screening`, `top_screened_tickers`, `latest_safety_score`, `insert_recommendation`, `set_recommendation_status`, `add_llm_usage`, `held_tickers`, `latest_close`, `ttm_dividends`) are defined once (Tasks 11/13/15) and referenced consistently in steps/APIs.

**Placeholder scan:** no "TBD"/"implement later"; every code step shows full code. The one "read the file and adapt" note (Task 17, options watchlist) gives an explicit rule because the exact current shape of `options.py`'s watchlist resolution must be matched in place — read it before editing.

**Ordering note:** Task 19 (yfinance fundamentals source) must be implemented before Task 18 (which imports it) — called out in both tasks.
