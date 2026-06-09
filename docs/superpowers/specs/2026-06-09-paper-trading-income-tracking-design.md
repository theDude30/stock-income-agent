# Paper Trading & Income Tracking — Sub-project 4 Design

**Date:** 2026-06-09
**Depends on:** Sub-projects 1–3 — the FastAPI app, async SQLAlchemy, Alembic, the pipeline runner/step framework, the `recommendations` table and `PipelineRepo`, and the `LLMClient` seam.

---

## 1. What this sub-project delivers

Sub-project 3 left the pipeline able to write `pending` recommendations but unable to act on them. This sub-project closes the loop: approved recommendations become paper trades, open positions are tracked, income events are recorded, and the portfolio is queryable via REST.

After this sub-project, the full daily pipeline runs end-to-end:

```
Ingestion → Screener → SafetyAnalyst → OptionsRecommender → Recommender
  → Executor → IncomeTracker
```

**Explicitly out of scope (Sub-project 5):**
- Weekly Learner, `agent_lessons` table, active-lessons injection
- Notifier / email alerts
- `alerts` table
- React dashboard wiring
- `GET /lessons`, `GET /feedback`, `POST /lessons/{id}/ignore` API endpoints

---

## 2. New database tables (4)

### PK type convention

Sub-project 2 used `BIGINT` PKs (pipeline_runs, news_items, options_chains). Sub-project 3 used `INTEGER` PKs (fundamentals, screenings, dividend_safety_scores, recommendations) — a known inconsistency. **Sub-project 4 uses `INTEGER` PKs** for all four new tables to match the recommendation table it FKs against (recommendations.id is INTEGER), avoiding FK type mismatches. This means `positions.recommendation_id`, `trades.position_id`, `income_events.source_recommendation_id`, and `feedback.recommendation_id` all use INTEGER, consistent with their referenced tables. Migrating to BIGINT across all tables is deferred to a future cleanup.

All tables use `ON DELETE RESTRICT` FKs to `stocks.ticker`, append-only ledgers where noted.

### `positions` — Open paper positions
```
id                INTEGER PK (autoincrement)
ticker            TEXT FK → stocks.ticker ON DELETE RESTRICT
recommendation_id INTEGER FK → recommendations.id ON DELETE RESTRICT
kind              TEXT CHECK IN ('stock', 'short_call')
shares            NUMERIC NOT NULL          -- shares for stock; contracts for options
avg_entry_price   NUMERIC NOT NULL          -- per-share cost basis OR per-share premium received (NOT total dollars)
strike            NUMERIC NULL              -- options only
expiration_date   DATE NULL                 -- options only
opened_at         TIMESTAMPTZ NOT NULL
status            TEXT CHECK IN ('open', 'closed', 'assigned', 'expired') DEFAULT 'open'
closed_at         TIMESTAMPTZ NULL
```

### `trades` — Append-only ledger
```
id                  INTEGER PK (autoincrement)
position_id         INTEGER FK → positions.id ON DELETE RESTRICT
ticker              TEXT FK → stocks.ticker ON DELETE RESTRICT
side                TEXT CHECK IN ('buy', 'sell', 'sell_to_open', 'buy_to_close', 'assign', 'expire')
shares_or_contracts NUMERIC NOT NULL
price               NUMERIC NOT NULL        -- per-share / per-contract-share price
executed_at         TIMESTAMPTZ NOT NULL
reason              TEXT CHECK IN ('recommendation', 'expiration', 'assignment', 'roll', 'manual_close')
```

Note: `short_put`, `exercise`, `target_hit`, `stop_hit` trade sides/reasons from the master spec are not used in Sub-project 4 (puts and target/stop exits are out of scope).

### `income_events` — Append-only income ledger
```
id                        INTEGER PK (autoincrement)
ticker                    TEXT FK → stocks.ticker ON DELETE RESTRICT
type                      TEXT CHECK IN ('dividend', 'call_premium', 'assignment_gain')
amount                    NUMERIC NOT NULL          -- TOTAL DOLLARS (not per-share)
event_date                DATE NOT NULL
source_position_id        INTEGER FK → positions.id NULL
source_recommendation_id  INTEGER FK → recommendations.id NULL
created_at                TIMESTAMPTZ NOT NULL
```

**Unique constraint** on `(ticker, event_date, type, source_position_id)` with `NULLS NOT DISTINCT` for `source_position_id`. This prevents double-booking a dividend for the same position on the same day (the idempotency key), while allowing two different positions to book a premium on the same ticker+date. Use `ON CONFLICT DO NOTHING` in repo inserts — do NOT use a SELECT-then-INSERT check (racy).

### `feedback` — Per-closed-position post-mortem
```
id                  INTEGER PK (autoincrement)
recommendation_id   INTEGER FK → recommendations.id ON DELETE RESTRICT
position_id         INTEGER FK → positions.id ON DELETE RESTRICT
entry_price         NUMERIC NOT NULL        -- per-share
exit_price          NUMERIC NULL            -- per-share; null for short_call at expiry (exit = strike or 0)
capital_pnl         NUMERIC NOT NULL        -- total dollars: (exit_price - entry_price) * shares
dividends_received  NUMERIC NOT NULL DEFAULT 0    -- total dollars
premiums_collected  NUMERIC NOT NULL DEFAULT 0    -- total dollars (premium × 100 × contracts)
total_return_pct    NUMERIC NOT NULL        -- (capital_pnl + dividends + premiums) / cost_basis
held_days           INTEGER NOT NULL
outcome             TEXT CHECK IN ('win', 'loss', 'breakeven')
exit_reason         TEXT NOT NULL
lessons             TEXT NULL               -- reserved for Sub-project 5 LLM post-mortem
created_at          TIMESTAMPTZ NOT NULL
```

**Money unit convention (important):** `income_events.amount`, `feedback.capital_pnl/dividends_received/premiums_collected` are **total dollars**. `positions.avg_entry_price`, `trades.price` are **per-share** (per-contract-share for options). The pure analysis functions in `app/analysis/portfolio.py` accept and return total dollars unless explicitly documented otherwise.

---

## 3. Pipeline steps

### Step 6 — ExecutorStep

**Selection and idempotency:** Reads `recommendations WHERE status='approved'` using `approved_unexecuted_recs()`. Each rec is processed in an isolated try/except block; the status flip to `executed` and its side-effect inserts (position, trade, income_event) are committed together atomically in the session. The idempotency guard is the `executed` status — a re-run skips anything already flipped. This is uniform across all rec types.

- **`add_position`**: Fetch latest close price from `prices` table. Use `payload.get('target_shares', 10)` for shares. Insert `position(kind='stock')`, `trade(side='buy')`, mark rec `status='executed'`.
- **`sell_covered_call`**: Read `strike`, `expiration_date`, `expected_premium` from payload. Insert `position(kind='short_call', avg_entry_price=premium_per_share)`, `trade(side='sell_to_open')`, `income_event(type='call_premium', amount=premium * 100)` (one contract = 100 shares), mark rec `status='executed'`.
- **`sell_position`**: Read `position_id` from `payload['position_id']` — **must not** use `list_open_positions(ticker)[0]` because multiple open positions per ticker are possible. Fetch that position, get latest close. Insert `trade(side='sell')`, `feedback`, close position (status='closed'), mark rec `status='executed'`. Error/skip if position not found or not open.
- Other rec types (`roll_call`, `rebalance`): log and skip — not implemented in SP4.

`is_critical = False`. Per-ticker errors logged; step never fails the run.

### Step 7 — IncomeTrackerStep

Runs after ExecutorStep. Inspects all open positions:

**Dividend tracking (stock positions):**
- For each open stock position, query `dividend_history` for ex-dates **strictly after** `opened_at::date` (exclusive lower bound — holding on ex-date does not entitle the holder; you must own shares *before* the ex-date) and ≤ today.
- For each qualifying dividend, use `ON CONFLICT DO NOTHING` on the unique constraint — no separate exists-check needed.
- `income_event.amount = amount_per_share * position.shares` (total dollars).

**Call expiry/assignment (short_call positions):**
- For calls where `expiration_date = today`:
  - **OTM (close < strike):** call expired worthless. Insert `trade(side='expire', price=0)`, close call position (status='expired'), insert `feedback` (premium already booked; `capital_pnl=0`, `premiums_collected = avg_entry_price * 100`, `total_return_pct = premiums_collected / (underlying_cost_basis)` if stock position exists else `premium / (avg_entry_price * 100)`, `outcome='win'`).
  - **ITM (close ≥ strike):** assignment. Find the associated stock position via `recommendation_id` link (the `sell_covered_call` rec should have the stock ticker; find open stock position for same ticker). Insert `trade(side='assign', price=strike)` on call position, close call position (status='assigned'), close stock position (status='assigned'). If `strike > stock_pos.avg_entry_price`: insert `income_event(type='assignment_gain', amount=(strike - avg_entry_price) * shares)`. Insert `feedback` with `capital_pnl = (strike - avg_entry_price) * shares`, `premiums_collected = call_pos.avg_entry_price * 100`, `outcome='win'` if total return > 0 else 'loss'.

**Roll detection:**
- Calls with `expiration_date` within 5 days where `close ≥ strike × 1.02` (deep ITM): write a pending `sell_covered_call` rec (type `'sell_covered_call'`, not `'roll_call'`) using `insert_recommendation`. The master spec defines `roll_call` as a distinct type, but SP3 deferred it and SP4 implements roll-detection by re-using `sell_covered_call` — this is a deliberate simplification. `roll_call` remains defined in the schema CHECK constraint but unused in SP4.

`is_critical = False`.

---

## 4. REST API

### `app/api/portfolio.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/portfolio/holdings` | Open stock positions with latest close (`price_date` included in response so caller knows the as-of date), unrealized P&L, active covered call if any |
| `GET` | `/portfolio/income?from=&to=` | Income events in date range, totalled by type |
| `GET` | `/portfolio/income/calendar?days=30` | Upcoming expected dividends (from dividend_history for held tickers) + calls expiring within N days |
| `GET` | `/portfolio/performance` | Realized income YTD, portfolio cost basis, SPY close-price return proxy (close-price only, no dividend reinvestment — **partial honesty view**; full SPY total-return + Treasury baseline lands in Sub-project 5) |

`GET /portfolio/live` (mark-to-market with 2-minute yfinance price cache) is deferred to Sub-project 5 — only meaningful when the React dashboard is wired. `/portfolio/holdings` uses latest DB close price; the response includes `price_date` so consumers know the staleness.

### `app/api/trades.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/trades?from=&to=` | Append-only trade ledger, optional date filter |
| `GET` | `/positions?status=` | All positions, optionally filtered by status |
| `GET` | `/positions/{id}` | Position detail with all trades and income events |

---

## 5. PipelineRepo additions

New methods added to `app/pipeline/repo.py`. Convention: identifiers first, scalar fields next, `now` last (matching established pattern). `type_` (trailing underscore) avoids shadowing the Python builtin.

```python
# positions
async def open_position(self, rec_id: int, ticker: str, kind: str, shares: Decimal,
    avg_entry_price: Decimal, strike: Decimal | None, expiration_date: date | None,
    now: datetime) -> int                              # returns new position id

async def close_position(self, position_id: int, status: str, now: datetime) -> None

async def list_open_positions(self, ticker: str | None = None,
    kind: str | None = None) -> list[Position]        # filters are ANDed

async def get_position(self, position_id: int) -> Position | None

# trades
async def insert_trade(self, position_id: int, ticker: str, side: str,
    shares_or_contracts: Decimal, price: Decimal, reason: str, now: datetime) -> int

async def list_trades(self, from_: date | None = None, to: date | None = None) -> list[Trade]

# income events — use ON CONFLICT DO NOTHING on unique constraint
async def insert_income_event(self, ticker: str, type_: str, amount: Decimal,
    event_date: date, source_position_id: int | None,
    source_recommendation_id: int | None, now: datetime) -> int | None  # None = conflict/skipped

async def list_income_events(self, from_: date | None = None,
    to: date | None = None) -> list[IncomeEvent]

# feedback
async def insert_feedback(self, rec_id: int, position_id: int, entry_price: Decimal,
    exit_price: Decimal | None, capital_pnl: Decimal, dividends_received: Decimal,
    premiums_collected: Decimal, total_return_pct: Decimal, held_days: int,
    outcome: str, exit_reason: str, now: datetime) -> int

# executor helpers
async def approved_unexecuted_recs(self) -> list[Recommendation]  # status='approved'
async def mark_rec_executed(self, rec_id: int) -> None            # direct UPDATE, no pending gate

# income tracker helpers
async def open_calls_expiring_on(self, expiry_date: date) -> list[Position]
async def dividends_since(self, ticker: str, since_date: date) -> list[DividendHistory]
    # WHERE ex_date > since_date (exclusive — must own BEFORE ex-date to receive dividend)
```

**Update to existing method:**
```python
async def held_tickers(self) -> list[str]:
    # Was: return []  (placeholder since SP3)
    # Now: SELECT DISTINCT ticker FROM positions WHERE status='open' AND kind='stock'
```

**Activation note:** Updating `held_tickers()` activates two dormant code paths starting on the *next* pipeline run after SP4 deploys:
1. `OptionsRecommenderStep` iterates held tickers for covered-call candidates.
2. `RecommenderStep` skips already-held tickers for `add_position`.
This is correct behavior (you can't write a covered-call rec for a position that was just opened in the same run — Executor runs after Recommender).

---

## 6. Pure analysis logic

`app/analysis/portfolio.py` — no DB/network, all pure functions. All money inputs/outputs are **total dollars** unless documented per-share.

```python
def compute_capital_pnl(entry_price: Decimal, exit_price: Decimal, shares: Decimal) -> Decimal
    # (exit_price - entry_price) * shares  — per-share inputs, total-dollar output

def compute_covered_call_return_pct(premium_total: Decimal, cost_basis: Decimal) -> Decimal
    # premium_total / cost_basis  — used for OTM expiry feedback total_return_pct
    # cost_basis = avg_entry_price * shares of underlying

def compute_total_return_pct(capital_pnl: Decimal, dividends: Decimal,
    premiums: Decimal, cost_basis: Decimal) -> Decimal
    # (capital_pnl + dividends + premiums) / cost_basis

def classify_outcome(total_return_pct: Decimal) -> str
    # >0 → 'win', <0 → 'loss', ==0 → 'breakeven'

def is_call_itm(strike: Decimal, close_price: Decimal) -> bool
    # close_price >= strike

def compute_assignment_gain(strike: Decimal, avg_entry_price: Decimal, shares: Decimal) -> Decimal
    # (strike - avg_entry_price) * shares  — 0 if strike <= avg_entry_price
```

---

## 7. Default pipeline step order (updated)

```python
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
        ExecutorStep(),       # NEW
        IncomeTrackerStep(),  # NEW
    ]
```

---

## 8. Key design decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | INTEGER PKs for new tables | `recommendations.id` (the primary FK target) is INTEGER (SP3 choice). Mixing BIGINT PKs with INTEGER FKs is valid SQL but confusing. Consistent INTEGER throughout SP4; BIGINT migration is future cleanup. |
| 2 | Execution price = latest close from `prices` | Pipeline runs at 17:15 ET after market close. Same-day close is the most accurate paper-trade price without a real-time feed. |
| 3 | Call premium income event at position open | Premium is received when the call is sold. Expiry/assignment closes the position; no new income event needed then (premium already booked). |
| 4 | `feedback.total_return_pct` for OTM call = `premium_total / cost_basis` | Recording 0 would misclassify a successful covered call as 'breakeven' and corrupt SP5 hit-rate stats. The real formula is premium yield against the underlying cost basis. |
| 5 | Money units: `income_events.amount` and `feedback.*_pnl/received/collected` are total dollars; `positions.avg_entry_price` and `trades.price` are per-share | Consistent with how the master spec describes income tracking. Option premium ×100 is applied at the income_event and feedback layer, not in the position row. |
| 6 | Dividend ex-date boundary is exclusive | Buying on ex-date does not entitle holder to dividend (market convention). `dividends_since` uses `ex_date > opened_at::date` strictly. |
| 7 | Executor idempotency via `status='executed'` flip, atomically committed | SELECT-then-insert is racy. Atomic commit of status flip + inserts; re-run skips anything already executed. Uniform across all rec types. |
| 8 | `sell_position` uses `payload['position_id']`, not ticker lookup | Multiple open positions per ticker are possible (multiple approved `add_position` recs). Payload must carry the specific position_id. SP3's Recommender currently doesn't populate this (dormant); SP4 must set it when wiring the sell path. |
| 9 | DB-level dedup for income events via unique constraint + ON CONFLICT DO NOTHING | SELECT-then-INSERT is racy. Unique constraint on `(ticker, event_date, type, source_position_id)` with NULLS NOT DISTINCT. |
| 10 | `roll_call` rec type not implemented; IncomeTracker writes `sell_covered_call` for rolls | SP3 deferred `roll_call` to SP4 but SP4 collapses roll into `sell_covered_call` for simplicity. The `roll_call` CHECK value exists in the schema but is unused. |
| 11 | `/portfolio/performance` is a partial honesty view in SP4 | SPY close-price proxy only (no dividend reinvestment); 1-month Treasury baseline deferred. Full honesty view (master spec success criterion #2) ships with the dashboard in Sub-project 5. |

---

## 9. Test strategy

- **Pure functions** (`app/analysis/portfolio.py`): unit tests, no DB, no network — fast
- **Repo methods**: integration tests against testcontainer Postgres (same `session`/`pg_container` fixtures as SP3)
- **ExecutorStep**: add_position executed → position+trade+rec-executed; sell_covered_call → call position + income event; sell_position via payload position_id; idempotency (re-run skips executed recs)
- **IncomeTrackerStep**: dividend insertion (strict ex-date boundary), OTM call expiry → feedback with correct return_pct, ITM assignment → positions closed + assignment_gain, duplicate dividend idempotency via unique constraint
- **Portfolio/trades APIs**: HTTPX ASGITransport tests (same pattern as `test_recommendations_api.py` and `test_stocks_api.py`)
- **Migration**: `test_migration_portfolio.py` verifying 4 new tables exist with correct columns

---

## 10. What activates after this sub-project

- **OptionsRecommenderStep** goes live: `held_tickers()` now returns real tickers; `sell_covered_call` recs flow through on the next pipeline run containing open positions.
- **`sell_position`** recommendation type becomes meaningful (positions exist to close).
- **`roll_call`** rec type remains unimplemented (deferred).
- The pipeline is fully end-to-end operational. `POST /pipeline/run` triggers all 12 steps.
