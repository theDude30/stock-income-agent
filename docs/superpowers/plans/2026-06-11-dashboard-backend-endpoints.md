# Dashboard Backend Endpoints (Sub-project 5b-i) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the read-only backend endpoints the 5b dashboard needs: `GET /portfolio/live` (mark-to-market via a 120 s `PriceCache`), the **completed** `GET /portfolio/performance` (SPY total return + Treasury baseline), and the five `/stocks/{ticker}` detail endpoints.

**Architecture:** A new `PriceCache` (`app/market/price_cache.py`) with injectable fetch-callable + clock, exposed to the portfolio router through a `_get_price_cache()` factory + `_price_cache_override` test seam (mirroring `app/api/pipeline.py`'s `_make_sources()`/`_sources_override`). Six new read methods on `PipelineRepo`. One new pure function in `app/analysis/portfolio.py` (adjusted-close total return). One new config field (`treasury_1m_yield_pct`). No schema changes, no migrations.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, pydantic-settings, pytest + testcontainers, httpx (ASGITransport). Design spec: `docs/superpowers/specs/2026-06-09-dashboard-design.md` §2.

**Branch:** `sub-project-5b-i-dashboard-backend` off `main`.

**Working directory:** all commands run from `backend/` (venv at `backend/.venv`).

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/app/market/__init__.py` | (empty package marker) |
| Create | `backend/app/market/price_cache.py` | `PriceCache` — per-ticker TTL cache |
| Create | `backend/tests/market/__init__.py` | (empty package marker) |
| Create | `backend/tests/market/test_price_cache.py` | PriceCache unit tests (fake clock + fake fetch) |
| Modify | `backend/app/pipeline/repo.py` | 6 new read methods (`get_stock`, `prices_between`, `list_dividend_history`, `list_news`, `latest_screening`, `safety_score_history`) |
| Create | `backend/tests/pipeline/test_repo_reads.py` | Repo read-method tests |
| Modify | `backend/app/api/portfolio.py` | `GET /portfolio/live`; completed `GET /portfolio/performance`; `_get_price_cache()` factory + override seam |
| Modify | `backend/app/analysis/portfolio.py` | `compute_adjusted_return_pct` pure function |
| Modify | `backend/tests/analysis/test_portfolio.py` | Test for the new pure function |
| Modify | `backend/app/config.py` | `treasury_1m_yield_pct` setting |
| Modify | `backend/tests/test_config.py` | Treasury setting default + env-override tests |
| Modify | `backend/tests/test_portfolio_api.py` | `/portfolio/live` (fresh + stale) and completed `/performance` tests |
| Modify | `backend/app/api/stocks.py` | 5 new `/stocks/{ticker}` endpoints |
| Modify | `backend/tests/test_stocks_api.py` | Tests for the 5 new endpoints |
| Modify | `.env.example` (repo root — there is **no** `backend/.env.example`) | `TREASURY_1M_YIELD_PCT` |
| Modify | `README.md` (repo root) | Flip implemented rows, status note, test count |

**Shared test-suite facts the implementer must know:**
- `tests/conftest.py` provides a **session-scoped** `pg_container` and `session` fixtures — DB state is shared across ALL test modules in one run. Always use **fresh tickers** not used elsewhere (taken: KO, JNJ, PG, MMM, VZ, T, O, ABBV, WMT, XOM, CVX). This plan uses: PEP, KMB, ADP, MCD.
- Every DB-touching test module needs the module-scoped `_migrate` autouse fixture (alembic upgrade head; idempotent).
- `pyproject.toml` sets `asyncio_mode = "auto"`, default `-m 'not slow'`, and `filterwarnings = ["error", ...]`.
- DB-touching tests are decorated `@pytest.mark.asyncio(loop_scope="session")`.
- ruff selects `["E","F","I","B","UP","N","RUF"]`; FastAPI `Query(...)` defaults need `# noqa: B008` (existing convention, see `app/api/portfolio.py:59`).

---

### Task 0: Branch setup

**Files:** none

- [ ] **Step 1: Create the feature branch**

```bash
cd /Users/tbergman/Documents/Workspace/stock-income-agent
git checkout main && git pull
git checkout -b sub-project-5b-i-dashboard-backend
```

Expected: `Switched to a new branch 'sub-project-5b-i-dashboard-backend'`

---

### Task 1: `PriceCache`

**Files:**
- Create: `backend/app/market/__init__.py`
- Create: `backend/app/market/price_cache.py`
- Create: `backend/tests/market/__init__.py`
- Test: `backend/tests/market/test_price_cache.py`

The cache wraps a **synchronous** fetch callable (yfinance is sync) and runs it via `asyncio.to_thread`. Clock is injectable for tests. TTL 120 s per design spec §2. Fetch failures propagate (the `/portfolio/live` endpoint catches them and falls back to the DB close).

- [ ] **Step 1: Create package markers**

```bash
touch backend/app/market/__init__.py backend/tests/market/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `backend/tests/market/test_price_cache.py`:

```python
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.market.price_cache import PriceCache


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 6, 11, 14, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: int) -> None:
        self.now = self.now + timedelta(seconds=seconds)


class CountingFetch:
    def __init__(self, price: Decimal) -> None:
        self.price = price
        self.calls: list[str] = []

    def __call__(self, ticker: str) -> Decimal:
        self.calls.append(ticker)
        return self.price


async def test_first_get_fetches_and_returns_price_with_timestamp():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("61.50"))
    cache = PriceCache(fetch=fetch, now=clock)

    price, as_of = await cache.get("KO")

    assert price == Decimal("61.50")
    assert as_of == clock.now
    assert fetch.calls == ["KO"]


async def test_second_get_within_ttl_uses_cache():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("61.50"))
    cache = PriceCache(fetch=fetch, now=clock)

    first = await cache.get("KO")
    clock.advance(119)
    second = await cache.get("KO")

    assert second == first  # same price AND same as_of timestamp
    assert fetch.calls == ["KO"]  # only one real fetch


async def test_get_after_ttl_refetches():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("61.50"))
    cache = PriceCache(fetch=fetch, now=clock)

    await cache.get("KO")
    clock.advance(120)  # exactly TTL → expired
    fetch.price = Decimal("62.00")
    price, as_of = await cache.get("KO")

    assert price == Decimal("62.00")
    assert as_of == clock.now
    assert fetch.calls == ["KO", "KO"]


async def test_tickers_are_cached_independently():
    clock = FakeClock()
    fetch = CountingFetch(Decimal("100"))
    cache = PriceCache(fetch=fetch, now=clock)

    await cache.get("KO")
    await cache.get("PEP")
    await cache.get("KO")

    assert fetch.calls == ["KO", "PEP"]


async def test_fetch_failure_propagates_and_is_not_cached():
    clock = FakeClock()
    calls: list[str] = []

    def failing_fetch(ticker: str) -> Decimal:
        calls.append(ticker)
        raise LookupError("no data")

    cache = PriceCache(fetch=failing_fetch, now=clock)

    with pytest.raises(LookupError):
        await cache.get("KO")
    with pytest.raises(LookupError):
        await cache.get("KO")  # not cached → fetch attempted again

    assert calls == ["KO", "KO"]


async def test_default_clock_is_utc_now():
    cache = PriceCache(fetch=lambda t: Decimal("1"))
    _, as_of = await cache.get("KO")
    assert as_of.tzinfo is not None
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd backend && .venv/bin/pytest tests/market/test_price_cache.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.market.price_cache'`

- [ ] **Step 4: Implement `PriceCache`**

Create `backend/app/market/price_cache.py`:

```python
import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal


class PriceCache:
    """Per-ticker live-price cache with a TTL (default 120 s, design spec 5b §2).

    Wraps a synchronous fetch callable (yfinance is sync) and runs it in a
    thread so async endpoints don't block the event loop. Fetch failures
    propagate to the caller and are never cached.
    """

    def __init__(
        self,
        fetch: Callable[[str], Decimal],
        now: Callable[[], datetime] | None = None,
        ttl_seconds: int = 120,
    ) -> None:
        self._fetch = fetch
        self._now = now if now is not None else (lambda: datetime.now(tz=UTC))
        self._ttl_seconds = ttl_seconds
        self._cache: dict[str, tuple[Decimal, datetime]] = {}

    async def get(self, ticker: str) -> tuple[Decimal, datetime]:
        """Return (price, as_of). Serves from cache while the entry is younger than the TTL."""
        cached = self._cache.get(ticker)
        now = self._now()
        if cached is not None and (now - cached[1]).total_seconds() < self._ttl_seconds:
            return cached
        price = await asyncio.to_thread(self._fetch, ticker)
        entry = (price, now)
        self._cache[ticker] = entry
        return entry
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/market/test_price_cache.py -v
```

Expected: 6 passed

- [ ] **Step 6: Lint and commit**

```bash
cd backend && .venv/bin/ruff check app/market tests/market
cd .. && git add backend/app/market backend/tests/market
git commit -m "feat(backend): PriceCache with 120s TTL for live dashboard prices"
```

---

### Task 2: Repo read methods

**Files:**
- Modify: `backend/app/pipeline/repo.py`
- Test: `backend/tests/pipeline/test_repo_reads.py` (new)

Six straight-read methods. Insert each next to its section's existing methods (section markers like `# ----- prices -----` already exist in the file). No new imports are needed — `Stock`, `Price`, `DividendHistory`, `NewsItem`, `Screening`, `DividendSafetyScore`, `select` are all already imported at the top of `repo.py`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/pipeline/test_repo_reads.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.stocks import DividendHistory, Price
from app.pipeline.repo import PipelineRepo
from app.sources.base import NewsItemDTO, StockMeta


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


_now = datetime(2026, 6, 11, 17, 15, tzinfo=UTC)
_today = _now.date()


@pytest.mark.asyncio(loop_scope="session")
async def test_get_stock(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    stock = await repo.get_stock("ADP")
    assert stock is not None and stock.name == "Automatic Data Processing"
    assert await repo.get_stock("NOPE") is None
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_prices_between(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    for d, close in [(date(2026, 6, 8), "300"), (date(2026, 6, 9), "302"), (date(2026, 6, 10), "301")]:
        session.add(Price(ticker="ADP", date=d, open=Decimal(close), high=Decimal(close),
                          low=Decimal(close), close=Decimal(close), adj_close=Decimal(close),
                          volume=1000))
    await session.flush()

    all_rows = await repo.prices_between("ADP")
    assert [p.date for p in all_rows] == [date(2026, 6, 8), date(2026, 6, 9), date(2026, 6, 10)]  # asc

    windowed = await repo.prices_between("ADP", from_=date(2026, 6, 9), to=date(2026, 6, 9))
    assert len(windowed) == 1 and windowed[0].close == Decimal("302")
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_dividend_history_newest_first(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    session.add(DividendHistory(ticker="ADP", ex_date=date(2026, 3, 10), pay_date=None,
                                amount_per_share=Decimal("1.40"), frequency="quarterly"))
    session.add(DividendHistory(ticker="ADP", ex_date=date(2026, 6, 10), pay_date=None,
                                amount_per_share=Decimal("1.40"), frequency="quarterly"))
    await session.flush()

    divs = await repo.list_dividend_history("ADP")
    assert [d.ex_date for d in divs] == [date(2026, 6, 10), date(2026, 3, 10)]  # desc
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_list_news_newest_first_with_limit(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    items = [
        NewsItemDTO(url=f"https://example.com/adp/{i}", title=f"ADP story {i}", summary="s",
                    source="example", published_at=datetime(2026, 6, 1 + i, tzinfo=UTC))
        for i in range(3)
    ]
    await repo.insert_news("ADP", items)

    news = await repo.list_news("ADP", limit=2)
    assert len(news) == 2
    assert news[0].published_at > news[1].published_at  # desc
    assert news[0].title == "ADP story 2"
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_latest_screening(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    run_id = await repo.start_run(now=_now)
    await repo.insert_screening(run_id, "ADP", 70.0, {"k": 1}, True,
                                datetime(2026, 6, 10, tzinfo=UTC))
    await repo.insert_screening(run_id, "ADP", 75.0, {"k": 2}, True,
                                datetime(2026, 6, 11, tzinfo=UTC))

    latest = await repo.latest_screening("ADP")
    assert latest is not None and latest.dividend_quality_score == Decimal("75.00")
    assert await repo.latest_screening("NOPE") is None
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_score_history_desc_with_limit(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("ADP", "Automatic Data Processing", "Industrials", "Payroll")],
                             today=_today)
    for day, score in [(9, 80), (10, 82), (11, 85)]:
        await repo.insert_safety_score("ADP", score, 0.5, 2.0, 0.4, 25, [], "fine",
                                       "m", "v", datetime(2026, 6, day, tzinfo=UTC))

    history = await repo.safety_score_history("ADP", limit=2)
    assert [s.score for s in history] == [85, 82]  # newest first, limited
    await session.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && .venv/bin/pytest tests/pipeline/test_repo_reads.py -v
```

Expected: FAIL — `AttributeError: 'PipelineRepo' object has no attribute 'get_stock'` (and similar)

- [ ] **Step 3: Add the six repo methods**

In `backend/app/pipeline/repo.py`:

**(a)** In the `# ----- stocks -----` section, immediately after `held_tickers` (ends ~line 79):

```python
    async def get_stock(self, ticker: str) -> Stock | None:
        return await self.session.get(Stock, ticker)
```

**(b)** In the `# ----- prices -----` section, immediately after `last_price_date` (ends ~line 118):

```python
    async def prices_between(self, ticker: str, from_: date | None = None,
                             to: date | None = None) -> list[Price]:
        stmt = select(Price).where(Price.ticker == ticker).order_by(Price.date)
        if from_ is not None:
            stmt = stmt.where(Price.date >= from_)
        if to is not None:
            stmt = stmt.where(Price.date <= to)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())
```

**(c)** In the `# ----- dividends -----` section, immediately after `last_dividend_ex_date` (ends ~line 149):

```python
    async def list_dividend_history(self, ticker: str) -> list[DividendHistory]:
        rows = await self.session.execute(
            select(DividendHistory).where(DividendHistory.ticker == ticker)
            .order_by(DividendHistory.ex_date.desc())
        )
        return list(rows.scalars().all())
```

**(d)** In the `# ----- news -----` section, immediately after `insert_news` (ends ~line 199):

```python
    async def list_news(self, ticker: str, limit: int = 20) -> list[NewsItem]:
        rows = await self.session.execute(
            select(NewsItem).where(NewsItem.ticker == ticker)
            .order_by(NewsItem.published_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())
```

**(e)** In the `# ----- screenings -----` section, immediately after `latest_screening_run_id` (ends ~line 381):

```python
    async def latest_screening(self, ticker: str) -> Screening | None:
        row = await self.session.execute(
            select(Screening).where(Screening.ticker == ticker)
            .order_by(Screening.created_at.desc()).limit(1)
        )
        return row.scalar_one_or_none()
```

**(f)** In the `# ----- safety scores -----` section, immediately after `latest_safety_score` (ends ~line 405):

```python
    async def safety_score_history(self, ticker: str, limit: int = 20) -> list[DividendSafetyScore]:
        rows = await self.session.execute(
            select(DividendSafetyScore).where(DividendSafetyScore.ticker == ticker)
            .order_by(DividendSafetyScore.scored_at.desc()).limit(limit)
        )
        return list(rows.scalars().all())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && .venv/bin/pytest tests/pipeline/test_repo_reads.py -v
```

Expected: 6 passed

- [ ] **Step 5: Lint and commit**

```bash
cd backend && .venv/bin/ruff check app/pipeline/repo.py tests/pipeline/test_repo_reads.py
cd .. && git add backend/app/pipeline/repo.py backend/tests/pipeline/test_repo_reads.py
git commit -m "feat(backend): repo read methods for dashboard detail endpoints"
```

---

### Task 3: `GET /portfolio/live`

**Files:**
- Modify: `backend/app/api/portfolio.py`
- Test: `backend/tests/test_portfolio_api.py` (append two tests)

The endpoint enriches open stock positions with mark-to-market P&L from `PriceCache`. On a per-ticker fetch failure it falls back to `repo.latest_close` with `stale: true` (design decision §7 #6 — degrade, don't error). The cache is process-global (so the TTL actually spans requests) and overridable for tests.

The production fetch callable goes through `app.api.pipeline._make_sources()` so it honors the existing `_sources_override` seam and reuses `YFinancePriceSource`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_portfolio_api.py`:

```python
@pytest.mark.asyncio(loop_scope="session")
async def test_portfolio_live_marks_to_market(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    _now = datetime(2026, 6, 11, 17, 15, tzinfo=UTC)
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PEP", "PepsiCo", "S", "B")], today=_now.date())
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PEP", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(
        rec_id=rec_id, ticker="PEP", kind="stock",
        shares=Decimal("10"), avg_entry_price=Decimal("160"),
        strike=None, expiration_date=None, now=_now)
    await session.commit()

    from app.api import portfolio as portfolio_api
    from app.market.price_cache import PriceCache

    portfolio_api._price_cache_override = PriceCache(fetch=lambda t: Decimal("165"))
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/portfolio/live")
            assert r.status_code == 200
            body = r.json()
            assert "as_of" in body
            pep = next(p for p in body["positions"] if p["ticker"] == "PEP")
            assert pep["live_price"] == 165.0
            assert pep["live_pnl"] == 50.0          # (165 - 160) * 10
            assert pep["live_pnl_pct"] == pytest.approx(50.0 / 1600.0)
            assert pep["stale"] is False
    finally:
        portfolio_api._price_cache_override = None


@pytest.mark.asyncio(loop_scope="session")
async def test_portfolio_live_falls_back_to_db_close_when_fetch_fails(
    session, monkeypatch, pg_container
):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    # PEP position exists from the previous test (shares 10 @ 160, committed).
    # Give it a DB close so the stale fallback has something to return.
    await session.execute(
        pg_insert(Price).values(
            ticker="PEP", date=date(2026, 6, 10), open=Decimal("162"), high=Decimal("163"),
            low=Decimal("161"), close=Decimal("162"), adj_close=Decimal("162"), volume=500,
        ).on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={"close": Decimal("162"), "adj_close": Decimal("162")},
        )
    )
    await session.commit()

    from app.api import portfolio as portfolio_api
    from app.market.price_cache import PriceCache

    def _boom(ticker: str) -> Decimal:
        raise LookupError("yfinance down")

    portfolio_api._price_cache_override = PriceCache(fetch=_boom)
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/portfolio/live")
            assert r.status_code == 200
            pep = next(p for p in r.json()["positions"] if p["ticker"] == "PEP")
            assert pep["stale"] is True
            assert pep["live_price"] == 162.0
            assert pep["live_pnl"] == 20.0          # (162 - 160) * 10
    finally:
        portfolio_api._price_cache_override = None
```

- [ ] **Step 2: Run new tests to verify they fail**

```bash
cd backend && .venv/bin/pytest tests/test_portfolio_api.py -v -k live
```

Expected: FAIL — `AttributeError: module 'app.api.portfolio' has no attribute '_price_cache_override'` (or 404 on `/portfolio/live`)

- [ ] **Step 3: Implement the endpoint + cache factory**

In `backend/app/api/portfolio.py`, replace the import block at the top of the file (currently lines 1–8) with:

```python
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Query

from app.db import get_session_factory
from app.market.price_cache import PriceCache
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/portfolio")

# Test seam: set to a PriceCache instance to override production wiring.
_price_cache_override: PriceCache | None = None

# Process-global cache so the 120 s TTL spans requests.
_price_cache: PriceCache | None = None


def _fetch_live_price(ticker: str) -> Decimal:
    """Latest close from the market-data sources (honors pipeline's _sources_override)."""
    from app.api.pipeline import _make_sources
    since = datetime.now(tz=UTC).date() - timedelta(days=7)
    bars = list(_make_sources().prices.fetch(ticker, since))
    if not bars:
        raise LookupError(f"no recent price bars for {ticker}")
    return Decimal(str(bars[-1].close))


def _get_price_cache() -> PriceCache:
    global _price_cache
    if _price_cache_override is not None:
        return _price_cache_override
    if _price_cache is None:
        _price_cache = PriceCache(fetch=_fetch_live_price)
    return _price_cache
```

Then add the endpoint after the existing `holdings()` function (after ~line 54):

```python
@router.get("/live")
async def live() -> dict:
    cache = _get_price_cache()
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        positions = await repo.list_open_positions(kind="stock")
        out = []
        for pos in positions:
            stale = False
            price: Decimal | None
            try:
                price, _ = await cache.get(pos.ticker)
            except Exception:
                close = await repo.latest_close(pos.ticker)
                price = Decimal(str(close)) if close is not None else None
                stale = True
            if price is not None:
                cost = pos.avg_entry_price * pos.shares
                live_pnl = (price - pos.avg_entry_price) * pos.shares
                live_pnl_pct = live_pnl / cost if cost > 0 else Decimal("0")
            else:
                live_pnl = None
                live_pnl_pct = None
            out.append({
                "id": pos.id,
                "ticker": pos.ticker,
                "shares": float(pos.shares),
                "avg_entry_price": float(pos.avg_entry_price),
                "live_price": float(price) if price is not None else None,
                "live_pnl": float(live_pnl) if live_pnl is not None else None,
                "live_pnl_pct": float(live_pnl_pct) if live_pnl_pct is not None else None,
                "stale": stale,
                "opened_at": pos.opened_at.isoformat(),
            })
        return {"as_of": datetime.now(tz=UTC).isoformat(), "positions": out}
```

Note: the existing `income()` endpoint already imports `Query` — the new top-of-file import block keeps that working. The inline `from datetime import UTC, datetime` statements inside existing functions become redundant but are harmless; remove them only if they trigger ruff F811 (they won't — they're function-local).

- [ ] **Step 4: Run the module's tests**

```bash
cd backend && .venv/bin/pytest tests/test_portfolio_api.py -v
```

Expected: all pass (existing `test_portfolio_api` + 2 new)

- [ ] **Step 5: Lint and commit**

```bash
cd backend && .venv/bin/ruff check app/api/portfolio.py tests/test_portfolio_api.py
cd .. && git add backend/app/api/portfolio.py backend/tests/test_portfolio_api.py
git commit -m "feat(backend): GET /portfolio/live with mark-to-market P&L and stale fallback"
```

---

### Task 4: Completed `GET /portfolio/performance`

**Files:**
- Modify: `backend/app/analysis/portfolio.py` (new pure function)
- Modify: `backend/tests/analysis/test_portfolio.py` (append test)
- Modify: `backend/app/config.py` (new setting)
- Modify: `backend/tests/test_config.py` (append tests)
- Modify: `backend/app/api/portfolio.py` (replace `performance()`)
- Modify: `backend/tests/test_portfolio_api.py` (append test)
- Modify: `.env.example` (repo root)

SPY total return uses **adjusted closes** (dividends are baked into `adj_close`, design §2). SPY is fetched live via `_make_sources()` — it is NOT in the `stocks` table and must not be persisted (`prices.ticker` has an FK to `stocks`). Treasury baseline is a config constant (design decision §7 #8).

- [ ] **Step 1: Write the failing pure-function test**

Append to `backend/tests/analysis/test_portfolio.py`:

```python
def test_compute_adjusted_return_pct():
    from app.analysis.portfolio import compute_adjusted_return_pct
    # 100 → 105 adjusted = +5%
    assert compute_adjusted_return_pct(Decimal("100"), Decimal("105")) == Decimal("0.05")
    # guard: non-positive start
    assert compute_adjusted_return_pct(Decimal("0"), Decimal("105")) == Decimal("0")
```

- [ ] **Step 2: Write the failing config tests**

Append to `backend/tests/test_config.py`:

```python
def test_treasury_1m_yield_default(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.delenv("TREASURY_1M_YIELD_PCT", raising=False)

    from app.config import Settings

    assert Settings().treasury_1m_yield_pct == 4.2


def test_treasury_1m_yield_env_override(monkeypatch):
    monkeypatch.setenv("POSTGRES_USER", "u")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p")
    monkeypatch.setenv("POSTGRES_DB", "d")
    monkeypatch.setenv("POSTGRES_HOST", "h")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("TREASURY_1M_YIELD_PCT", "5.1")

    from app.config import Settings

    assert Settings().treasury_1m_yield_pct == 5.1
```

- [ ] **Step 3: Run both to verify they fail**

```bash
cd backend && .venv/bin/pytest tests/analysis/test_portfolio.py tests/test_config.py -v
```

Expected: 2 new FAIL (`ImportError: cannot import name 'compute_adjusted_return_pct'`; `AttributeError: ... treasury_1m_yield_pct`), existing tests pass

- [ ] **Step 4: Implement pure function and setting**

Append to `backend/app/analysis/portfolio.py`:

```python
def compute_adjusted_return_pct(start_adj_close: Decimal, end_adj_close: Decimal) -> Decimal:
    """Total return implied by adjusted closes (dividends are baked into adj_close)."""
    if start_adj_close <= 0:
        return Decimal("0")
    return (end_adj_close - start_adj_close) / start_adj_close
```

In `backend/app/config.py`, add after the `llm_model` field (line 22):

```python
    # Annualized 1-month Treasury yield (%) used as the performance baseline
    # (design 5b §2: config constant; optionally ^IRX-refreshed later).
    treasury_1m_yield_pct: float = Field(default=4.2)
```

- [ ] **Step 5: Verify they pass**

```bash
cd backend && .venv/bin/pytest tests/analysis/test_portfolio.py tests/test_config.py -v
```

Expected: all pass

- [ ] **Step 6: Write the failing endpoint test**

Append to `backend/tests/test_portfolio_api.py`:

```python
@pytest.mark.asyncio(loop_scope="session")
async def test_portfolio_performance_includes_spy_and_treasury(
    session, monkeypatch, pg_container
):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    from app.api import pipeline as pipeline_api
    from app.sources.base import PriceBar, Sources
    from app.sources.fakes import (
        InMemoryDividendSource,
        InMemoryNewsSource,
        InMemoryOptionsSource,
        InMemoryPriceSource,
        InMemoryUniverseSource,
    )

    spy_bars = [
        PriceBar(date=date(2026, 1, 2), open=100.0, high=100.0, low=100.0,
                 close=100.0, adj_close=100.0, volume=1),
        PriceBar(date=date(2026, 6, 10), open=105.0, high=105.0, low=105.0,
                 close=105.0, adj_close=105.0, volume=1),
    ]
    pipeline_api._sources_override = Sources(
        universe=InMemoryUniverseSource([]),
        prices=InMemoryPriceSource({"SPY": spy_bars}),
        dividends=InMemoryDividendSource({}),
        options=InMemoryOptionsSource({}),
        news=InMemoryNewsSource({}),
    )
    try:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/portfolio/performance")
            assert r.status_code == 200
            perf = r.json()
            assert "note" not in perf  # SP4 placeholder removed
            assert "ytd_income" in perf
            assert "cost_basis" in perf
            assert "ytd_capital_pnl" in perf
            assert "ytd_total_return_pct" in perf
            assert perf["spy_total_return_pct"] == pytest.approx(0.05)  # 100 → 105
            assert perf["treasury_1m_yield_pct"] == 4.2
            assert 0 < perf["treasury_ytd_return_pct"] < 0.042  # pro-rated YTD fraction
    finally:
        pipeline_api._sources_override = None
```

- [ ] **Step 7: Run it to verify it fails**

```bash
cd backend && .venv/bin/pytest tests/test_portfolio_api.py -v -k performance
```

Expected: FAIL — `"note" not in perf` assertion (old endpoint still returns the placeholder)

- [ ] **Step 8: Replace the `performance()` endpoint**

In `backend/app/api/portfolio.py`:

Add to the top-of-file imports (the block created in Task 3):

```python
import asyncio

from app.analysis.portfolio import compute_adjusted_return_pct, compute_total_return_pct
from app.config import get_settings
```

(`import asyncio` goes above the `from` imports per isort/ruff-I ordering.)

Replace the entire existing `performance()` function (the one returning the `"note"` key) with:

```python
def _spy_ytd_total_return_pct(ytd_start: date) -> float | None:
    """SPY total return from adjusted closes; None if the fetch fails or is empty."""
    from app.api.pipeline import _make_sources
    try:
        bars = list(_make_sources().prices.fetch("SPY", ytd_start))
    except Exception:
        return None
    if len(bars) < 2:
        return None
    start = Decimal(str(bars[0].adj_close))
    end = Decimal(str(bars[-1].adj_close))
    return float(compute_adjusted_return_pct(start, end))


@router.get("/performance")
async def performance() -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        today = datetime.now(tz=UTC).date()
        ytd_start = date(today.year, 1, 1)

        events = await repo.list_income_events(from_=ytd_start, to=today)
        ytd_income = sum((Decimal(str(e.amount)) for e in events), Decimal("0"))

        positions = await repo.list_open_positions(kind="stock")
        cost_basis = Decimal("0")
        capital_pnl = Decimal("0")
        for p in positions:
            cost_basis += p.avg_entry_price * p.shares
            close = await repo.latest_close(p.ticker)
            if close is not None:
                capital_pnl += (Decimal(str(close)) - p.avg_entry_price) * p.shares

        # premiums are already income events (call_premium / assignment_gain),
        # so they're inside ytd_income; pass premiums=0 to avoid double counting.
        total_return_pct = compute_total_return_pct(
            capital_pnl=capital_pnl, dividends=ytd_income,
            premiums=Decimal("0"), cost_basis=cost_basis,
        )

        spy_total_return_pct = await asyncio.to_thread(_spy_ytd_total_return_pct, ytd_start)

        settings = get_settings()
        ytd_fraction = (today - ytd_start).days / 365
        treasury_ytd_return_pct = settings.treasury_1m_yield_pct / 100 * ytd_fraction

        return {
            "ytd_income": float(ytd_income),
            "cost_basis": float(cost_basis),
            "ytd_capital_pnl": float(capital_pnl),
            "ytd_total_return_pct": float(total_return_pct),
            "spy_total_return_pct": spy_total_return_pct,
            "treasury_1m_yield_pct": settings.treasury_1m_yield_pct,
            "treasury_ytd_return_pct": treasury_ytd_return_pct,
        }
```

- [ ] **Step 9: Run the module's tests**

```bash
cd backend && .venv/bin/pytest tests/test_portfolio_api.py -v
```

Expected: all pass (1 + 2 live + 1 performance)

- [ ] **Step 10: Add the env key to `.env.example`**

Append to the repo-root `.env.example` (after the `NOTIFY_EMAIL_TO=` line):

```
# Performance baseline — annualized 1-month Treasury yield (%)
TREASURY_1M_YIELD_PCT=4.2
```

- [ ] **Step 11: Lint and commit**

```bash
cd backend && .venv/bin/ruff check app tests
cd .. && git add backend/app backend/tests .env.example
git commit -m "feat(backend): complete GET /portfolio/performance with SPY total return and Treasury baseline"
```

---

### Task 5: Stock detail endpoints — `/stocks/{ticker}`, `/prices`, `/dividends`

**Files:**
- Modify: `backend/app/api/stocks.py`
- Test: `backend/tests/test_stocks_api.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_stocks_api.py` (the file already imports `PipelineRepo`, `StockMeta`, `create_app`, `ASGITransport`, `AsyncClient`, `datetime`, `UTC`):

```python
@pytest.mark.asyncio(loop_scope="session")
async def test_stock_detail_prices_dividends(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    from datetime import date
    from decimal import Decimal

    from app.models.stocks import DividendHistory, Price

    _now = datetime(2026, 6, 11, tzinfo=UTC)
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KMB", "Kimberly-Clark", "Staples", "Household")],
                             today=_now.date())
    run_id = await repo.start_run(now=_now)
    await repo.insert_screening(run_id, "KMB", 81.0, {"ttm_yield": 0.034}, True, _now)
    await repo.insert_safety_score("KMB", 79, 0.6, 1.8, 0.7, 52, [], "steady",
                                   "m", "v", _now)
    for d, close in [(date(2026, 6, 9), "130"), (date(2026, 6, 10), "131")]:
        session.add(Price(ticker="KMB", date=d, open=Decimal(close), high=Decimal(close),
                          low=Decimal(close), close=Decimal(close), adj_close=Decimal(close),
                          volume=2000))
    session.add(DividendHistory(ticker="KMB", ex_date=date(2026, 3, 6), pay_date=date(2026, 4, 2),
                                amount_per_share=Decimal("1.22"), frequency="quarterly"))
    session.add(DividendHistory(ticker="KMB", ex_date=date(2026, 6, 5), pay_date=None,
                                amount_per_share=Decimal("1.22"), frequency="quarterly"))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # detail
        r = await client.get("/stocks/KMB")
        assert r.status_code == 200
        body = r.json()
        assert body["name"] == "Kimberly-Clark"
        assert body["latest_screening"]["dividend_quality_score"] == 81.0
        assert body["latest_safety_score"]["score"] == 79

        r = await client.get("/stocks/NOPE")
        assert r.status_code == 404

        # prices, with and without window
        r = await client.get("/stocks/KMB/prices")
        assert r.status_code == 200 and len(r.json()) == 2

        r = await client.get("/stocks/KMB/prices?from=2026-06-10&to=2026-06-10")
        rows = r.json()
        assert len(rows) == 1 and rows[0]["close"] == 131.0

        # dividends, newest first
        r = await client.get("/stocks/KMB/dividends")
        divs = r.json()
        assert [d["ex_date"] for d in divs] == ["2026-06-05", "2026-03-06"]
        assert divs[0]["amount_per_share"] == 1.22
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && .venv/bin/pytest tests/test_stocks_api.py -v -k detail
```

Expected: FAIL — 404 on `GET /stocks/KMB` (route not defined)

- [ ] **Step 3: Implement the three endpoints**

In `backend/app/api/stocks.py`, replace the import block (lines 1–4) with:

```python
from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo
```

Add the endpoints after the existing `safety_score` function. **Route-ordering note:** FastAPI matches in registration order; `/stocks/{ticker}` must come AFTER the more-specific `/stocks/{ticker}/safety-score` etc. is irrelevant here because the paths differ in segment count — but keep the existing `safety_score` route untouched and append below it:

```python
@router.get("/stocks/{ticker}")
async def stock_detail(ticker: str) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        stock = await repo.get_stock(ticker)
        if stock is None:
            raise HTTPException(status_code=404, detail="unknown ticker")
        screening = await repo.latest_screening(ticker)
        safety = await repo.latest_safety_score(ticker)
        return {
            "ticker": stock.ticker, "name": stock.name, "sector": stock.sector,
            "industry": stock.industry, "active": stock.active,
            "latest_screening": {
                "dividend_quality_score": float(screening.dividend_quality_score),
                "passed_screen": screening.passed_screen,
                "signals": screening.signals,
                "created_at": screening.created_at.isoformat(),
            } if screening is not None else None,
            "latest_safety_score": {
                "score": safety.score,
                "concerns": list(safety.concerns or []),
                "reasoning": safety.llm_reasoning,
                "scored_at": safety.scored_at.isoformat(),
            } if safety is not None else None,
        }


@router.get("/stocks/{ticker}/prices")
async def stock_prices(
    ticker: str,
    from_: date | None = Query(None, alias="from"),  # noqa: B008
    to: date | None = None,
) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.prices_between(ticker, from_=from_, to=to)
        return [
            {"date": p.date.isoformat(), "open": float(p.open), "high": float(p.high),
             "low": float(p.low), "close": float(p.close), "adj_close": float(p.adj_close),
             "volume": p.volume}
            for p in rows
        ]


@router.get("/stocks/{ticker}/dividends")
async def stock_dividends(ticker: str) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_dividend_history(ticker)
        return [
            {"ex_date": d.ex_date.isoformat(),
             "pay_date": d.pay_date.isoformat() if d.pay_date is not None else None,
             "amount_per_share": float(d.amount_per_share),
             "frequency": d.frequency}
            for d in rows
        ]
```

- [ ] **Step 4: Run the module's tests**

```bash
cd backend && .venv/bin/pytest tests/test_stocks_api.py -v
```

Expected: all pass

- [ ] **Step 5: Lint and commit**

```bash
cd backend && .venv/bin/ruff check app/api/stocks.py tests/test_stocks_api.py
cd .. && git add backend/app/api/stocks.py backend/tests/test_stocks_api.py
git commit -m "feat(backend): stock detail, prices, and dividends endpoints"
```

---

### Task 6: `/stocks/{ticker}/news` and `/stocks/{ticker}/safety-score/history`

**Files:**
- Modify: `backend/app/api/stocks.py`
- Test: `backend/tests/test_stocks_api.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_stocks_api.py`:

```python
@pytest.mark.asyncio(loop_scope="session")
async def test_stock_news_and_safety_history(session, monkeypatch, pg_container):
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    from app.sources.base import NewsItemDTO

    repo = PipelineRepo(session)
    # KMB exists from the previous test (with one safety score at 2026-06-11).
    await repo.insert_news("KMB", [
        NewsItemDTO(url="https://example.com/kmb/1", title="KMB raises dividend", summary="up",
                    source="example", published_at=datetime(2026, 6, 9, tzinfo=UTC)),
        NewsItemDTO(url="https://example.com/kmb/2", title="KMB earnings beat", summary="beat",
                    source="example", published_at=datetime(2026, 6, 10, tzinfo=UTC)),
    ])
    # second, older safety score → history of 2
    await repo.insert_safety_score("KMB", 74, 0.6, 1.8, 0.7, 51, ["watch payout"], "ok",
                                   "m", "v", datetime(2026, 3, 11, tzinfo=UTC))
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        r = await client.get("/stocks/KMB/news?limit=1")
        assert r.status_code == 200
        news = r.json()
        assert len(news) == 1
        assert news[0]["title"] == "KMB earnings beat"  # newest first

        r = await client.get("/stocks/KMB/safety-score/history")
        assert r.status_code == 200
        hist = r.json()
        assert [h["score"] for h in hist] == [79, 74]  # newest first
        assert hist[1]["concerns"] == ["watch payout"]

        r = await client.get("/stocks/KMB/safety-score/history?limit=1")
        assert [h["score"] for h in r.json()] == [79]
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd backend && .venv/bin/pytest tests/test_stocks_api.py -v -k history
```

Expected: FAIL — 404 on `/stocks/KMB/news` (route not defined)

- [ ] **Step 3: Implement the two endpoints**

Append to `backend/app/api/stocks.py`:

```python
@router.get("/stocks/{ticker}/news")
async def stock_news(ticker: str, limit: int = 20) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_news(ticker, limit=limit)
        return [
            {"id": n.id, "published_at": n.published_at.isoformat(), "source": n.source,
             "url": n.url, "title": n.title, "summary": n.summary,
             "sentiment_score": float(n.sentiment_score) if n.sentiment_score is not None else None}
            for n in rows
        ]


@router.get("/stocks/{ticker}/safety-score/history")
async def safety_score_history(ticker: str, limit: int = 20) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.safety_score_history(ticker, limit=limit)
        return [
            {"score": s.score, "concerns": list(s.concerns or []),
             "scored_at": s.scored_at.isoformat()}
            for s in rows
        ]
```

**Route-ordering caution:** FastAPI resolves `/stocks/KMB/safety-score` against `/stocks/{ticker}/safety-score` (2 segments after prefix) and `/stocks/KMB/safety-score/history` against the new 3-segment route — no conflict regardless of registration order.

- [ ] **Step 4: Run the module's tests**

```bash
cd backend && .venv/bin/pytest tests/test_stocks_api.py -v
```

Expected: all pass

- [ ] **Step 5: Lint and commit**

```bash
cd backend && .venv/bin/ruff check app/api/stocks.py tests/test_stocks_api.py
cd .. && git add backend/app/api/stocks.py backend/tests/test_stocks_api.py
git commit -m "feat(backend): stock news and safety-score history endpoints"
```

---

### Task 7: Full suite, lint, README

**Files:**
- Modify: `README.md` (repo root)

- [ ] **Step 1: Run the full backend suite and lint**

```bash
cd backend && .venv/bin/pytest -m "not slow" -q && .venv/bin/ruff check app tests
```

Expected: all tests pass (124 existing + the ~17 added by Tasks 1–6), ruff clean. Note the exact total test count from pytest's summary line for Step 2.

- [ ] **Step 2: Update README**

All edits in repo-root `README.md`:

**(a) REST API status note** (currently ~line 170). Replace:

```
> **Status:** Health, pipeline, recommendations, and a subset of stocks endpoints are implemented (Sub-projects 1–3). Portfolio and trades endpoints landed in Sub-project 4; learning (`/lessons`, `/feedback`), `/settings` (read), and notifier-related alerts landed in Sub-project 5a. Remaining `planned` rows (stocks list/detail/prices/dividends/news, `/portfolio/live`, `PATCH /settings`, `/settings/kill-switch`) are not yet built.
```

with:

```
> **Status:** Health, pipeline, recommendations, and a subset of stocks endpoints are implemented (Sub-projects 1–3). Portfolio and trades endpoints landed in Sub-project 4; learning (`/lessons`, `/feedback`), `/settings` (read), and notifier-related alerts landed in Sub-project 5a. Dashboard read endpoints (`/portfolio/live`, completed `/portfolio/performance`, `/stocks/{ticker}` detail/prices/dividends/news/safety-history) landed in Sub-project 5b-i. Remaining `planned` rows (`/stocks` list, `PATCH /settings`, `/settings/kill-switch`) are not yet built.
```

**(b) Stocks & data table** (~lines 182–190). Flip four rows from `planned` to `✅ implemented` and add one new row after the safety-score row:

```
| `GET` | `/stocks/{ticker}` | ✅ implemented | Stock detail + latest signals |
| `GET` | `/stocks/{ticker}/prices?from=&to=` | ✅ implemented | OHLCV history |
| `GET` | `/stocks/{ticker}/dividends` | ✅ implemented | Dividend history |
| `GET` | `/stocks/{ticker}/news?limit=` | ✅ implemented | Recent news for ticker |
| `GET` | `/stocks/{ticker}/safety-score` | ✅ implemented | Latest LLM safety score + reasoning |
| `GET` | `/stocks/{ticker}/safety-score/history?limit=` | ✅ implemented | Safety-score series (newest first) |
```

(`GET /stocks` — the universe list — stays `planned`.)

**(c) Portfolio table** (~line 206). Flip:

```
| `GET` | `/portfolio/live` | planned | Current positions with mark-to-market P&L (2-min price cache) |
```

to:

```
| `GET` | `/portfolio/live` | ✅ implemented | Current positions with mark-to-market P&L (2-min price cache, stale fallback) |
```

**(d) Test count** (~line 291). Replace `124 tests` with the actual count from Step 1's pytest summary.

- [ ] **Step 3: Re-verify and commit**

```bash
cd backend && .venv/bin/pytest -m "not slow" -q
cd .. && git add README.md
git commit -m "docs: flip 5b-i dashboard endpoint rows to implemented"
```

---

## Self-Review (spec → plan traceability)

| Design spec §2 requirement | Task |
|---|---|
| `PriceCache` (`app/market/price_cache.py`), `async def get(ticker) -> tuple[Decimal, datetime]`, 120 s TTL, factory-injected, fake clock + fake client testable | Task 1 (class) + Task 3 (factory/seam) |
| `GET /portfolio/live`: holdings fields + `live_price`/`live_pnl`/`live_pnl_pct`, top-level `as_of`, DB-close fallback with `stale: true` | Task 3 |
| Completed `GET /portfolio/performance`: YTD total return, SPY total return (adjusted close), Treasury baseline; `treasury_1m_yield_pct` config constant (`^IRX` refresh explicitly NOT required) | Task 4 |
| `GET /stocks/{ticker}` (row + latest screening + latest safety) | Task 5 |
| `GET /stocks/{ticker}/prices?from=&to=` (`Query(None, alias="from")` pattern) | Task 5 |
| `GET /stocks/{ticker}/dividends` (newest first) | Task 5 |
| `GET /stocks/{ticker}/news?limit=` | Task 6 |
| `GET /stocks/{ticker}/safety-score/history?limit=` | Task 6 |
| README rows flip `planned` → `✅ implemented` | Task 7 |
| Test strategy §8: PriceCache TTL + stale-fallback fake clock/client; `/portfolio/live` shape; `/performance` SPY+Treasury fields; each `/stocks/{ticker}/…` endpoint; no live network | Tasks 1, 3, 4, 5, 6 (all via fakes/overrides) |
