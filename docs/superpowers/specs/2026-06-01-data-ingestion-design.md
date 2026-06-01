# Data Ingestion — Sub-project 2 Design

**Status:** approved (2026-06-01). Implementation plan to follow.

**Scope:** implement Step 1 of the daily pipeline (Ingestion) from the master design spec, plus the supporting tables, the APScheduler shell, and the manual-trigger HTTP endpoint. Out of scope: screener, LLM scoring, recommendations, frontend, sentiment scoring.

**Depends on:** Sub-project 1 (Foundation) — FastAPI app, async SQLAlchemy, Alembic, `/health`, CI.

---

## 1. Goals

1. Populate the `stocks` table monthly from the S&P 500 constituent list.
2. Ingest daily OHLCV prices for every active ticker.
3. Ingest dividend history for every active ticker.
4. Ingest options chains for a 50-ticker watchlist + any held tickers.
5. Ingest recent news (RSS) for the same watchlist + holdings.
6. Record every run in `pipeline_runs` with per-step granularity.
7. Trigger automatically on weekdays at **17:15 ET** via APScheduler.
8. Allow manual triggering via `POST /pipeline/run[?step=<name>]`.

**Non-goals:**

- Screener logic (computes `dividend_quality_score`). Lands in Sub-project 3.
- LLM calls of any kind.
- Recommendations, paper trades, income tracking.
- React dashboard wiring.
- News sentiment scoring (`news_items.sentiment_score` stays null).

---

## 2. Architecture

### 2.1 Module layout

```
backend/app/
  pipeline/
    __init__.py
    runner.py            # orchestrator: pipeline_runs bookkeeping, step dispatch
    scheduler.py         # APScheduler lifespan integration, weekday 17:15 ET cron
    cli.py               # `python -m app.pipeline {run|backfill|step <name>}`
    steps/
      __init__.py
      universe.py        # monthly: refresh stocks from Wikipedia
      prices.py          # daily: yfinance OHLCV upsert (critical step)
      dividends.py       # daily: yfinance dividends upsert
      options.py         # daily: yfinance options for watchlist + holdings
      news.py            # daily: Yahoo Finance per-ticker RSS, dedupe by URL
  sources/
    __init__.py
    base.py              # protocols + DTO dataclasses
    yfinance_source.py   # production: prices, dividends, options
    wikipedia_source.py  # production: S&P 500 universe
    yahoo_rss_source.py  # production: RSS news
    fakes.py             # InMemory* test doubles
  models/
    __init__.py          # existing Base
    stocks.py            # Stock, Price, DividendEvent ORM models
    news.py              # NewsItem
    options.py           # OptionsChainRow
    pipeline.py          # PipelineRun
  api/
    pipeline.py          # GET /pipeline/runs, POST /pipeline/run
```

**Why this shape:** sources are isolated behind protocols. Steps don't import yfinance. Tests inject `fakes.py`. The orchestrator is the only thing that knows about `pipeline_runs`. Each step is a self-contained `async def run(ctx: StepContext) -> StepResult`.

### 2.2 Source protocols

```python
# app/sources/base.py
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
```

Production implementations (`yfinance_source.py`, `wikipedia_source.py`, `yahoo_rss_source.py`) wrap upstream libraries and normalize results into these dataclasses. They contain no business logic — only shape conversion. They are the only modules in the codebase allowed to import `yfinance`, `feedparser`, or scrape HTML.

### 2.3 StepContext / Sources

```python
@dataclass
class Sources:
    universe: UniverseSource
    prices: PriceSource
    dividends: DividendSource
    options: OptionsSource
    news: NewsSource

@dataclass
class StepContext:
    repo: PipelineRepo
    sources: Sources
    run_id: int
    now: Callable[[], datetime]
```

Production wiring lives in `app/main.py`'s lifespan / dependency provider; tests construct `Sources` from `fakes.py`.

### 2.4 Concurrency model

Every step that iterates tickers uses the same pattern:

```python
sem = asyncio.Semaphore(10)

async def fetch_one(ticker: str) -> tuple[str, str | None]:
    async with sem:
        try:
            data = await asyncio.to_thread(ctx.sources.prices.fetch, ticker, since)
            await ctx.repo.upsert_prices(ticker, data)
            return ticker, None
        except Exception as e:
            return ticker, str(e)

results = await asyncio.gather(*(fetch_one(t) for t in tickers))
```

- `asyncio.to_thread` keeps blocking yfinance calls off the event loop.
- Semaphore of 10 caps concurrency. yfinance's effective limit is ~50 req/sec; 10 concurrent × ~200ms each ≈ 50/sec sustained.
- The semaphore value is a constant in code, easy to tune if we see 429s.

---

## 3. Per-step behavior

### 3.1 Universe step

- **When:** first run of the first weekday of each month, plus first run on an empty DB.
- **Source:** Wikipedia `List_of_S&P_500_companies` table, parsed with `pandas.read_html`.
- **Write:** upsert into `stocks` by `ticker`. Tickers present in the DB but missing from Wikipedia get `active = false` and `removed_at = today`. New tickers get `active = true` and `added_at = today`.
- **Failure:** non-critical. Logged; run continues with whatever `stocks` table currently holds.

### 3.2 Prices step

- **Source:** yfinance per-ticker `history()`.
- **Incremental:** `since = max(prices.date) for this ticker + 1 day`. Empty DB → `since = today - 5 years` (backfill).
- **Write:** upsert (`ON CONFLICT (ticker, date) DO UPDATE`). yfinance occasionally revises old bars; updates are fine.
- **Failure handling:** per-ticker isolation. The step itself fails only if <80% of tickers succeed — this is the one critical step.

### 3.3 Dividends step

- **Source:** yfinance per-ticker `dividends` series.
- **Write:** upsert on `(ticker, ex_date)`. `pay_date` and `frequency` are inferred when possible, null otherwise (filled in by Sub-project 3's screener if needed).
- **Failure:** non-critical.

### 3.4 Options step

- **Watchlist for v1 (placeholder):** top 50 tickers by trailing-12-month dividend yield computed from current `prices` and `dividend_history`. **This is a documented stand-in for the real screener-driven ranking that lands in Sub-project 3.** Held tickers are always included (in this sub-project there are none, but the union logic stays).
- **Source:** yfinance per-ticker `option_chain(expiration)` for every expiration within the next 60 days.
- **Write:** insert (not upsert) — `options_chains` is a daily snapshot table. Each day's pull adds new rows distinguished by `snapshot_at`. This means the table grows ~50 × ~5 expirations × ~30 strikes × 2 (call/put) = ~15k rows/day. Acceptable.
- **Failure:** non-critical.

### 3.5 News step

- **Source:** Yahoo Finance per-ticker RSS feed at `https://finance.yahoo.com/rss/headline?s=TICKER`. Parsed with `feedparser`.
- **Tickers:** same watchlist + holdings as options.
- **Write:** insert (`ON CONFLICT (url) DO NOTHING`). Dedupe key is the canonical article URL.
- **Failure:** non-critical. RSS feeds break; the run shouldn't.
- **Sentiment:** `sentiment_score` left null. A later sub-project decides whether to add it.

---

## 4. Orchestrator (`runner.py`)

```python
async def run_pipeline(
    ctx: StepContext,
    steps: list[Step] | None = None,
) -> PipelineRunSummary:
    run = await ctx.repo.start_run(now=ctx.now())
    ctx.run_id = run.id
    steps = steps or DEFAULT_STEPS

    completed: list[str] = []
    errors: dict[str, dict] = {}
    failed_critical = False

    for step in steps:
        if not step.should_run(ctx):  # e.g., universe step gates on date
            continue
        try:
            result = await step.run(ctx)
            completed.append(step.name)
            if result.per_ticker_failures:
                errors[step.name] = {"per_ticker": result.per_ticker_failures}
        except StepFailure as e:
            errors[step.name] = {"reason": str(e)}
            if step.is_critical:
                failed_critical = True
                break

    status = (
        "failed" if failed_critical
        else "partial" if errors
        else "success"
    )
    await ctx.repo.finish_run(run.id, status=status, completed=completed, errors=errors)
    return PipelineRunSummary(...)
```

`DEFAULT_STEPS = [universe, prices, dividends, options, news]`. Order matters: prices and dividends must run before options (options watchlist needs yield), and universe must run before anything else on an empty DB.

---

## 5. Schema (single Alembic migration)

| Table | Key columns | Notes |
|---|---|---|
| `stocks` | `ticker (PK)`, `name`, `sector`, `industry`, `active`, `added_at`, `removed_at` | Index on `active`. |
| `prices` | `(ticker, date) PK`, `open/high/low/close/adj_close NUMERIC(12,4)`, `volume BIGINT` | Index on `date`. |
| `dividend_history` | `(ticker, ex_date) PK`, `pay_date`, `amount_per_share NUMERIC(12,6)`, `frequency` | Frequency may be null in v1. |
| `options_chains` | `id PK`, `ticker FK`, `expiration_date`, `strike NUMERIC(10,2)`, `option_type`, `bid/ask/last NUMERIC(10,4)` nullable, `implied_volatility NUMERIC(8,6)` nullable, `volume`, `open_interest`, `snapshot_at` | Daily insert (not upsert). Indexes: `(ticker, snapshot_at)`, `(ticker, expiration_date, strike, option_type)`. |
| `news_items` | `id PK`, `ticker FK`, `url TEXT UNIQUE`, `title`, `summary`, `source`, `published_at`, `sentiment_score` nullable, `raw_payload JSONB` | Index on `(ticker, published_at DESC)`. |
| `pipeline_runs` | `id PK`, `started_at`, `finished_at` nullable, `status`, `steps_completed TEXT[]`, `errors JSONB`, `llm_tokens_used` nullable, `llm_cost_usd NUMERIC(10,4)` nullable | Index on `started_at DESC`. |

Foreign keys from `prices`, `dividend_history`, `options_chains`, `news_items` to `stocks.ticker` are `ON DELETE RESTRICT`. We never delete from `stocks` (delisting flips `active`).

Single migration file: all six tables created atomically. Subsequent sub-projects add their own migrations.

---

## 6. HTTP API

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/pipeline/runs?limit=30` | Last N runs ordered by `started_at DESC`. Each row: `{id, started_at, finished_at, status, steps_completed, error_count}`. |
| `GET` | `/pipeline/runs/{id}` | Full run record including `errors` JSONB. |
| `POST` | `/pipeline/run` | Trigger full pipeline. Returns `{run_id}` immediately; pipeline runs in background. |
| `POST` | `/pipeline/run?step=<name>` | Trigger a single step. Same response shape. |

Background execution uses FastAPI's `BackgroundTasks` (in-process; fine for a personal app and consistent with APScheduler running in the same process). The endpoint inserts the `pipeline_runs` row synchronously so the caller has a `run_id` to poll.

---

## 7. Scheduler

`scheduler.py` exposes `start(app)` and `stop()` invoked from FastAPI's `lifespan` context. Internally uses `AsyncIOScheduler` with one job:

```python
scheduler.add_job(
    func=run_pipeline_wrapper,
    trigger=CronTrigger(
        day_of_week="mon-fri",
        hour=17, minute=15,
        timezone="America/New_York",
    ),
    id="daily_pipeline",
    replace_existing=True,
    coalesce=True,
    misfire_grace_time=3600,
)
```

`coalesce=True` + `misfire_grace_time=3600` means a missed run (process restart at 17:14) coalesces into one execution if started within an hour. No clustering, no jobstore persistence — the cron is stateless enough to recompute on restart.

---

## 8. CLI

`python -m app.pipeline ...` for ad-hoc and backfill use:

| Command | Purpose |
|---|---|
| `python -m app.pipeline run` | Same as `POST /pipeline/run`, but blocking and printing the summary. |
| `python -m app.pipeline run --step prices` | Run a single step. |
| `python -m app.pipeline backfill` | Special mode: forces prices and dividends to fetch 5 years of history. Run once after the initial migration. |

The CLI shares the same `StepContext` wiring as the HTTP path.

---

## 9. Error handling & retries

- **Per-ticker fault isolation** in every step. A single ticker's failure produces `(ticker, err_str)` and the step keeps going.
- **Per-call retries:** 3× exponential backoff (1s, 2s, 4s) for yfinance; 2× for RSS. Implemented as an inline `async def retry(...)` helper, not a library.
- **Step-level failure** only triggered by:
  - Prices step: <80% of tickers succeeded → `StepFailure`, run status = `failed`.
  - Any other step: never. They always complete; failures are recorded in `pipeline_runs.errors`.
- **Logging:** structured JSON via stdlib logging. Events: step start, step end, per-ticker failure, retry exhaustion. No per-ticker success spam.

---

## 10. Testing strategy

```
backend/tests/
  test_sources_fakes.py             # InMemory* sources behave per protocol
  pipeline/
    test_runner.py                  # orchestrator records pipeline_runs correctly
    test_step_universe.py           # stocks populated; missing tickers deactivated
    test_step_prices.py             # per-ticker isolation; <80% trips StepFailure
    test_step_dividends.py          # upsert idempotency
    test_step_options.py            # watchlist limited to top-50-by-yield + holdings
    test_step_news.py               # URL dedupe across runs
  test_pipeline_api.py              # POST /pipeline/run → run_id, GET reflects state
  test_yfinance_integration.py      # @pytest.mark.slow, skipped by default; one real ticker (KO)
  test_migration_ingestion.py       # alembic upgrade creates all six tables
```

Existing tests (config, db, health, alembic) continue to pass unchanged.

**Coverage target:** every step has happy-path, one-ticker-fails, and all-fail-degrades cases. The integration test boots FastAPI with fake sources and asserts the `pipeline_runs` row reflects the right outcome.

---

## 11. Operational notes

**First-run sequence after migration:**

```bash
# Inside the api container, or via host venv:
python -m app.pipeline backfill              # ~3-5 min: 5yr prices + dividends for ~500 tickers
```

After backfill, the daily scheduler takes over. Backfill is idempotent — safe to re-run.

**Disk impact (rough):**

- 5yr prices: ~630k rows × ~80 bytes ≈ 50 MB.
- Dividend history: ~50k rows × ~50 bytes ≈ 3 MB.
- Options snapshots: ~15k rows/day × 30 days × ~120 bytes ≈ 55 MB/month.
- News: ~100 items/day × ~1 KB ≈ 100 KB/day, ~3 MB/month.

Combined first-month footprint: ~110 MB. Multi-year retention is acceptable on a personal-machine Postgres.

**LLM cost:** zero in this sub-project. The `pipeline_runs.llm_tokens_used` / `llm_cost_usd` columns stay null.

---

## 12. Open questions deferred to later sub-projects

- **Real watchlist ranking** — replace "top 50 by yield" with screener-driven `dividend_quality_score` ordering when Sub-project 3 lands.
- **Sentiment scoring on news items** — null in v1; decide later whether the dashboard needs it.
- **Paid news API** — design spec mentions optional v1.5 paid source. Not addressed here; the `NewsSource` protocol makes it a drop-in.
- **Pipeline run pruning** — `pipeline_runs` will accumulate over years. No retention policy in v1; add a `cleanup_pipeline_runs` step later if it matters.
