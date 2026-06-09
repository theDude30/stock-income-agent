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

All follow the established conventions: `BIGINT` PKs, `ON DELETE RESTRICT` FKs to `stocks.ticker`, append-only ledgers where noted.

### `positions` — Open paper positions
```
id              BIGSERIAL PK
ticker          TEXT FK → stocks.ticker ON DELETE RESTRICT
recommendation_id BIGINT FK → recommendations.id ON DELETE RESTRICT
kind            TEXT CHECK IN ('stock', 'short_call')
shares          NUMERIC NOT NULL          -- shares for stock; contracts for options
avg_entry_price NUMERIC NOT NULL          -- cost basis per share / premium received per contract
strike          NUMERIC NULL              -- options only
expiration_date DATE NULL                 -- options only
opened_at       TIMESTAMPTZ NOT NULL
status          TEXT CHECK IN ('open', 'closed', 'assigned', 'expired') DEFAULT 'open'
closed_at       TIMESTAMPTZ NULL
```

### `trades` — Append-only ledger
```
id                  BIGSERIAL PK
position_id         BIGINT FK → positions.id ON DELETE RESTRICT
ticker              TEXT FK → stocks.ticker ON DELETE RESTRICT
side                TEXT CHECK IN ('buy', 'sell', 'sell_to_open', 'buy_to_close', 'assign', 'expire')
shares_or_contracts NUMERIC NOT NULL
price               NUMERIC NOT NULL
executed_at         TIMESTAMPTZ NOT NULL
reason              TEXT CHECK IN ('recommendation', 'expiration', 'assignment', 'roll', 'manual_close')
```

### `income_events` — Append-only income ledger
```
id                      BIGSERIAL PK
ticker                  TEXT FK → stocks.ticker ON DELETE RESTRICT
type                    TEXT CHECK IN ('dividend', 'call_premium', 'assignment_gain')
amount                  NUMERIC NOT NULL
event_date              DATE NOT NULL
source_position_id      BIGINT FK → positions.id NULL
source_recommendation_id BIGINT FK → recommendations.id NULL
created_at              TIMESTAMPTZ NOT NULL
```

### `feedback` — Per-closed-position post-mortem
```
id                  BIGSERIAL PK
recommendation_id   BIGINT FK → recommendations.id ON DELETE RESTRICT
position_id         BIGINT FK → positions.id ON DELETE RESTRICT
entry_price         NUMERIC NOT NULL
exit_price          NUMERIC NULL       -- null if still open at recording time
capital_pnl         NUMERIC NOT NULL   -- (exit_price - entry_price) * shares
dividends_received  NUMERIC NOT NULL DEFAULT 0
premiums_collected  NUMERIC NOT NULL DEFAULT 0
total_return_pct    NUMERIC NOT NULL
held_days           INTEGER NOT NULL
outcome             TEXT CHECK IN ('win', 'loss', 'breakeven')
exit_reason         TEXT NOT NULL
created_at          TIMESTAMPTZ NOT NULL
```

---

## 3. Pipeline steps

### Step 6 — ExecutorStep

Reads `recommendations WHERE status='approved'` that have no corresponding position yet. For each:

- **`add_position`**: use the latest available close price from `prices` as the execution price (paper-trade simplification — execution is simulated at previous close; noted in the trade's `reason`). Insert `trade(side='buy')`, open `position(kind='stock')`, mark recommendation `status='executed'`.
- **`sell_covered_call`**: record `income_event(type='call_premium')` for the expected premium from the rec's payload, open `position(kind='short_call')`, mark rec `status='executed'`.
- **`sell_position`**: close the matching open stock position, insert `trade(side='sell')` at latest close price, insert `feedback` row, mark rec `status='executed'`.

The Executor is **intentionally dumb** — it only acts on already-approved recs. The Phase-2 transition (auto-approval) is a config flag change in the Recommender, not an Executor change.

`is_critical = False`. Per-ticker errors are caught and logged; the step never fails the run.

### Step 7 — IncomeTrackerStep

Runs after ExecutorStep. Inspects all open positions:

**Dividend tracking (stock positions):**
- For each open stock position, check `dividend_history` for ex-dates that fall today or were missed since the position opened.
- Insert `income_event(type='dividend')` for each qualifying dividend (amount = `dividend_history.amount_per_share * position.shares`).
- Idempotent: skip if an income event for `(ticker, event_date, type='dividend')` already exists.

**Call expiry/assignment (short_call positions):**
- For calls expiring today:
  - Compare strike to latest close price.
  - **OTM (close < strike):** call expired worthless. Insert `trade(side='expire')`, close position (status='expired'), create `feedback` row. Premium was already recorded as `income_event` at open time.
  - **ITM (close ≥ strike):** assignment. Insert `trade(side='assign')` for the underlying shares at strike price, close the call position (status='assigned'), close the stock position (status='assigned'), create `feedback` row. Insert `income_event(type='assignment_gain')` if `strike > avg_entry_price`.

**Roll detection:**
- Calls expiring within 5 days that are deep ITM (close ≥ strike × 1.02) get a `sell_covered_call` recommendation written with `reasoning` noting the roll context. (Recommender already handles the logic; IncomeTracker just triggers it by writing the pending rec.)

`is_critical = False`.

---

## 4. REST API

### `app/api/portfolio.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/portfolio/holdings` | Open stock positions with latest close price, unrealized P&L, yield, active covered call |
| `GET` | `/portfolio/income?from=&to=` | Income events in date range, grouped by type |
| `GET` | `/portfolio/income/calendar?days=30` | Upcoming expected dividends (from dividend_history) + calls expiring within N days |
| `GET` | `/portfolio/performance` | Realized income YTD, total return vs SPY close-price proxy, portfolio cost basis |

`GET /portfolio/live` (mark-to-market with 2-minute price cache) is deferred to Sub-project 5 when the React dashboard is wired up — for now `/portfolio/holdings` uses the latest `prices` row.

### `app/api/trades.py`

| Method | Path | Description |
|---|---|---|
| `GET` | `/trades?from=&to=` | Append-only trade ledger, optional date filter |
| `GET` | `/positions?status=` | All positions, optionally filtered by status (open/closed/assigned/expired) |
| `GET` | `/positions/{id}` | Position detail with all trades and income events |

---

## 5. PipelineRepo additions

New methods added to `app/pipeline/repo.py`:

```python
# positions
async def open_position(rec_id, ticker, kind, shares, avg_entry_price, strike, expiration_date, now) -> int
async def close_position(position_id, status, now) -> None
async def list_open_positions(ticker=None) -> list[Position]
async def get_position(position_id) -> Position | None

# trades
async def insert_trade(position_id, ticker, side, shares_or_contracts, price, reason, now) -> int
async def list_trades(from_=None, to=None) -> list[Trade]

# income events
async def insert_income_event(ticker, type_, amount, event_date, source_position_id, source_recommendation_id, now) -> int
async def list_income_events(from_=None, to=None) -> list[IncomeEvent]
async def income_event_exists(ticker, event_date, type_) -> bool

# feedback
async def insert_feedback(rec_id, position_id, entry_price, exit_price, capital_pnl, dividends_received, premiums_collected, total_return_pct, held_days, outcome, exit_reason, now) -> int

# executor helpers
async def approved_unexecuted_recs() -> list[Recommendation]
async def executed_recommendation_ids() -> set[int]

# income tracker helpers
async def open_calls_expiring_on(date) -> list[Position]
async def dividends_since(ticker, since_date) -> list[DividendHistory]
```

---

## 6. Pure analysis logic

`app/analysis/portfolio.py` — no DB/network, all pure functions:

```python
def compute_capital_pnl(entry_price, exit_price, shares) -> Decimal
def compute_total_return_pct(capital_pnl, dividends, premiums, cost_basis) -> Decimal
def classify_outcome(total_return_pct) -> str   # 'win' | 'loss' | 'breakeven'
def is_call_itm(strike, close_price) -> bool
def compute_assignment_gain(strike, avg_entry_price, shares) -> Decimal
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
| 1 | Execution price = latest close from `prices` table | Pipeline runs at 17:15 ET after close. Using the same day's close is the most accurate paper-trade price available without a real-time feed. Avoids extra yfinance calls at execution time. |
| 2 | `income_event` for call premium written at open, not expiry | Premium is received when the call is sold; recording it at open is accurate. Expiry closes the position (OTM) or triggers assignment (ITM) — no new income event needed at that point (already booked). |
| 3 | `feedback` written on position close only | Keeps `feedback` as a closed-position post-mortem rather than an ongoing mark. The dashboard's Holdings tab computes unrealized P&L on-the-fly from latest prices. |
| 4 | No `agent_lessons` table in this sub-project | The `SafetyStep` prompt builder already accepts `active_lessons=[]`; that stays empty until Sub-project 5 builds the Weekly Learner. No schema migration needed here for that. |
| 5 | `/portfolio/live` deferred to Sub-project 5 | Requires a real-time price cache (2-min TTL yfinance calls per position). Only valuable when the dashboard is live. `/portfolio/holdings` using latest close is sufficient for API testing now. |
| 6 | Roll recommendation written by IncomeTracker, not a new step | The Recommender already writes `sell_covered_call` recs; IncomeTracker can write a `sell_covered_call` rec with a roll-context payload using the same `insert_recommendation` repo method. No new step needed. |

---

## 9. Test strategy

Following the established pattern:

- **Pure functions** (`app/analysis/portfolio.py`): unit tests, no DB, no network — fast
- **Repo methods**: integration tests against testcontainer Postgres (same `session`/`pg_container` fixtures)
- **ExecutorStep**: test happy path (add_position executed → position opened), sell_covered_call execution, sell_position execution, idempotency (re-running doesn't double-execute)
- **IncomeTrackerStep**: dividend insertion, OTM expiry, ITM assignment, duplicate-event idempotency
- **Portfolio/trades APIs**: HTTPX ASGITransport tests against real DB (same pattern as `test_recommendations_api.py`)
- **Migration**: `test_migration_portfolio.py` verifying 5 new tables exist with correct columns

---

## 10. What activates after this sub-project

- **OptionsRecommenderStep** goes live: it already queries `held_tickers()` which returns `[]` today. Once `positions` is populated, `held_tickers()` returns real tickers and `sell_covered_call` recommendations flow through.
- **`sell_position` and `roll_call`** recommendation types become meaningful (positions exist to sell/roll).
- The pipeline is fully end-to-end operational. Running `POST /pipeline/run` triggers all 12 steps.
