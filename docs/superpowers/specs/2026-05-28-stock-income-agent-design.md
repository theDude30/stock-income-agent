# Stock Income Agent — Design Spec

**Date:** 2026-05-28
**Author:** Tzahi Bergman (with Claude as design collaborator)
**Status:** Draft — pending user review

---

## 1. Goal

Build a personal, self-hosted agent that generates **recurring monthly income** from a paper-traded (later real) S&P 500 stock portfolio, using a **dividend portfolio + covered-call writing** strategy. The agent ingests market data, news, and fundamentals; produces concrete recommendations (which stocks to buy, which positions to exit, which covered calls to sell, at which strike); simulates trades in a paper portfolio; tracks realized income over time; and learns from outcomes.

### Why income, not capital appreciation
Predicting which stocks will rise short-term is a problem dominated by institutional investors with structural advantages. **Income strategies** (dividends + covered calls) play to LLM strengths (synthesizing fundamentals, flagging deterioration, scoring sustainability) and produce more predictable, measurable outcomes. The probability of generating *some* monthly income is high (~85–95%); the probability of meaningfully beating SPY total return is lower but real (~30–40%).

### Phasing
- **Phase 1 (this spec):** Human-in-the-loop. The agent proposes; the user approves; paper trades execute against real market data. Outcomes tracked over time.
- **Phase 2 (later):** Same code; flip a config flag to enable auto-execution of approved recommendation types. Live trading via broker API is a Phase 3+ concern, deliberately out of scope here.

### Non-goals (v1)
- Day trading or intraday signals
- Public deployment, multi-user, authentication
- Universes beyond S&P 500
- Crypto, futures, fixed income
- Tax-lot accounting, wash-sale tracking
- Real broker integration

---

## 2. Success criteria

1. **Operational:** Pipeline runs reliably each weekday evening; failures are isolated per-ticker; dashboard is accessible at localhost; all components run in Docker Compose with one `docker compose up`.
2. **Honest reporting:** Every performance view includes an SPY total-return benchmark line and a 1-month Treasury baseline. The user can always answer "would I be better off just buying SPY?"
3. **Useful recommendations:** After 3 months of paper trading, ≥60% of high-confidence dividend safety scores correctly predicted dividend continuity; ≥70% of covered calls expired worthless or at modest assignment (the win conditions).
4. **Learning is measurable:** The `agent_lessons` table accumulates non-empty, falsifiable patterns; lessons backed by ≥5 closed positions are visible on the Settings tab; user can mark lessons as ignored.
5. **Cost predictable:** Steady-state run cost ≤ $15/month including LLM tokens, with free data feeds.

---

## 3. Stock universe

**v1:** S&P 500 constituents only. Refreshed monthly from a public source (Wikipedia + cross-check against S&P's published list).

**Future expansion (out of v1 scope but designed for):** S&P 1500 with liquidity filters (avg daily volume > $1M, market cap > $500M). The `stocks` table is universe-agnostic — adding a new universe is a config + loader change, not a schema change.

---

## 4. Architecture

**Approach A — Monolithic FastAPI service.** One Python service contains scheduler, ingestion, scoring engine, LLM orchestration, paper-portfolio logic, and REST API for the React frontend. A separate Postgres container holds all state.

### Containers (docker-compose)
- `api` — FastAPI + APScheduler running the daily pipeline in-process
- `web` — React build served by nginx
- `db` — PostgreSQL 16

### Decision/Execution split (the Phase 1→2 seam)
The pipeline writes `Recommendation` records. A separate `Executor` module reads `recommendations WHERE status='approved'` and turns them into paper trades. In Phase 1, only the user can move a recommendation to `approved` (via the dashboard). In Phase 2, a config flag causes new recommendations of opted-in types to be auto-approved by the system. **No code rewrite is required for the transition.**

### Live portfolio view
On dashboard load, the API enriches open positions with latest prices from yfinance (per-ticker 2-minute cache to avoid hammering the source). Mark-to-market P&L is computed on the fly; persisted portfolio snapshots are recorded once daily after the pipeline.

```
                                ┌──────────────────────────────────┐
                                │  React Dashboard                 │
                                │  Income overview · Holdings ·    │
                                │  Recommendations · Performance · │
                                │  Settings                        │
                                └──────────────┬───────────────────┘
                                               │ REST
                                ┌──────────────▼───────────────────┐
                                │   FastAPI (api container)        │
                                │   - REST endpoints               │
                                │   - APScheduler (weekday 17:15)  │
                                │   - Pipeline modules:            │
                                │       Ingestion, DividendScreener│
                                │       DividendSafetyAnalyst,     │
                                │       OptionsRecommender,        │
                                │       Recommender, Executor,     │
                                │       IncomeTracker, Learner,    │
                                │       Notifier                   │
                                └──────────────┬───────────────────┘
                                               │ SQL
                                ┌──────────────▼───────────────────┐
                                │  PostgreSQL (db container)       │
                                └──────────────────────────────────┘

  External: yfinance (free) · Yahoo/MarketWatch RSS (free, v1) ·
            paid news/sentiment API (v1.5) · Anthropic API · SMTP
```

### Stack
- **Backend:** Python 3.12, FastAPI, APScheduler, SQLAlchemy 2.x, Alembic (migrations), pydantic
- **Data:** yfinance (prices, dividends, options chains, basic news), free RSS feeds for v1
- **LLM:** Anthropic Claude — Haiku for routine analyst calls, Sonnet for the weekly learning loop
- **Frontend:** React (Vite), TypeScript, TanStack Query, Recharts
- **Database:** PostgreSQL 16
- **Containerization:** Docker Compose
- **Testing:** pytest + testcontainers for Postgres, fake LLM/market clients by default

---

## 5. Data model

11 tables. PK = primary key. FK columns marked.

### `stocks` — S&P 500 universe
`ticker (PK)`, `name`, `sector`, `industry`, `active (bool)`, `added_at`, `removed_at`. Refreshed monthly.

### `prices` — Daily OHLCV
`ticker (FK)`, `date`, `open`, `high`, `low`, `close`, `adj_close`, `volume`. PK = `(ticker, date)`.

### `news_items` — Articles linked to tickers
`id (PK)`, `ticker (FK)`, `published_at`, `source`, `url (unique)`, `title`, `summary`, `sentiment_score (nullable)`, `raw_payload (JSONB)`.

### `dividend_history` — Dividends per stock
`ticker (FK)`, `ex_date`, `pay_date`, `amount_per_share`, `frequency` (`monthly` | `quarterly` | `semiannual` | `annual` | `special`). PK = `(ticker, ex_date)`.

### `options_chains` — Daily options snapshots (holdings + watchlist only)
`id (PK)`, `ticker (FK)`, `expiration_date`, `strike`, `option_type` (`call` | `put`), `bid`, `ask`, `last`, `implied_volatility`, `volume`, `open_interest`, `snapshot_at`.

### `screenings` — Daily output of the dividend screener
`id (PK)`, `run_id`, `ticker (FK)`, `dividend_quality_score`, `signals (JSONB — yield, payout_ratio, fcf_coverage, debt_to_equity, etc.)`, `passed_screen (bool)`, `created_at`.

### `dividend_safety_scores` — LLM safety assessments
`id (PK)`, `ticker (FK)`, `score (0–100)`, `payout_ratio`, `fcf_coverage`, `debt_to_equity`, `consecutive_years_paid`, `concerns (text[])`, `llm_reasoning`, `llm_model`, `llm_prompt_version`, `scored_at`.

### `recommendations` — The agent's picks (centerpiece)
`id (PK)`, `run_id`, `type` (`add_position` | `sell_position` | `rebalance` | `sell_covered_call` | `roll_call`), `ticker (FK)`, `confidence` (`high` | `med` | `low`), `payload (JSONB — type-specific fields)`, `reasoning (text)`, `signals_snapshot (JSONB)`, `llm_model`, `llm_prompt_version`, `status` (`pending` | `approved` | `rejected` | `expired` | `superseded` | `executed`), `approval_mode` (`manual` | `auto`), `decided_by` (`user` | `system`), `decided_at`, `created_at`.

The `payload` shape varies by `type`:
- `add_position`: `{target_shares, target_price (or 'market'), expected_yield}`
- `sell_position`: `{position_id, reason_codes}`
- `sell_covered_call`: `{strike, expiration_date, expected_premium, prob_assignment}`
- `roll_call`: `{old_position_id, new_strike, new_expiration}`

Recommendations are immutable after creation except for `status`, `decided_by`, `decided_at`.

### `positions` — Open paper positions (stocks and options)
`id (PK)`, `ticker (FK)`, `recommendation_id (FK)`, `kind` (`stock` | `short_call` | `short_put`), `shares (or contracts)`, `avg_entry_price (or premium_received)`, `strike (nullable)`, `expiration_date (nullable)`, `opened_at`, `target_price (nullable)`, `stop_price (nullable)`, `status` (`open` | `closed` | `assigned` | `expired`).

### `trades` — Append-only ledger of every paper trade
`id (PK)`, `position_id (FK)`, `ticker (FK)`, `side` (`buy` | `sell` | `sell_to_open` | `buy_to_close` | `assign` | `exercise`), `shares_or_contracts`, `price`, `executed_at`, `reason` (`recommendation` | `target_hit` | `stop_hit` | `expiration` | `assignment` | `manual_close` | `roll`).

### `income_events` — Append-only ledger of all income realized
`id (PK)`, `ticker (FK)`, `type` (`dividend` | `call_premium` | `put_premium` | `assignment_gain`), `amount`, `event_date`, `source_position_id (FK nullable)`, `source_recommendation_id (FK nullable)`. **This is the source of truth for monthly income reporting.**

### `feedback` — Per-closed-position outcome
`id (PK)`, `recommendation_id (FK)`, `entry_price`, `exit_price`, `capital_pnl`, `dividends_received`, `premiums_collected`, `total_return_pct`, `held_days`, `outcome` (`win` | `loss` | `breakeven`), `exit_reason`, `lessons (text — LLM post-mortem)`, `created_at`.

### `agent_lessons` — Distilled patterns the agent has learned
`id (PK)`, `pattern (text)`, `evidence_recommendation_ids (int[])`, `sample_size`, `effective_from`, `effective_until (nullable; null = active)`, `user_ignored (bool)`, `created_at`. Injected into LLM prompts when active.

### `alerts` — Outbound notification log
`id (PK)`, `type` (`new_recommendations` | `dividend_safety_alert` | `dividend_payment_upcoming` | `position_closed` | `call_expiring` | `monthly_summary`), `payload (JSONB)`, `channel` (`email` | `web`), `sent_at`.

### `pipeline_runs` — Operational ledger
`id (PK)`, `started_at`, `finished_at`, `status` (`running` | `success` | `partial` | `failed`), `steps_completed (text[])`, `errors (JSONB)`, `llm_tokens_used`, `llm_cost_usd`.

### Design notes
- `trades` and `income_events` are append-only. Positions are derived state; if reporting ever looks wrong, the ledgers are authoritative.
- Every recommendation captures `llm_prompt_version` and `signals_snapshot` so the learning loop can reason about *exactly* what produced each pick.
- The `agent_lessons.user_ignored` flag is a user-controlled kill switch for individual lessons.

---

## 6. Daily pipeline

Triggered by APScheduler weekdays at **17:15 ET** (after market close, prices settled). Steps run sequentially; each is idempotent and isolated per-ticker so one failure can't block the rest.

### Step 1 — Ingestion *(~1 min)*
- yfinance OHLCV for every S&P 500 ticker → upsert `prices`
- yfinance dividends for changed tickers → upsert `dividend_history`
- yfinance options chains for held + watchlist (~50 names) → insert `options_chains`
- News (free RSS in v1) for held + watchlist → dedupe by URL → insert `news_items`
- Monthly: refresh `stocks` table from S&P 500 source

### Step 2 — DividendScreener *(~5s, in-memory)*
For each S&P 500 ticker with sufficient history:
- Yield = trailing-12mo dividends ÷ current price
- Payout ratio = dividends ÷ earnings (sustainable < 70%)
- FCF coverage = free cash flow ÷ dividends paid (safe ≥ 1.5)
- Consecutive years paid / raised
- Debt-to-equity
- 5yr earnings growth

Composite `dividend_quality_score` (0–100) + flags (`is_aristocrat`, `is_king`, `is_monthly_payer`, `pays_in_cycle_A/B/C`). Top ~30 advance to LLM, plus all current holdings (always re-evaluated).

### Step 3 — DividendSafetyAnalyst LLM *(~30 calls, ~$0.05–0.50/day depending on model)*
For each finalist, prompt the LLM with:
- Last 4 quarters of earnings (revenue, EPS, FCF)
- Last 8 dividend declarations
- Computed safety metrics from Step 2
- Last 7 days of relevant news headlines + summaries
- All currently-active `agent_lessons`

LLM returns structured JSON: `{safety_score, concerns: [...], outlook, reasoning}`. Validated against a Pydantic schema; bad outputs are retried once with stricter instructions, then logged and skipped.

### Step 4 — OptionsRecommender LLM *(only for held tickers with no active call; ~once per holding per week)*
For each eligible holding:
- Pull options chain (30–45 days to expiration)
- Filter to calls 3–7% out of the money
- Score each by premium yield, prob of assignment (from IV), regret-of-assignment
- LLM picks the best strike + expiration with reasoning

Returns: `{strike, expiration, expected_premium, prob_assignment, reasoning}`. Written as `recommendations.type='sell_covered_call'`.

### Step 5 — Recommender
Combines Step 3 and Step 4 outputs into `recommendations` rows of three types:
- `add_position` for high-scoring new candidates not yet held
- `sell_position` for holdings with sharply-deteriorating safety (drop > 15 points week-over-week, or critical LLM concerns)
- `sell_covered_call` for eligible holdings (from Step 4)

All written with `status='pending'`, `approval_mode='manual'` in Phase 1.

### Step 6 — Executor
Reads `recommendations WHERE status='approved' AND no corresponding trade yet`. For each:
- `add_position` → on next session's open price, insert `trade(buy)` + open `position(kind='stock')`
- `sell_position` → on next session's open, insert `trade(sell)`, close `position`, compute `feedback` row
- `sell_covered_call` → record premium received immediately as `income_event(type='call_premium')`, open `position(kind='short_call')`

Executor is intentionally dumb — it only acts on already-approved recs. The Phase-1→2 transition flips a single config flag (`auto_approve.<type>`) which causes the Recommender to write `status='approved'` directly for those types.

### Step 7 — IncomeTracker
For each open position:
- Stocks: if today is an ex-div date, schedule expected income; on pay-date, insert `income_event(type='dividend')`
- Short calls: at expiration, check if in-the-money:
  - OTM at expiration → call expires worthless, position closes, premium kept (already recorded)
  - ITM at expiration → assignment: paper-sell the underlying shares at strike, insert `trade(assign)`, write `feedback` row, possibly trigger an `add_position` rec to re-establish exposure
- Calls approaching expiration deep ITM → recommend `roll_call` (close current call + sell new further-dated, higher-strike call)

### Step 8 — Notifier
Daily email digest (configurable, off by default until SMTP set up):
- New pending recommendations needing review
- Dividend safety alerts: any holding with safety drop > 10 points
- Upcoming dividend payments (next 7 days)
- Calls expiring within 5 days
- On the 1st of each month: monthly income summary

### Learning loop (separate, runs Fridays at 17:30 ET)
After the regular Friday pipeline:
1. Gather past week's `feedback`, `income_events`, `dividend_safety_scores` deltas, user rejections, counterfactuals
2. LLM call (Sonnet — quality matters here) reviews evidence + active lessons; proposes retirements and additions
3. Validation gates: new lessons require sample size ≥ 5, must be falsifiable, can't directly contradict an active lesson with larger sample
4. Adopted lessons get injected into the prompt header of next week's analyst calls
5. Retired lessons keep `effective_until` set (audit trail)

---

## 7. Dashboard

Five tabs in the React UI. **Income, not P&L, is the headline.**

### Tab 1: Income Overview *(default)*
- Cards: projected forward-12mo income, MTD income, trailing-12mo income, current portfolio yield, vs. SPY dividend yield (~1.3%), vs. 1-month Treasury (~5%)
- Main chart: stacked monthly income over time (dividends + premiums + assignments), with SPY-equivalent dividends as comparison line
- Right panel: 30-day income calendar — every expected dividend payment and option expiration

### Tab 2: Holdings
Table of every open position with: ticker, shares, avg cost, current price, % of portfolio, annual yield, projected annual income, DividendQualityScore + trend arrow, active covered call (strike, expiration, premium received), days to next ex-div, last safety LLM review.

Click row → drawer with full LLM reasoning, recent news, dividend history chart, safety score history.

### Tab 3: Recommendations
Pending recommendations grouped by type (`add_position`, `sell_position`, `sell_covered_call`). Each card shows full LLM reasoning and `[Approve]` / `[Reject]` buttons. Approval moves rec to `status='approved'` for Executor to pick up on next pipeline run.

### Tab 4: Performance
- Total return YTD: capital appreciation + income + premiums
- vs. SPY total return (the honesty check)
- vs. 1-month Treasury (do-nothing baseline)
- Realized income: monthly chart, trailing 24 months
- Hit rates: `add_position` outcomes, % of calls expired worthless / assigned / rolled, % of safety warnings that were correct
- Dividend cuts: how many holdings cut dividends; did the agent warn?

### Tab 5: Settings & Agent Status
- Pipeline run history (last 30 runs) with green/yellow/red status, manual re-run per step
- Approval-mode toggles per recommendation type (off in Phase 1)
- Safety rails: daily action cap, max position size %, total exposure cap, kill switch (`auto_execution_enabled`)
- Notification preferences + email config
- API keys (Anthropic, optional paid news API)
- Universe selector (S&P 500 only in v1)
- Active `agent_lessons` viewer — toggle ignored, see retired lessons
- LLM cost month-to-date

---

## 8. Error handling & operational concerns

### Resilience
- **Per-ticker isolation:** Step failures for one ticker never block others
- **Run state tracking:** Every pipeline run gets a `pipeline_runs` row; dashboard surfaces last 30 with status
- **Retries:** yfinance 3× exponential backoff, LLM 2×, JSON-validation 1× with stricter instructions
- **Data quality gates:** Reject prices that change >50% day-over-day; flag options chains with too few strikes; flag dividend amounts >5× historical mean

### Testing
- **Unit tests:** Every pure function in screener, safety metrics, P&L, options scoring. Sub-5s, no DB, no network
- **Integration tests:** Pipeline end-to-end against Postgres testcontainer with fixture data; full state transitions verified; complete dividend and covered-call cycles verified; learning loop produces lessons
- **Fakes by default:** `FakeMarketDataClient` and `FakeLLMClient` return deterministic responses; real services only in `tests/live/` behind env flag
- **Replay tests:** Real pipeline outputs saved as fixtures; replay through system asserts no unexpected changes

### Operations
- Secrets in `.env.local` (not committed); `.env.example` committed
- Structured JSON logs to stdout, captured by Docker; every log carries `run_id`
- Daily `pg_dump` backup from a sidecar container
- LLM token counter per run; dashboard surfaces month-to-date cost
- Local-only by default: `localhost:3000` (web), `localhost:8000` (api), `localhost:5432` (db) — no auth, no public exposure

---

## 9. Cost estimates

### Build
- Time: ~20–30 days of focused work, ~3 months calendar with evenings/weekends
- LLM tokens during dev: realistic range $15–70 depending on working style; budget ~$75 to be safe

### Runtime (steady state)
- LLM: ~$2–5/month using Haiku for routine + Sonnet for weekly learning
- Data: $0 for v1 (free yfinance + RSS); optional ~$30/month paid news API in v1.5
- Hosting: $0 (local Docker); ~$10–30/month if later moved to cloud
- **Total v1 runtime: ~$5/month**

---

## 10. Phase 2 readiness (designed-in, not built)

The following capabilities are designed into the architecture but not exercised in Phase 1:

1. **Auto-approval per recommendation type** — flip `auto_approve.<type>` in settings; Recommender starts writing `status='approved'` directly for that type
2. **Safety rails enforced at the Recommender layer** — daily action cap, position-size cap, total-exposure cap, kill switch — all read from settings on each rec write, regardless of approval mode
3. **Kill switch** — `auto_execution_enabled=false` immediately reverts all auto-approval back to manual
4. **Broker integration point** — Executor has a single `paper_broker` interface; a future `live_broker` implementation (Alpaca, IBKR, etc.) plugs in here. This is explicitly *not* built in v1.

---

## 11. Open questions / decisions deferred

- Specific paid news/sentiment API: defer until v1.5; pick after seeing what free RSS leaves missing
- LLM prompt versioning approach: store prompts in code with semver, log version with each rec
- Backtest harness: not in v1; consider after 3 months of forward paper trading
- Universe expansion to S&P 1500: deferred to v1.5 pending v1 results
- Authentication for remote dashboard access: deferred; no public exposure in v1

---

## 12. Honest probabilities (for the record)

Documented here so future-me doesn't forget what was realistic at design time:

| Outcome | Estimated probability |
|---|---|
| System works as designed (pipeline reliable, dashboard functional) | ~90% |
| Agent produces *some* monthly income on real capital later | ~85–95% |
| Agent's strategy beats SPY total return over 1 year | ~30–40% |
| Strategy survives a 30% market crash with income mostly intact | ~60–70% |
| User makes meaningful absolute money relative to time invested | depends primarily on capital deployed, not the agent |

The asymmetry is favorable: worst case is ~$30–75 spent and 3 months learning a lot; best case is a useful income tool that runs for years.
