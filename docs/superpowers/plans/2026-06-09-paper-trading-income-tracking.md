# Paper Trading & Income Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the pipeline loop — approved recommendations become paper trades, positions and income are tracked, and the portfolio is queryable via REST.

**Architecture:** Four new ORM tables (`positions`, `trades`, `income_events`, `feedback`) with an Alembic migration. Two new pipeline steps (`ExecutorStep`, `IncomeTrackerStep`) follow the established `Step` ABC pattern. Pure analysis logic lives in `app/analysis/portfolio.py`. REST APIs follow the existing router-per-resource pattern and commit in `app/main.py`.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, pydantic-settings, pytest + testcontainers, httpx (ASGITransport).

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/app/models/portfolio.py` | Position, Trade, IncomeEvent, Feedback ORM models |
| Modify | `backend/app/models/__init__.py` | Register new models |
| Create | `backend/alembic/versions/0003_portfolio_tables.py` | DB migration |
| Create | `backend/app/analysis/portfolio.py` | Pure P&L / outcome functions |
| Modify | `backend/app/pipeline/repo.py` | ~15 new repo methods + `held_tickers` fix |
| Create | `backend/app/pipeline/steps/executor.py` | ExecutorStep |
| Create | `backend/app/pipeline/steps/income_tracker.py` | IncomeTrackerStep |
| Modify | `backend/app/pipeline/steps/__init__.py` | Add two steps + fix `held_tickers` |
| Create | `backend/app/api/portfolio.py` | Portfolio REST endpoints |
| Create | `backend/app/api/trades.py` | Trades & positions endpoints |
| Modify | `backend/app/main.py` | Register two new routers |
| Create | `backend/tests/test_migration_portfolio.py` | Migration smoke test |
| Create | `backend/tests/analysis/test_portfolio.py` | Pure function unit tests |
| Create | `backend/tests/pipeline/test_repo_portfolio.py` | Repo integration tests |
| Create | `backend/tests/pipeline/test_step_executor.py` | ExecutorStep integration tests |
| Create | `backend/tests/pipeline/test_step_income_tracker.py` | IncomeTrackerStep integration tests |
| Create | `backend/tests/test_portfolio_api.py` | Portfolio API tests |
| Create | `backend/tests/test_trades_api.py` | Trades & positions API tests |

---

### Task 0: ORM models (positions, trades, income_events, feedback)

**Files:**
- Create: `backend/app/models/portfolio.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_models_import.py` (add assertion to existing test)

- [ ] **Step 1: Write the failing test** — add one assertion to `backend/tests/test_models_import.py`:

```python
def test_new_models_registered():
    import app.models  # noqa: F401
    from app.models import Base

    tables = set(Base.metadata.tables)
    assert {"fundamentals", "screenings", "dividend_safety_scores", "recommendations"} <= tables
    assert {"positions", "trades", "income_events", "feedback"} <= tables  # add this line
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_models_import.py -v`
Expected: FAIL (`AssertionError` — tables not yet registered).

- [ ] **Step 3: Create `backend/app/models/portfolio.py`:**

```python
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class Position(Base):
    __tablename__ = "positions"
    __table_args__ = (
        CheckConstraint("kind IN ('stock', 'short_call')", name="ck_positions_kind"),
        CheckConstraint(
            "status IN ('open', 'closed', 'assigned', 'expired')",
            name="ck_positions_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    recommendation_id: Mapped[int] = mapped_column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    shares: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    strike: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    expiration_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="open")
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        CheckConstraint(
            "side IN ('buy', 'sell', 'sell_to_open', 'buy_to_close', 'assign', 'expire')",
            name="ck_trades_side",
        ),
        CheckConstraint(
            "reason IN ('recommendation', 'expiration', 'assignment', 'roll', 'manual_close')",
            name="ck_trades_reason",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    side: Mapped[str] = mapped_column(Text, nullable=False)
    shares_or_contracts: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)


class IncomeEvent(Base):
    __tablename__ = "income_events"
    __table_args__ = (
        CheckConstraint(
            "type IN ('dividend', 'call_premium', 'assignment_gain')",
            name="ck_income_events_type",
        ),
        UniqueConstraint(
            "ticker", "event_date", "type", "source_position_id",
            name="uq_income_events_dedup",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(Text, ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    source_position_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("positions.id", ondelete="RESTRICT"), nullable=True)
    source_recommendation_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"
    __table_args__ = (
        CheckConstraint("outcome IN ('win', 'loss', 'breakeven')", name="ck_feedback_outcome"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recommendation_id: Mapped[int] = mapped_column(Integer, ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False)
    position_id: Mapped[int] = mapped_column(Integer, ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    capital_pnl: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    dividends_received: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=Decimal(0))
    premiums_collected: Mapped[Decimal] = mapped_column(Numeric, nullable=False, default=Decimal(0))
    total_return_pct: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    held_days: Mapped[int] = mapped_column(Integer, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    exit_reason: Mapped[str] = mapped_column(Text, nullable=False)
    lessons: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

- [ ] **Step 4: Update `backend/app/models/__init__.py`** — add `portfolio` to the import block:

```python
from app.models import (  # noqa: E402, F401
    fundamentals,
    news,
    options,
    pipeline,
    portfolio,
    recommendation,
    safety,
    screening,
    stocks,
)
```

- [ ] **Step 5: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_models_import.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/portfolio.py app/models/__init__.py tests/test_models_import.py
git commit -m "feat(backend): ORM models for positions, trades, income_events, feedback"
```

---

### Task 1: Alembic migration `0003_portfolio_tables`

**Files:**
- Create: `backend/alembic/versions/0003_portfolio_tables.py`
- Test: `backend/tests/test_migration_portfolio.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/test_migration_portfolio.py`:

```python
import os
import subprocess
import sys

import pytest
from sqlalchemy import text


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
async def test_portfolio_tables_exist(session):
    for table in ("positions", "trades", "income_events", "feedback"):
        result = await session.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_name = :t"),
            {"t": table},
        )
        assert result.scalar() == 1, f"table {table!r} not found"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_portfolio.py -v`
Expected: FAIL (tables don't exist yet).

- [ ] **Step 3: Create `backend/alembic/versions/0003_portfolio_tables.py`:**

```python
"""portfolio tables: positions, trades, income_events, feedback

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "positions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("shares", sa.Numeric(), nullable=False),
        sa.Column("avg_entry_price", sa.Numeric(), nullable=False),
        sa.Column("strike", sa.Numeric(), nullable=True),
        sa.Column("expiration_date", sa.Date(), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="open"),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('stock', 'short_call')", name="ck_positions_kind"),
        sa.CheckConstraint("status IN ('open', 'closed', 'assigned', 'expired')", name="ck_positions_status"),
    )
    op.create_table(
        "trades",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("shares_or_contracts", sa.Numeric(), nullable=False),
        sa.Column("price", sa.Numeric(), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "side IN ('buy', 'sell', 'sell_to_open', 'buy_to_close', 'assign', 'expire')",
            name="ck_trades_side",
        ),
        sa.CheckConstraint(
            "reason IN ('recommendation', 'expiration', 'assignment', 'roll', 'manual_close')",
            name="ck_trades_reason",
        ),
    )
    op.create_table(
        "income_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("ticker", sa.Text(), sa.ForeignKey("stocks.ticker", ondelete="RESTRICT"), nullable=False),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(), nullable=False),
        sa.Column("event_date", sa.Date(), nullable=False),
        sa.Column("source_position_id", sa.Integer(), sa.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("source_recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('dividend', 'call_premium', 'assignment_gain')",
            name="ck_income_events_type",
        ),
        sa.UniqueConstraint(
            "ticker", "event_date", "type", "source_position_id",
            name="uq_income_events_dedup",
        ),
    )
    op.create_table(
        "feedback",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("recommendation_id", sa.Integer(), sa.ForeignKey("recommendations.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("position_id", sa.Integer(), sa.ForeignKey("positions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("entry_price", sa.Numeric(), nullable=False),
        sa.Column("exit_price", sa.Numeric(), nullable=True),
        sa.Column("capital_pnl", sa.Numeric(), nullable=False),
        sa.Column("dividends_received", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("premiums_collected", sa.Numeric(), nullable=False, server_default="0"),
        sa.Column("total_return_pct", sa.Numeric(), nullable=False),
        sa.Column("held_days", sa.Integer(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("exit_reason", sa.Text(), nullable=False),
        sa.Column("lessons", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("outcome IN ('win', 'loss', 'breakeven')", name="ck_feedback_outcome"),
    )


def downgrade() -> None:
    op.drop_table("feedback")
    op.drop_table("income_events")
    op.drop_table("trades")
    op.drop_table("positions")
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_portfolio.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/0003_portfolio_tables.py tests/test_migration_portfolio.py
git commit -m "feat(backend): alembic migration for portfolio tables"
```

---

### Task 2: Pure portfolio analysis functions

**Files:**
- Create: `backend/app/analysis/portfolio.py`
- Create: `backend/tests/analysis/test_portfolio.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/analysis/test_portfolio.py`:

```python
from decimal import Decimal

from app.analysis.portfolio import (
    classify_outcome,
    compute_assignment_gain,
    compute_capital_pnl,
    compute_covered_call_return_pct,
    compute_total_return_pct,
    is_call_itm,
)


def test_compute_capital_pnl():
    assert compute_capital_pnl(Decimal("50"), Decimal("60"), Decimal("100")) == Decimal("1000")
    assert compute_capital_pnl(Decimal("60"), Decimal("50"), Decimal("100")) == Decimal("-1000")


def test_compute_covered_call_return_pct():
    # $150 premium / $5000 cost basis = 3%
    assert compute_covered_call_return_pct(Decimal("150"), Decimal("5000")) == Decimal("0.03")


def test_compute_total_return_pct():
    pct = compute_total_return_pct(
        capital_pnl=Decimal("500"),
        dividends=Decimal("100"),
        premiums=Decimal("50"),
        cost_basis=Decimal("5000"),
    )
    assert pct == Decimal("0.13")  # 650 / 5000


def test_classify_outcome():
    assert classify_outcome(Decimal("0.05")) == "win"
    assert classify_outcome(Decimal("-0.02")) == "loss"
    assert classify_outcome(Decimal("0")) == "breakeven"


def test_is_call_itm():
    assert is_call_itm(Decimal("50"), Decimal("50")) is True   # at the money = ITM for assignment
    assert is_call_itm(Decimal("50"), Decimal("51")) is True
    assert is_call_itm(Decimal("50"), Decimal("49")) is False


def test_compute_assignment_gain():
    # strike $55, entry $50, 100 shares → $500 gain
    assert compute_assignment_gain(Decimal("55"), Decimal("50"), Decimal("100")) == Decimal("500")
    # strike below entry → 0
    assert compute_assignment_gain(Decimal("48"), Decimal("50"), Decimal("100")) == Decimal("0")
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/analysis/test_portfolio.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Create `backend/app/analysis/portfolio.py`:**

```python
from decimal import Decimal


def compute_capital_pnl(entry_price: Decimal, exit_price: Decimal, shares: Decimal) -> Decimal:
    return (exit_price - entry_price) * shares


def compute_covered_call_return_pct(premium_total: Decimal, cost_basis: Decimal) -> Decimal:
    """Return premium_total / cost_basis. cost_basis = avg_entry_price * shares of underlying."""
    if cost_basis == 0:
        return Decimal("0")
    return premium_total / cost_basis


def compute_total_return_pct(
    capital_pnl: Decimal, dividends: Decimal, premiums: Decimal, cost_basis: Decimal
) -> Decimal:
    if cost_basis == 0:
        return Decimal("0")
    return (capital_pnl + dividends + premiums) / cost_basis


def classify_outcome(total_return_pct: Decimal) -> str:
    if total_return_pct > 0:
        return "win"
    if total_return_pct < 0:
        return "loss"
    return "breakeven"


def is_call_itm(strike: Decimal, close_price: Decimal) -> bool:
    return close_price >= strike


def compute_assignment_gain(
    strike: Decimal, avg_entry_price: Decimal, shares: Decimal
) -> Decimal:
    gain = (strike - avg_entry_price) * shares
    return gain if gain > 0 else Decimal("0")
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/analysis/test_portfolio.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/analysis/portfolio.py tests/analysis/test_portfolio.py
git commit -m "feat(backend): pure portfolio P&L and outcome analysis functions"
```

---

### Task 3: PipelineRepo portfolio methods

**Files:**
- Modify: `backend/app/pipeline/repo.py`
- Create: `backend/tests/pipeline/test_repo_portfolio.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/pipeline/test_repo_portfolio.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

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
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


_now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
_today = _now.date()


@pytest.mark.asyncio(loop_scope="session")
async def test_position_lifecycle(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_shares": 10}, reasoning="test", signals_snapshot={},
        model="m", prompt_version="v", now=_now)

    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="KO", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("60.00"),
        strike=None, expiration_date=None, now=_now)
    assert pos_id > 0

    positions = await repo.list_open_positions(ticker="KO")
    assert len(positions) == 1 and positions[0].id == pos_id

    positions_by_kind = await repo.list_open_positions(kind="stock")
    assert any(p.id == pos_id for p in positions_by_kind)

    pos = await repo.get_position(pos_id)
    assert pos is not None and pos.status == "open"

    await repo.close_position(pos_id, "closed", _now)
    pos = await repo.get_position(pos_id)
    assert pos.status == "closed"
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_trade_insert_and_list(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("JNJ", "J&J", "HC", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="JNJ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="JNJ", kind="stock",
        shares=Decimal("5"), avg_entry_price=Decimal("150"),
        strike=None, expiration_date=None, now=_now)

    trade_id = await repo.insert_trade(
        position_id=pos_id, ticker="JNJ", side="buy",
        shares_or_contracts=Decimal("5"), price=Decimal("150"),
        reason="recommendation", now=_now)
    assert trade_id > 0

    trades = await repo.list_trades()
    assert any(t.id == trade_id for t in trades)
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_income_event_dedup(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="PG", kind="stock",
        shares=Decimal("20"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_now)

    ev_id = await repo.insert_income_event(
        ticker="PG", type_="dividend", amount=Decimal("48.20"),
        event_date=date(2026, 6, 1),
        source_position_id=pos_id, source_recommendation_id=None, now=_now)
    assert ev_id is not None

    # duplicate → None (ON CONFLICT DO NOTHING)
    dup_id = await repo.insert_income_event(
        ticker="PG", type_="dividend", amount=Decimal("48.20"),
        event_date=date(2026, 6, 1),
        source_position_id=pos_id, source_recommendation_id=None, now=_now)
    assert dup_id is None

    events = await repo.list_income_events()
    assert sum(1 for e in events if e.ticker == "PG") == 1
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_feedback_insert(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("MMM", "3M", "I", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="MMM", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="MMM", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("100"),
        strike=None, expiration_date=None, now=_now)

    fb_id = await repo.insert_feedback(
        rec_id=rec_id, position_id=pos_id,
        entry_price=Decimal("100"), exit_price=Decimal("110"),
        capital_pnl=Decimal("100"), dividends_received=Decimal("0"),
        premiums_collected=Decimal("0"), total_return_pct=Decimal("0.10"),
        held_days=30, outcome="win", exit_reason="recommendation", now=_now)
    assert fb_id > 0
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_approved_unexecuted_recs_and_mark_executed(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("VZ", "Verizon", "T", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="VZ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(rec_id, "approved", "user", _now)

    recs = await repo.approved_unexecuted_recs()
    assert any(r.id == rec_id for r in recs)

    await repo.mark_rec_executed(rec_id)
    recs_after = await repo.approved_unexecuted_recs()
    assert not any(r.id == rec_id for r in recs_after)
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_open_calls_expiring_on(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("T", "AT&T", "T", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="T", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(
        rec_id=rec_id, ticker="T", kind="short_call",
        shares=Decimal("1"), avg_entry_price=Decimal("0.50"),
        strike=Decimal("20"), expiration_date=_today,
        now=_now)

    calls = await repo.open_calls_expiring_on(_today)
    assert any(p.ticker == "T" and p.expiration_date == _today for p in calls)
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_dividends_since_excludes_open_date(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("O", "Realty", "RE", "B")], today=_today)
    from app.models.stocks import DividendHistory as DH
    session.add(DH(ticker="O", ex_date=_today, pay_date=None,
                   amount_per_share=Decimal("0.257"), frequency="monthly"))
    await session.flush()

    divs = await repo.dividends_since("O", _today)
    assert divs == []  # ex_date == since_date is excluded (strict >)

    divs2 = await repo.dividends_since("O", date(2026, 6, 8))
    assert len(divs2) == 1
    await session.commit()
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo_portfolio.py -v`
Expected: FAIL (methods not defined on PipelineRepo).

- [ ] **Step 3: Add methods to `backend/app/pipeline/repo.py`**

Add at the top of the file, to the existing model imports:
```python
from app.models.portfolio import Feedback, IncomeEvent, Position, Trade
```

Then add the following methods at the end of the `PipelineRepo` class, before the `# ----- LLM cost bookkeeping -----` section (or at the end):

```python
    # ----- positions -----

    async def open_position(self, rec_id: int, ticker: str, kind: str, shares: Decimal,
                            avg_entry_price: Decimal, strike: Decimal | None,
                            expiration_date: date | None, now: datetime) -> int:
        pos = Position(
            recommendation_id=rec_id, ticker=ticker, kind=kind, shares=shares,
            avg_entry_price=avg_entry_price, strike=strike, expiration_date=expiration_date,
            opened_at=now, status="open",
        )
        self.session.add(pos)
        await self.session.flush()
        return pos.id

    async def close_position(self, position_id: int, status: str, now: datetime) -> None:
        pos = await self.session.get(Position, position_id)
        if pos is not None:
            pos.status = status
            pos.closed_at = now
            await self.session.flush()

    async def list_open_positions(self, ticker: str | None = None,
                                   kind: str | None = None) -> list[Position]:
        stmt = select(Position).where(Position.status == "open")
        if ticker is not None:
            stmt = stmt.where(Position.ticker == ticker)
        if kind is not None:
            stmt = stmt.where(Position.kind == kind)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def get_position(self, position_id: int) -> Position | None:
        return await self.session.get(Position, position_id)

    # ----- trades -----

    async def insert_trade(self, position_id: int, ticker: str, side: str,
                           shares_or_contracts: Decimal, price: Decimal,
                           reason: str, now: datetime) -> int:
        trade = Trade(
            position_id=position_id, ticker=ticker, side=side,
            shares_or_contracts=shares_or_contracts, price=price,
            reason=reason, executed_at=now,
        )
        self.session.add(trade)
        await self.session.flush()
        return trade.id

    async def list_trades(self, from_: date | None = None, to: date | None = None) -> list[Trade]:
        stmt = select(Trade).order_by(Trade.executed_at.desc())
        if from_ is not None:
            stmt = stmt.where(Trade.executed_at >= from_)
        if to is not None:
            stmt = stmt.where(Trade.executed_at <= to)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    # ----- income events -----

    async def insert_income_event(self, ticker: str, type_: str, amount: Decimal,
                                   event_date: date, source_position_id: int | None,
                                   source_recommendation_id: int | None,
                                   now: datetime) -> int | None:
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        stmt = pg_insert(IncomeEvent).values(
            ticker=ticker, type=type_, amount=amount, event_date=event_date,
            source_position_id=source_position_id,
            source_recommendation_id=source_recommendation_id,
            created_at=now,
        ).on_conflict_do_nothing(constraint="uq_income_events_dedup").returning(IncomeEvent.id)
        result = await self.session.execute(stmt)
        row = result.scalar()
        return row  # None if conflict

    async def list_income_events(self, from_: date | None = None,
                                  to: date | None = None) -> list[IncomeEvent]:
        stmt = select(IncomeEvent).order_by(IncomeEvent.event_date.desc())
        if from_ is not None:
            stmt = stmt.where(IncomeEvent.event_date >= from_)
        if to is not None:
            stmt = stmt.where(IncomeEvent.event_date <= to)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    # ----- feedback -----

    async def insert_feedback(self, rec_id: int, position_id: int, entry_price: Decimal,
                               exit_price: Decimal | None, capital_pnl: Decimal,
                               dividends_received: Decimal, premiums_collected: Decimal,
                               total_return_pct: Decimal, held_days: int,
                               outcome: str, exit_reason: str, now: datetime) -> int:
        fb = Feedback(
            recommendation_id=rec_id, position_id=position_id,
            entry_price=entry_price, exit_price=exit_price, capital_pnl=capital_pnl,
            dividends_received=dividends_received, premiums_collected=premiums_collected,
            total_return_pct=total_return_pct, held_days=held_days,
            outcome=outcome, exit_reason=exit_reason, created_at=now,
        )
        self.session.add(fb)
        await self.session.flush()
        return fb.id

    # ----- executor helpers -----

    async def approved_unexecuted_recs(self) -> list[Recommendation]:
        rows = await self.session.execute(
            select(Recommendation).where(Recommendation.status == "approved")
        )
        return list(rows.scalars().all())

    async def mark_rec_executed(self, rec_id: int) -> None:
        rec = await self.session.get(Recommendation, rec_id)
        if rec is not None:
            rec.status = "executed"
            await self.session.flush()

    # ----- income tracker helpers -----

    async def open_calls_expiring_on(self, expiry_date: date) -> list[Position]:
        rows = await self.session.execute(
            select(Position).where(
                Position.status == "open",
                Position.kind == "short_call",
                Position.expiration_date == expiry_date,
            )
        )
        return list(rows.scalars().all())

    async def dividends_since(self, ticker: str, since_date: date) -> list[DividendHistory]:
        rows = await self.session.execute(
            select(DividendHistory).where(
                DividendHistory.ticker == ticker,
                DividendHistory.ex_date > since_date,  # strict > : must own BEFORE ex-date
            ).order_by(DividendHistory.ex_date)
        )
        return list(rows.scalars().all())
```

You also need to add `Decimal` and `date` to the imports at the top of `repo.py` if they're not already there. Check: `from decimal import Decimal` and `from datetime import UTC, date, datetime`. Also add `from sqlalchemy import select` if not present (it's already used throughout the file).

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo_portfolio.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/repo.py tests/pipeline/test_repo_portfolio.py
git commit -m "feat(backend): repo CRUD for positions, trades, income events, feedback"
```

---

### Task 4: ExecutorStep

**Files:**
- Create: `backend/app/pipeline/steps/executor.py`
- Create: `backend/tests/pipeline/test_step_executor.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/pipeline/test_step_executor.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.executor import ExecutorStep
from app.sources.base import Sources, StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


_now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
_today = _now.date()
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id):
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: _now)


@pytest.mark.asyncio(loop_scope="session")
async def test_executor_add_position(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    from app.models.stocks import Price
    from datetime import date
    session.add(Price(ticker="KO", date=_today, open=Decimal("60"), high=Decimal("61"),
                      low=Decimal("59"), close=Decimal("60.50"), adj_close=Decimal("60.50"), volume=1000000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={"target_shares": 5}, reasoning="r", signals_snapshot={},
        model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(rec_id, "approved", "user", _now)
    await session.commit()

    result = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()

    assert result.ok_count >= 1
    positions = await repo.list_open_positions(ticker="KO")
    assert len(positions) == 1
    assert positions[0].shares == Decimal("5")
    rec = await repo.get_recommendation(rec_id)
    assert rec.status == "executed"

    # idempotency: re-run does not open a second position
    result2 = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()
    assert len(await repo.list_open_positions(ticker="KO")) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_executor_sell_covered_call(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("JNJ", "J&J", "HC", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="JNJ", confidence="high",
        payload={"strike": "155", "expiration_date": "2026-07-18", "expected_premium": "1.50"},
        reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(rec_id, "approved", "user", _now)
    await session.commit()

    result = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()

    assert result.ok_count >= 1
    calls = await repo.list_open_positions(ticker="JNJ", kind="short_call")
    assert len(calls) == 1 and calls[0].strike == Decimal("155")
    events = await repo.list_income_events()
    assert any(e.ticker == "JNJ" and e.type == "call_premium" for e in events)


@pytest.mark.asyncio(loop_scope="session")
async def test_executor_sell_position(session):
    from datetime import date
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    from app.models.stocks import Price
    session.add(Price(ticker="PG", date=_today, open=Decimal("170"), high=Decimal("172"),
                      low=Decimal("169"), close=Decimal("171"), adj_close=Decimal("171"), volume=500000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    add_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=add_rec_id, ticker="PG", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_now)

    sell_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_position", ticker="PG", confidence="high",
        payload={"position_id": pos_id}, reasoning="deteriorating", signals_snapshot={},
        model="m", prompt_version="v", now=_now)
    await repo.set_recommendation_status(sell_rec_id, "approved", "user", _now)
    await session.commit()

    result = await ExecutorStep().run(_ctx(repo, run_id))
    await session.commit()

    assert result.ok_count >= 1
    pos = await repo.get_position(pos_id)
    assert pos.status == "closed"
    rec = await repo.get_recommendation(sell_rec_id)
    assert rec.status == "executed"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_executor.py -v`
Expected: FAIL.

- [ ] **Step 3: Create `backend/app/pipeline/steps/executor.py`:**

```python
import logging
from datetime import date
from decimal import Decimal

from app.analysis.portfolio import (
    classify_outcome,
    compute_capital_pnl,
    compute_total_return_pct,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)


class ExecutorStep(Step):
    name = "executor"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        recs = await ctx.repo.approved_unexecuted_recs()
        ok, failures = 0, []
        today = ctx.now().date()

        for rec in recs:
            try:
                if rec.type == "add_position":
                    await self._execute_add(ctx, rec, today)
                elif rec.type == "sell_covered_call":
                    await self._execute_sell_call(ctx, rec, today)
                elif rec.type == "sell_position":
                    await self._execute_sell_position(ctx, rec, today)
                else:
                    logger.info("executor: skipping unimplemented rec type %s", rec.type)
                    continue
                ok += 1
            except Exception as exc:
                logger.warning("executor: failed %s %s: %s", rec.type, rec.ticker, exc)
                failures.append((rec.ticker, str(exc)))

        return StepResult(ok_count=ok, per_ticker_failures=failures)

    async def _execute_add(self, ctx: StepContext, rec, today: date) -> None:
        price = await ctx.repo.latest_close(rec.ticker)
        if price is None:
            raise ValueError(f"no close price for {rec.ticker}")
        payload = rec.payload or {}
        shares = Decimal(str(payload.get("target_shares", 10)))
        price_dec = Decimal(str(price))

        position_id = await ctx.repo.open_position(
            rec_id=rec.id, ticker=rec.ticker, kind="stock",
            shares=shares, avg_entry_price=price_dec,
            strike=None, expiration_date=None, now=ctx.now(),
        )
        await ctx.repo.insert_trade(
            position_id=position_id, ticker=rec.ticker, side="buy",
            shares_or_contracts=shares, price=price_dec,
            reason="recommendation", now=ctx.now(),
        )
        await ctx.repo.mark_rec_executed(rec.id)

    async def _execute_sell_call(self, ctx: StepContext, rec, today: date) -> None:
        payload = rec.payload or {}
        premium = Decimal(str(payload.get("expected_premium", "0")))
        strike = Decimal(str(payload["strike"]))
        expiration = date.fromisoformat(str(payload["expiration_date"]))

        position_id = await ctx.repo.open_position(
            rec_id=rec.id, ticker=rec.ticker, kind="short_call",
            shares=Decimal("1"), avg_entry_price=premium,
            strike=strike, expiration_date=expiration, now=ctx.now(),
        )
        await ctx.repo.insert_trade(
            position_id=position_id, ticker=rec.ticker, side="sell_to_open",
            shares_or_contracts=Decimal("1"), price=premium,
            reason="recommendation", now=ctx.now(),
        )
        await ctx.repo.insert_income_event(
            ticker=rec.ticker, type_="call_premium",
            amount=premium * 100,  # 1 contract = 100 shares
            event_date=today,
            source_position_id=position_id,
            source_recommendation_id=rec.id,
            now=ctx.now(),
        )
        await ctx.repo.mark_rec_executed(rec.id)

    async def _execute_sell_position(self, ctx: StepContext, rec, today: date) -> None:
        payload = rec.payload or {}
        position_id = payload.get("position_id")
        if position_id is None:
            raise ValueError(f"sell_position rec {rec.id} missing payload.position_id")

        pos = await ctx.repo.get_position(int(position_id))
        if pos is None or pos.status != "open":
            raise ValueError(f"position {position_id} not found or not open")

        price = await ctx.repo.latest_close(rec.ticker)
        if price is None:
            raise ValueError(f"no close price for {rec.ticker}")
        price_dec = Decimal(str(price))

        capital_pnl = compute_capital_pnl(pos.avg_entry_price, price_dec, pos.shares)
        cost_basis = pos.avg_entry_price * pos.shares
        total_return_pct = compute_total_return_pct(capital_pnl, Decimal(0), Decimal(0), cost_basis)
        held_days = (today - pos.opened_at.date()).days
        outcome = classify_outcome(total_return_pct)

        await ctx.repo.insert_trade(
            position_id=pos.id, ticker=rec.ticker, side="sell",
            shares_or_contracts=pos.shares, price=price_dec,
            reason="recommendation", now=ctx.now(),
        )
        await ctx.repo.close_position(pos.id, "closed", ctx.now())
        await ctx.repo.insert_feedback(
            rec_id=rec.id, position_id=pos.id,
            entry_price=pos.avg_entry_price, exit_price=price_dec,
            capital_pnl=capital_pnl, dividends_received=Decimal(0),
            premiums_collected=Decimal(0), total_return_pct=total_return_pct,
            held_days=held_days, outcome=outcome, exit_reason="recommendation",
            now=ctx.now(),
        )
        await ctx.repo.mark_rec_executed(rec.id)
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_executor.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/executor.py tests/pipeline/test_step_executor.py
git commit -m "feat(backend): executor step — approved recs become paper trades"
```

---

### Task 5: IncomeTrackerStep

**Files:**
- Create: `backend/app/pipeline/steps/income_tracker.py`
- Create: `backend/tests/pipeline/test_step_income_tracker.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/pipeline/test_step_income_tracker.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.stocks import DividendHistory as DH
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.income_tracker import IncomeTrackerStep
from app.sources.base import Sources, StockMeta


@pytest.fixture(scope="module", autouse=True)
def _migrate(pg_container):
    env = {**os.environ,
           "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
           "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
           "POSTGRES_PORT": str(pg_container.get_exposed_port(5432))}
    r = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                       capture_output=True, text=True, env=env,
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


_open_date = datetime(2026, 6, 1, 17, 0, tzinfo=UTC)
_ex_date = date(2026, 6, 5)  # strictly after open date
_now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
_today = _now.date()
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id, now=None):
    t = now or _now
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: t)


@pytest.mark.asyncio(loop_scope="session")
async def test_income_tracker_books_dividend(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    session.add(DH(ticker="KO", ex_date=_ex_date, pay_date=None,
                   amount_per_share=Decimal("0.485"), frequency="quarterly"))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    await repo.open_position(
        rec_id=rec_id, ticker="KO", kind="stock",
        shares=Decimal("100"), avg_entry_price=Decimal("60"),
        strike=None, expiration_date=None, now=_open_date)
    await session.commit()

    result = await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()

    events = await repo.list_income_events()
    div_events = [e for e in events if e.ticker == "KO" and e.type == "dividend"]
    assert len(div_events) == 1
    assert div_events[0].amount == Decimal("48.50")  # 0.485 * 100

    # idempotency: run again, no duplicate
    await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()
    events2 = await repo.list_income_events()
    assert len([e for e in events2 if e.ticker == "KO" and e.type == "dividend"]) == 1


@pytest.mark.asyncio(loop_scope="session")
async def test_income_tracker_otm_call_expiry(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("JNJ", "J&J", "HC", "B")], today=_today)
    from app.models.stocks import Price
    session.add(Price(ticker="JNJ", date=_today, open=Decimal("150"), high=Decimal("152"),
                      low=Decimal("149"), close=Decimal("151"), adj_close=Decimal("151"), volume=100000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="JNJ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="JNJ", kind="short_call",
        shares=Decimal("1"), avg_entry_price=Decimal("1.50"),
        strike=Decimal("160"), expiration_date=_today,  # OTM: close=151 < strike=160
        now=_open_date)
    # Also open underlying stock position (for cost basis in feedback)
    stock_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="JNJ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    await repo.open_position(
        rec_id=stock_rec_id, ticker="JNJ", kind="stock",
        shares=Decimal("100"), avg_entry_price=Decimal("148"),
        strike=None, expiration_date=None, now=_open_date)
    await session.commit()

    result = await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()

    pos = await repo.get_position(pos_id)
    assert pos.status == "expired"
    trades = await repo.list_trades()
    assert any(t.position_id == pos_id and t.side == "expire" for t in trades)


@pytest.mark.asyncio(loop_scope="session")
async def test_income_tracker_itm_call_assignment(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    from app.models.stocks import Price
    session.add(Price(ticker="PG", date=_today, open=Decimal("170"), high=Decimal("172"),
                      low=Decimal("169"), close=Decimal("171"), adj_close=Decimal("171"), volume=200000))
    await session.flush()
    run_id = await repo.start_run(now=_now)
    stock_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    stock_pos_id = await repo.open_position(
        rec_id=stock_rec_id, ticker="PG", kind="stock",
        shares=Decimal("100"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_open_date)
    call_rec_id = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_open_date)
    call_pos_id = await repo.open_position(
        rec_id=call_rec_id, ticker="PG", kind="short_call",
        shares=Decimal("1"), avg_entry_price=Decimal("2.00"),
        strike=Decimal("165"), expiration_date=_today,  # ITM: close=171 >= strike=165
        now=_open_date)
    await session.commit()

    await IncomeTrackerStep().run(_ctx(repo, run_id))
    await session.commit()

    call_pos = await repo.get_position(call_pos_id)
    assert call_pos.status == "assigned"
    stock_pos = await repo.get_position(stock_pos_id)
    assert stock_pos.status == "assigned"
    events = await repo.list_income_events()
    # assignment_gain: (165 - 160) * 100 = 500
    assert any(e.ticker == "PG" and e.type == "assignment_gain" and e.amount == Decimal("500") for e in events)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_income_tracker.py -v`
Expected: FAIL.

- [ ] **Step 3: Create `backend/app/pipeline/steps/income_tracker.py`:**

```python
import logging
from datetime import date
from decimal import Decimal

from app.analysis.portfolio import (
    classify_outcome,
    compute_assignment_gain,
    compute_capital_pnl,
    compute_covered_call_return_pct,
    compute_total_return_pct,
    is_call_itm,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)


class IncomeTrackerStep(Step):
    name = "income_tracker"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        ok, failures = 0, []
        today = ctx.now().date()

        # 1. Dividend tracking for open stock positions
        stock_positions = await ctx.repo.list_open_positions(kind="stock")
        for pos in stock_positions:
            try:
                await self._track_dividends(ctx, pos, today)
                ok += 1
            except Exception as exc:
                logger.warning("income_tracker: dividend %s: %s", pos.ticker, exc)
                failures.append((pos.ticker, str(exc)))

        # 2. Call expiry / assignment
        expiring_calls = await ctx.repo.open_calls_expiring_on(today)
        for pos in expiring_calls:
            try:
                await self._settle_call(ctx, pos, today)
                ok += 1
            except Exception as exc:
                logger.warning("income_tracker: call settle %s: %s", pos.ticker, exc)
                failures.append((pos.ticker, str(exc)))

        return StepResult(ok_count=ok, per_ticker_failures=failures)

    async def _track_dividends(self, ctx: StepContext, pos, today: date) -> None:
        dividends = await ctx.repo.dividends_since(pos.ticker, pos.opened_at.date())
        for div in dividends:
            if div.ex_date > today:
                continue
            amount = div.amount_per_share * pos.shares
            await ctx.repo.insert_income_event(
                ticker=pos.ticker, type_="dividend",
                amount=amount, event_date=div.ex_date,
                source_position_id=pos.id,
                source_recommendation_id=None,
                now=ctx.now(),
            )

    async def _settle_call(self, ctx: StepContext, pos, today: date) -> None:
        close = await ctx.repo.latest_close(pos.ticker)
        if close is None:
            raise ValueError(f"no close price for {pos.ticker}")
        close_dec = Decimal(str(close))

        if is_call_itm(pos.strike, close_dec):
            await self._handle_assignment(ctx, pos, close_dec, today)
        else:
            await self._handle_otm_expiry(ctx, pos, today)

    async def _handle_otm_expiry(self, ctx: StepContext, pos, today: date) -> None:
        # Call expired worthless — premium already booked at open
        await ctx.repo.insert_trade(
            position_id=pos.id, ticker=pos.ticker, side="expire",
            shares_or_contracts=pos.shares, price=Decimal("0"),
            reason="expiration", now=ctx.now(),
        )
        await ctx.repo.close_position(pos.id, "expired", ctx.now())

        # Find underlying stock position for cost basis (best effort)
        stock_positions = await ctx.repo.list_open_positions(ticker=pos.ticker, kind="stock")
        premium_total = pos.avg_entry_price * 100
        if stock_positions:
            sp = stock_positions[0]
            cost_basis = sp.avg_entry_price * sp.shares
            total_return_pct = compute_covered_call_return_pct(premium_total, cost_basis)
        else:
            total_return_pct = Decimal("0")

        await ctx.repo.insert_feedback(
            rec_id=pos.recommendation_id, position_id=pos.id,
            entry_price=pos.avg_entry_price, exit_price=Decimal("0"),
            capital_pnl=Decimal("0"), dividends_received=Decimal("0"),
            premiums_collected=premium_total,
            total_return_pct=total_return_pct,
            held_days=(today - pos.opened_at.date()).days,
            outcome="win",  # premium kept, shares retained
            exit_reason="expiration", now=ctx.now(),
        )

    async def _handle_assignment(self, ctx: StepContext, pos, close_dec: Decimal, today: date) -> None:
        # Call ITM — shares assigned at strike
        await ctx.repo.insert_trade(
            position_id=pos.id, ticker=pos.ticker, side="assign",
            shares_or_contracts=pos.shares * 100,
            price=pos.strike, reason="assignment", now=ctx.now(),
        )
        await ctx.repo.close_position(pos.id, "assigned", ctx.now())

        stock_positions = await ctx.repo.list_open_positions(ticker=pos.ticker, kind="stock")
        if stock_positions:
            sp = stock_positions[0]
            await ctx.repo.close_position(sp.id, "assigned", ctx.now())

            assignment_gain = compute_assignment_gain(pos.strike, sp.avg_entry_price, sp.shares)
            if assignment_gain > 0:
                await ctx.repo.insert_income_event(
                    ticker=pos.ticker, type_="assignment_gain",
                    amount=assignment_gain, event_date=today,
                    source_position_id=sp.id, source_recommendation_id=None,
                    now=ctx.now(),
                )

            capital_pnl = compute_capital_pnl(sp.avg_entry_price, pos.strike, sp.shares)
            premium_total = pos.avg_entry_price * 100
            cost_basis = sp.avg_entry_price * sp.shares
            total_return_pct = compute_total_return_pct(capital_pnl, Decimal(0), premium_total, cost_basis)
            outcome = classify_outcome(total_return_pct)

            await ctx.repo.insert_feedback(
                rec_id=sp.recommendation_id, position_id=sp.id,
                entry_price=sp.avg_entry_price, exit_price=pos.strike,
                capital_pnl=capital_pnl, dividends_received=Decimal(0),
                premiums_collected=premium_total,
                total_return_pct=total_return_pct,
                held_days=(today - sp.opened_at.date()).days,
                outcome=outcome, exit_reason="assignment", now=ctx.now(),
            )
```

- [ ] **Step 4: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_income_tracker.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add app/pipeline/steps/income_tracker.py tests/pipeline/test_step_income_tracker.py
git commit -m "feat(backend): income tracker step — dividends, call expiry, assignment"
```

---

### Task 6: Wire steps into default pipeline + activate `held_tickers`

**Files:**
- Modify: `backend/app/pipeline/steps/__init__.py`
- Modify: `backend/app/pipeline/repo.py` (update `held_tickers`)
- Create: `backend/tests/pipeline/test_default_steps_portfolio.py`

- [ ] **Step 1: Write the failing test** — create `backend/tests/pipeline/test_default_steps_portfolio.py`:

```python
from app.pipeline.steps import default_steps
from app.pipeline.steps.executor import ExecutorStep
from app.pipeline.steps.income_tracker import IncomeTrackerStep


def test_default_steps_include_executor_and_income_tracker():
    steps = default_steps()
    names = [s.name for s in steps]
    assert "executor" in names
    assert "income_tracker" in names
    # executor comes after recommender
    assert names.index("executor") > names.index("recommender")
    # income_tracker comes after executor
    assert names.index("income_tracker") > names.index("executor")
    # last two steps are executor, income_tracker
    assert isinstance(steps[-2], ExecutorStep)
    assert isinstance(steps[-1], IncomeTrackerStep)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_default_steps_portfolio.py -v`
Expected: FAIL.

- [ ] **Step 3: Update `backend/app/pipeline/steps/__init__.py`** — add imports and append to `default_steps()`:

The current `default_steps()` returns a list ending with `OptionsRecommenderStep(), RecommenderStep()`. Add the two new steps:

```python
from app.pipeline.steps.executor import ExecutorStep
from app.pipeline.steps.income_tracker import IncomeTrackerStep
```

And in `default_steps()`, change the last two lines from:
```python
        OptionsRecommenderStep(),
        RecommenderStep(),
    ]
```
to:
```python
        OptionsRecommenderStep(),
        RecommenderStep(),
        ExecutorStep(),
        IncomeTrackerStep(),
    ]
```

- [ ] **Step 4: Update `held_tickers` in `backend/app/pipeline/repo.py`** — replace the placeholder with the real query:

```python
    async def held_tickers(self) -> list[str]:
        rows = await self.session.execute(
            select(Position.ticker).where(
                Position.status == "open",
                Position.kind == "stock",
            ).distinct()
        )
        return [r[0] for r in rows.all()]
```

- [ ] **Step 5: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_default_steps_portfolio.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/pipeline/steps/__init__.py app/pipeline/repo.py tests/pipeline/test_default_steps_portfolio.py
git commit -m "feat(backend): wire executor+income_tracker into default pipeline; activate held_tickers"
```

---

### Task 7: Portfolio API

**Files:**
- Create: `backend/app/api/portfolio.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_portfolio_api.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_portfolio_api.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

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
async def test_portfolio_api(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    _now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
    _today = _now.date()

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    from app.models.stocks import DividendHistory, Price
    session.add(Price(ticker="KO", date=_today, open=Decimal("61"), high=Decimal("62"),
                      low=Decimal("60"), close=Decimal("61.50"), adj_close=Decimal("61.50"), volume=1000000))
    session.add(DividendHistory(ticker="KO", ex_date=date(2026, 6, 15), pay_date=None,
                                amount_per_share=Decimal("0.485"), frequency="quarterly"))
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="KO", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("60"),
        strike=None, expiration_date=None, now=_now)
    await repo.insert_income_event(
        ticker="KO", type_="dividend", amount=Decimal("4.85"),
        event_date=date(2026, 3, 15),
        source_position_id=pos_id, source_recommendation_id=None, now=_now)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/portfolio/holdings")
        assert r.status_code == 200
        holdings = r.json()
        assert any(h["ticker"] == "KO" for h in holdings)
        ko = next(h for h in holdings if h["ticker"] == "KO")
        assert "price_date" in ko
        assert "unrealized_pnl" in ko

        r = await client.get("/portfolio/income")
        assert r.status_code == 200
        assert any(e["ticker"] == "KO" for e in r.json())

        r = await client.get("/portfolio/income/calendar?days=30")
        assert r.status_code == 200
        cal = r.json()
        assert "upcoming_dividends" in cal

        r = await client.get("/portfolio/performance")
        assert r.status_code == 200
        perf = r.json()
        assert "ytd_income" in perf
        assert "cost_basis" in perf
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_portfolio_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Create `backend/app/api/portfolio.py`:**

```python
from datetime import date, timedelta

from fastapi import APIRouter

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/portfolio")


@router.get("/holdings")
async def holdings() -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        positions = await repo.list_open_positions(kind="stock")
        result = []
        for pos in positions:
            close = await repo.latest_close(pos.ticker)
            close_price = float(close) if close is not None else None
            unrealized_pnl = (
                float((float(close) - float(pos.avg_entry_price)) * float(pos.shares))
                if close is not None else None
            )
            # find active covered call on this ticker
            calls = await repo.list_open_positions(ticker=pos.ticker, kind="short_call")
            active_call = None
            if calls:
                c = calls[0]
                active_call = {
                    "strike": float(c.strike) if c.strike else None,
                    "expiration_date": c.expiration_date.isoformat() if c.expiration_date else None,
                    "premium": float(c.avg_entry_price),
                }
            # get latest price date
            from sqlalchemy import select
            from app.models.stocks import Price
            price_row = (await session.execute(
                select(Price.date).where(Price.ticker == pos.ticker)
                .order_by(Price.date.desc()).limit(1)
            )).scalar()
            result.append({
                "id": pos.id,
                "ticker": pos.ticker,
                "shares": float(pos.shares),
                "avg_entry_price": float(pos.avg_entry_price),
                "current_price": close_price,
                "price_date": price_row.isoformat() if price_row else None,
                "unrealized_pnl": unrealized_pnl,
                "opened_at": pos.opened_at.isoformat(),
                "active_call": active_call,
            })
        return result


@router.get("/income")
async def income(from_: date | None = None, to: date | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        events = await repo.list_income_events(from_=from_, to=to)
        return [
            {
                "id": e.id, "ticker": e.ticker, "type": e.type,
                "amount": float(e.amount), "event_date": e.event_date.isoformat(),
                "source_position_id": e.source_position_id,
            }
            for e in events
        ]


@router.get("/income/calendar")
async def income_calendar(days: int = 30) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from datetime import datetime, UTC
        today = datetime.now(UTC).date()
        cutoff = today + timedelta(days=days)

        # Upcoming dividends for held tickers
        held = await repo.list_open_positions(kind="stock")
        upcoming_dividends = []
        for pos in held:
            divs = await repo.dividends_since(pos.ticker, today - timedelta(days=1))
            for d in divs:
                if d.ex_date <= cutoff:
                    upcoming_dividends.append({
                        "ticker": pos.ticker,
                        "ex_date": d.ex_date.isoformat(),
                        "amount_per_share": float(d.amount_per_share),
                        "estimated_income": float(d.amount_per_share * pos.shares),
                    })

        # Calls expiring within N days
        calls = await repo.list_open_positions(kind="short_call")
        expiring_calls = [
            {
                "ticker": pos.ticker,
                "expiration_date": pos.expiration_date.isoformat() if pos.expiration_date else None,
                "strike": float(pos.strike) if pos.strike else None,
                "premium": float(pos.avg_entry_price),
            }
            for pos in calls
            if pos.expiration_date and pos.expiration_date <= cutoff
        ]

        return {"upcoming_dividends": upcoming_dividends, "expiring_calls": expiring_calls}


@router.get("/performance")
async def performance() -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from datetime import datetime, UTC
        today = datetime.now(UTC).date()
        ytd_start = date(today.year, 1, 1)

        events = await repo.list_income_events(from_=ytd_start, to=today)
        ytd_income = sum(float(e.amount) for e in events)

        positions = await repo.list_open_positions(kind="stock")
        cost_basis = sum(float(p.avg_entry_price) * float(p.shares) for p in positions)

        return {
            "ytd_income": ytd_income,
            "cost_basis": cost_basis,
            "note": "SPY total-return benchmark and Treasury baseline ship in Sub-project 5",
        }
```

- [ ] **Step 4: Register the router in `backend/app/main.py`** — add import and `include_router`:

```python
from app.api.portfolio import router as portfolio_router
```

```python
    app.include_router(portfolio_router)
```

- [ ] **Step 5: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_portfolio_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/portfolio.py app/main.py tests/test_portfolio_api.py
git commit -m "feat(backend): portfolio API (holdings, income, calendar, performance)"
```

---

### Task 8: Trades & positions API

**Files:**
- Create: `backend/app/api/trades.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_trades_api.py`

- [ ] **Step 1: Write the failing tests** — create `backend/tests/test_trades_api.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

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
async def test_trades_and_positions_api(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    _now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
    _today = _now.date()

    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("VZ", "Verizon", "T", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="VZ", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    pos_id = await repo.open_position(
        rec_id=rec_id, ticker="VZ", kind="stock",
        shares=Decimal("20"), avg_entry_price=Decimal("40"),
        strike=None, expiration_date=None, now=_now)
    trade_id = await repo.insert_trade(
        position_id=pos_id, ticker="VZ", side="buy",
        shares_or_contracts=Decimal("20"), price=Decimal("40"),
        reason="recommendation", now=_now)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/trades")
        assert r.status_code == 200
        assert any(t["id"] == trade_id for t in r.json())

        r = await client.get("/positions?status=open")
        assert r.status_code == 200
        assert any(p["id"] == pos_id for p in r.json())

        r = await client.get(f"/positions/{pos_id}")
        assert r.status_code == 200
        detail = r.json()
        assert detail["ticker"] == "VZ"
        assert "trades" in detail
        assert any(t["id"] == trade_id for t in detail["trades"])

        r = await client.get("/positions/99999")
        assert r.status_code == 404
```

- [ ] **Step 2: Run — expect FAIL**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_trades_api.py -v`
Expected: FAIL.

- [ ] **Step 3: Create `backend/app/api/trades.py`:**

```python
from datetime import date

from fastapi import APIRouter, HTTPException

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter()


@router.get("/trades")
async def list_trades(from_: date | None = None, to: date | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        trades = await repo.list_trades(from_=from_, to=to)
        return [
            {
                "id": t.id, "position_id": t.position_id, "ticker": t.ticker,
                "side": t.side, "shares_or_contracts": float(t.shares_or_contracts),
                "price": float(t.price), "executed_at": t.executed_at.isoformat(),
                "reason": t.reason,
            }
            for t in trades
        ]


@router.get("/positions")
async def list_positions(status: str | None = None) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        from sqlalchemy import select
        from app.models.portfolio import Position
        stmt = select(Position)
        if status is not None:
            stmt = stmt.where(Position.status == status)
        rows = await session.execute(stmt)
        positions = list(rows.scalars().all())
        return [_pos_summary(p) for p in positions]


@router.get("/positions/{position_id}")
async def get_position(position_id: int) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        pos = await repo.get_position(position_id)
        if pos is None:
            raise HTTPException(status_code=404, detail="position not found")
        trades = await repo.list_trades()
        pos_trades = [
            {
                "id": t.id, "side": t.side,
                "shares_or_contracts": float(t.shares_or_contracts),
                "price": float(t.price), "executed_at": t.executed_at.isoformat(),
                "reason": t.reason,
            }
            for t in trades if t.position_id == position_id
        ]
        events = await repo.list_income_events()
        pos_events = [
            {"id": e.id, "type": e.type, "amount": float(e.amount),
             "event_date": e.event_date.isoformat()}
            for e in events if e.source_position_id == position_id
        ]
        detail = _pos_summary(pos)
        detail["trades"] = pos_trades
        detail["income_events"] = pos_events
        return detail


def _pos_summary(pos) -> dict:
    return {
        "id": pos.id, "ticker": pos.ticker, "kind": pos.kind,
        "shares": float(pos.shares), "avg_entry_price": float(pos.avg_entry_price),
        "strike": float(pos.strike) if pos.strike else None,
        "expiration_date": pos.expiration_date.isoformat() if pos.expiration_date else None,
        "opened_at": pos.opened_at.isoformat(), "status": pos.status,
        "closed_at": pos.closed_at.isoformat() if pos.closed_at else None,
    }
```

- [ ] **Step 4: Register the router in `backend/app/main.py`** — add import and `include_router`:

```python
from app.api.trades import router as trades_router
```

```python
    app.include_router(trades_router)
```

- [ ] **Step 5: Run — expect PASS**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_trades_api.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/trades.py app/main.py tests/test_trades_api.py
git commit -m "feat(backend): trades and positions API"
```

---

### Task 9: Full suite, lint, and README update

**Files:**
- Modify: `README.md` (mark new endpoints as implemented)

- [ ] **Step 1: Run the full default suite**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -m "not slow" -q`
Expected: all pass. Fix any failures before proceeding.

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check .`
Expected: no errors. Fix any import-order or unused-import findings, then re-run.

- [ ] **Step 3: Update README API table** — mark the newly-implemented endpoints in `README.md`'s "Stocks & data", "Portfolio", and "Trades & history" tables. Change `planned` to `✅ implemented` for:
- `GET /portfolio/holdings`
- `GET /portfolio/income?from=&to=`
- `GET /portfolio/income/calendar?days=30`
- `GET /portfolio/performance`
- `GET /trades?from=&to=`
- `GET /positions?status=`
- `GET /positions/{id}`

- [ ] **Step 4: Update phasing table in `README.md`** — change Phase 4 status from `planned` to `✅ done`.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(backend): SP4 suite green + lint clean; update README"
```

---

## Self-Review

### Spec coverage check

| Spec section | Task |
|---|---|
| §2 positions table | Task 0 (ORM) + Task 1 (migration) |
| §2 trades table | Task 0 + Task 1 |
| §2 income_events table (unique constraint) | Task 0 + Task 1 |
| §2 feedback table (lessons column) | Task 0 + Task 1 |
| §3 ExecutorStep (add/sell_call/sell_position) | Task 4 |
| §3 ExecutorStep idempotency via status='executed' | Task 4 |
| §3 sell_position uses payload['position_id'] | Task 4 |
| §3 IncomeTrackerStep (dividend, OTM expiry, ITM assignment) | Task 5 |
| §3 Dividend ex-date strict boundary | Task 3 (dividends_since) + Task 5 |
| §3 OTM feedback total_return_pct = premium/cost_basis | Task 5 |
| §4 /portfolio/holdings (with price_date) | Task 7 |
| §4 /portfolio/income | Task 7 |
| §4 /portfolio/income/calendar | Task 7 |
| §4 /portfolio/performance (partial, documented) | Task 7 |
| §4 /trades, /positions, /positions/{id} | Task 8 |
| §5 ~15 new repo methods | Task 3 |
| §5 held_tickers() activated | Task 6 |
| §6 pure analysis functions | Task 2 |
| §7 default_steps updated | Task 6 |
| §8 money-unit conventions | Documented in spec; applied in Tasks 4, 5 |
| §8 income_events ON CONFLICT DO NOTHING | Task 3 (insert_income_event) |
| §9 migration test | Task 1 |
| §9 pure function tests | Task 2 |
| §9 repo tests | Task 3 |
| §9 step tests | Tasks 4, 5 |
| §9 API tests | Tasks 7, 8 |

### Type consistency check

- `open_position` returns `int` (position id) — consumed in Tasks 4, 5 ✓
- `insert_trade` returns `int` (trade id) — not consumed in steps (fire-and-forget) ✓
- `insert_income_event` returns `int | None` — None = conflict ✓
- `insert_feedback` returns `int` ✓
- `approved_unexecuted_recs` returns `list[Recommendation]` — Recommendation already imported in repo ✓
- `mark_rec_executed` returns `None` ✓
- `list_open_positions` takes `ticker: str | None, kind: str | None` — used correctly in all consumers ✓
- Pure functions: all take `Decimal`, return `Decimal` or `str` ✓
- `dividends_since` uses `DividendHistory` (already imported in repo as `from app.models.stocks import DividendHistory`) — check the import block in repo.py; `DividendHistory` is already imported (used by existing `ttm_dividends` / `consecutive_years_paid` methods) ✓
- `Position` model imported in repo via `from app.models.portfolio import Feedback, IncomeEvent, Position, Trade` ✓

### Placeholder scan

No TBD, TODO, or "implement later" text. All code blocks are complete. The `lessons` column is present in the ORM/migration but left NULL — documented as reserved for Sub-project 5, not a placeholder. ✓
