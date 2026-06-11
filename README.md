# Stock Income Agent

A personal, self-hosted agent that generates **recurring monthly income** from a paper-traded (later real) S&P 500 portfolio, using a **dividend portfolio + covered-call writing** strategy. The agent ingests market data, news, and fundamentals; produces concrete recommendations; simulates trades; tracks realized income over time; and learns from outcomes.

Full design: [`docs/superpowers/specs/2026-05-28-stock-income-agent-design.md`](docs/superpowers/specs/2026-05-28-stock-income-agent-design.md).

---

## Product goals

### Primary goal
Generate predictable **monthly income** (dividends + covered-call premiums) from S&P 500 stocks, with a human-in-the-loop approval workflow in Phase 1 and an explicit seam to enable auto-execution in Phase 2.

### Why income, not capital appreciation
Predicting which stocks will rise short-term is dominated by institutional investors with structural advantages. **Income strategies** play to LLM strengths — synthesizing fundamentals, flagging deterioration, scoring sustainability — and produce more predictable, measurable outcomes.

### Specific goals
1. **Curate** a high-quality dividend portfolio (Aristocrats, Kings, monthly payers; safe payout ratios; FCF coverage).
2. **Recommend** monthly covered-call sales on holdings to earn premium income, with explicit strike/expiration choices.
3. **Track** every dividend payment, premium received, and assignment as a discrete, append-only income event.
4. **Benchmark** honestly against SPY total return and 1-month Treasury yields — no hidden underperformance.
5. **Learn** weekly from closed positions and user feedback; visible, falsifiable lessons injected into next week's analysis prompts.
6. **Stay local & cheap**: ~$5/month runtime, runs entirely on a laptop via Docker Compose, no auth, no cloud dependency.

### Success criteria
| Criterion | Target |
|---|---|
| Pipeline reliability | Runs every weekday evening; failures isolated per ticker |
| Honest reporting | Every chart shows SPY total return + 1-month Treasury baseline |
| Dividend safety accuracy | ≥60% of high-confidence safety scores correctly predict continuity (after 3 months) |
| Covered-call success | ≥70% of calls expire worthless or assign at modest gain |
| Learning loop | `agent_lessons` accumulates falsifiable patterns with sample size ≥5 |
| Steady-state cost | ≤ $15/month including LLM tokens |

---

## Honest probabilities

Documented up front so future-me does not forget what was realistic at design time.

| Outcome | Estimated probability |
|---|---|
| System works as designed (reliable pipeline, functional dashboard) | **~90%** |
| Agent produces *some* monthly income on real capital later | **~85–95%** |
| Agent's strategy beats SPY total return over 1 year | **~30–40%** |
| Strategy survives a 30% market crash with income mostly intact | **~60–70%** |
| User makes meaningful absolute money relative to time invested | depends primarily on capital deployed, not the agent |

The asymmetry is favorable: **worst case** is ~$30–75 spent and 3 months learning a lot; **best case** is a useful income tool that runs for years.

---

## Architecture

### High-level

```mermaid
flowchart TB
    subgraph user[User]
        Browser([Browser])
    end

    subgraph stack[Docker Compose stack]
        Web[web container<br/>React + nginx]
        API[api container<br/>FastAPI + APScheduler]
        DB[(db container<br/>PostgreSQL 16)]
    end

    subgraph ext[External services]
        YF[yfinance<br/>prices · dividends · options · news]
        News[Free RSS / paid news API<br/>v1.5+]
        LLM[Anthropic Claude<br/>Haiku + Sonnet]
        SMTP[SMTP<br/>email alerts]
    end

    Browser -- HTTP --> Web
    Web -- /api/* proxy --> API
    API -- SQL --> DB
    API --> YF
    API --> News
    API --> LLM
    API --> SMTP
```

**Approach:** Monolithic FastAPI service contains scheduler, ingestion, scoring, LLM orchestration, paper-portfolio logic, and REST API. Postgres is the single source of truth. React frontend is served by nginx and proxies `/api/*` to the backend.

**Stack:** Python 3.12 · FastAPI · SQLAlchemy 2.x (async) · Alembic · pydantic-settings · React 18 · Vite · TypeScript · TanStack Query · PostgreSQL 16 · Docker Compose.

### Daily pipeline

Runs weekdays at 17:15 ET via APScheduler:

```mermaid
flowchart LR
    A[1. Ingestion<br/>prices · divs · options · news] --> B[2. DividendScreener<br/>technical + fundamental scoring]
    B --> C[3. DividendSafetyAnalyst<br/>LLM safety scores]
    C --> D[4. OptionsRecommender<br/>LLM strike/expiry picks]
    D --> E[5. Recommender<br/>writes pending recs]
    E --> F[6. Executor<br/>approved recs → paper trades]
    F --> G[7. IncomeTracker<br/>dividends · assignments · expiries]
    G --> H[8. Notifier<br/>email digest]
```

A separate **weekly Learner** runs Fridays after the regular pipeline: reviews closed positions, generates new lessons (gated by sample size ≥ 5), and updates the active lessons injected into next week's prompts.

### Decision → Execution split (Phase 1 → Phase 2 seam)

```mermaid
sequenceDiagram
    participant Pipe as Pipeline
    participant DB as recommendations table
    participant User as User (dashboard)
    participant Exec as Executor
    participant Paper as Paper portfolio

    Pipe->>DB: insert(status=pending, mode=manual)
    DB-->>User: GET /recommendations
    User->>DB: POST /:id/approve
    Note over DB: status=approved, decided_by=user
    Exec->>DB: SELECT WHERE status='approved'
    Exec->>Paper: insert trade, open position
    Exec->>DB: status=executed

    rect rgb(240, 240, 200)
    Note over Pipe,Paper: Phase 2: same code path,<br/>auto_approve.<type>=true flips<br/>Pipeline → status=approved directly
    end
```

The Pipeline and Executor are coupled only through the `recommendations` table. Phase-2 auto-execution is a config flag flip, not a code change.

### Data model

14 tables, organized by domain:

```mermaid
erDiagram
    stocks ||--o{ prices : has
    stocks ||--o{ news_items : tagged
    stocks ||--o{ dividend_history : pays
    stocks ||--o{ options_chains : has
    stocks ||--o{ screenings : screened_in
    stocks ||--o{ dividend_safety_scores : scored
    stocks ||--o{ recommendations : about
    stocks ||--o{ positions : held
    stocks ||--o{ trades : for
    stocks ||--o{ income_events : from

    recommendations ||--o| positions : opens
    positions ||--o{ trades : ledger
    positions ||--o{ income_events : produces
    recommendations ||--o| feedback : outcome
    feedback }o--o{ agent_lessons : evidences

    pipeline_runs ||--o{ recommendations : produced_in
    alerts }o--|| recommendations : about
```

Key principles:
- **`trades` and `income_events` are append-only** — positions and P&L are derived state. The ledgers are authoritative.
- **`recommendations` are immutable** after creation; only `status` and `decided_at` change.
- Every recommendation carries `signals_snapshot` and `llm_prompt_version` so the learning loop can reason about exactly what produced each pick.

---

## REST API

All endpoints are prefixed `/` on the api container (port 8000); the React frontend reaches them via `/api/*` (nginx proxy in prod, Vite proxy in dev).

> **Status:** Health, pipeline, recommendations, and a subset of stocks endpoints are implemented (Sub-projects 1–3). Portfolio and trades endpoints landed in Sub-project 4; learning (`/lessons`, `/feedback`), `/settings` (read), and notifier-related alerts landed in Sub-project 5a. Remaining `planned` rows (stocks list/detail/prices/dividends/news, `/portfolio/live`, `PATCH /settings`, `/settings/kill-switch`) are not yet built.

### Health & ops

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/health` | ✅ implemented | Liveness + DB ping. Returns 200 `{"status":"ok","database":"ok"}` or 503 `{"status":"degraded","database":"down"}` |
| `GET` | `/pipeline/runs` | ✅ implemented | Last 30 pipeline runs with status, duration, errors (`?limit=`) |
| `GET` | `/pipeline/runs/{run_id}` | ✅ implemented | Full run detail incl. errors |
| `POST` | `/pipeline/run?step=<name>` | ✅ implemented | Manually trigger an individual step; 202 Accepted, runs in background |

### Stocks & data

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/stocks` | planned | List universe (S&P 500); filter by sector, dividend status |
| `GET` | `/stocks/{ticker}` | planned | Stock detail + latest signals |
| `GET` | `/stocks/{ticker}/prices?from=&to=` | planned | OHLCV history |
| `GET` | `/stocks/{ticker}/dividends` | planned | Dividend history |
| `GET` | `/stocks/{ticker}/news?limit=` | planned | Recent news for ticker |
| `GET` | `/stocks/{ticker}/safety-score` | ✅ implemented | Latest LLM safety score + reasoning |
| `GET` | `/screenings?run_id=` | ✅ implemented | Dividend-screener results for a run (defaults to latest run) |

### Recommendations

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/recommendations?status=&type=` | ✅ implemented | List recs, default `status=pending` |
| `GET` | `/recommendations/{id}` | ✅ implemented | Full rec with reasoning + signals snapshot |
| `POST` | `/recommendations/{id}/approve` | ✅ implemented | User approves (Phase 1) |
| `POST` | `/recommendations/{id}/reject` | ✅ implemented | User rejects with optional reason text |

### Portfolio

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/portfolio/live` | planned | Current positions with mark-to-market P&L (2-min price cache) |
| `GET` | `/portfolio/holdings` | ✅ implemented | Open positions + yields + safety scores |
| `GET` | `/portfolio/income?from=&to=` | ✅ implemented | Income events in range |
| `GET` | `/portfolio/income/calendar?days=30` | ✅ implemented | Next-N-days projected income |
| `GET` | `/portfolio/performance` | ✅ implemented | YTD return vs. SPY total return vs. 1-mo Treasury |

### Trades & history

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/trades?from=&to=` | ✅ implemented | Append-only ledger |
| `GET` | `/positions?status=` | ✅ implemented | Open and closed positions |
| `GET` | `/positions/{id}` | ✅ implemented | Position with full trade history + feedback |

### Learning

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/lessons?active=true` | ✅ implemented | Current `agent_lessons` injected into prompts |
| `POST` | `/lessons/{id}/ignore` | ✅ implemented | User toggles a lesson off |
| `GET` | `/feedback?from=&to=` | ✅ implemented | Closed-position post-mortems |

### Settings

| Method | Path | Status | Description |
|---|---|---|---|
| `GET` | `/settings` | ✅ implemented | Current config (approval modes, safety rails, notification prefs) |
| `PATCH` | `/settings` | planned | Update config (e.g., flip `auto_approve.sell_covered_call`) |
| `POST` | `/settings/kill-switch` | planned | Immediately revert all auto-approval to manual |

### Response shapes

All responses are JSON. Errors follow:

```json
{ "error": { "code": "string", "message": "human readable", "details": {} } }
```

Validation errors return HTTP 422 with `details` listing the failing fields (FastAPI default).

---

## Local development

### Requirements

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12.x | Backend uses `requires-python = ">=3.12,<3.13"`. Manage with pyenv if needed. |
| Node.js | 20.x (18 works) | Frontend Dockerfile pins Node 20; Vite 5 / Vitest 2 also run on Node 18. |
| npm | 10.x | Ships with Node 20. |
| Docker | 24+ | Or any Docker-compatible runtime (e.g. Podman with the docker socket alias). Needed for the full stack and for backend tests (testcontainers pulls `postgres:16-alpine`). |
| Docker Compose | v2 (`docker compose`) | Bundled with modern Docker. |
| uv | 0.5.4 | Python package manager. Install with `pip install uv==0.5.4`. |

The host Docker daemon must be running before backend tests or `make up`. Testcontainers can also be run with `TESTCONTAINERS_RYUK_DISABLED=true` if your runtime doesn't support its watchdog container.

### Configure

```bash
cp .env.example .env.local
# Edit .env.local; at minimum set POSTGRES_PASSWORD to something other than `changeme`.
```

### Option A — full stack via Docker Compose

Brings up Postgres + backend (with Alembic migrations) + frontend (nginx) in three containers.

```bash
make up         # build + start all containers
make logs       # follow logs
```

Then visit:
- Dashboard: <http://localhost:3000>
- API:       <http://localhost:8000>
- Health:    <http://localhost:8000/health>

### Option B — backend only, on host

Useful for fast iteration on the API. Uses a local uv-managed venv and a testcontainers-launched Postgres instead of the compose `db` service.

```bash
cd backend
uv venv                                # creates .venv/
uv pip install -e ".[dev]"             # installs runtime + dev deps
.venv/bin/pytest -m "not slow" -v      # 124 tests; add -m slow for live-API tests
.venv/bin/ruff check .                 # lint
```

To run the API against a manually-started Postgres:

```bash
export POSTGRES_USER=stockagent POSTGRES_PASSWORD=devpass \
       POSTGRES_DB=stockagent POSTGRES_HOST=localhost POSTGRES_PORT=5432
.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --reload --port 8000
```

### Option C — frontend only, on host

Useful for fast iteration on the React app. Vite dev server proxies `/api/*` to the URL configured in `vite.config.ts` (default `http://api:8000` — change to `http://localhost:8000` if running the API from Option B).

```bash
cd frontend
npm install
npm test -- --run      # vitest: 4 tests (api/health, App)
npm run dev            # http://localhost:3000
npm run build          # tsc -b && vite build → frontend/dist/
```

### Common commands

```bash
make up                  # start full stack
make down                # stop everything
make test                # run all tests (backend + frontend) via compose
make test-backend        # backend only (pytest + testcontainers)
make test-frontend       # frontend only (vitest)
make lint                # ruff + eslint
make migrate             # apply alembic migrations
make shell-api           # bash inside api container
make shell-db            # psql inside db container
```

### Project structure

```
backend/
  app/
    api/             # HTTP endpoints (one file per resource)
    models/          # SQLAlchemy models
    config.py        # pydantic-settings
    db.py            # async engine + sessions
    main.py          # FastAPI app factory
  alembic/           # migrations
  tests/             # pytest + testcontainers
frontend/
  src/
    api/             # typed API client modules
    App.tsx
    main.tsx
  tests/             # vitest + Testing Library
docs/
  superpowers/
    specs/           # design docs
    plans/           # implementation plans (per sub-project)
docker-compose.yml
Makefile
```

---

## Phasing

| Phase | Status | What's in it |
|---|---|---|
| **1. Foundation** | ✅ done | Containerized stack, FastAPI + Postgres + React skeleton, `/health` endpoint, Alembic infra, CI |
| **2. Data ingestion** | ✅ done | yfinance prices/dividends/options + news RSS; daily pipeline shell |
| **3. Analysis & recommendations** | ✅ done | DividendScreener, DividendSafetyAnalyst LLM, OptionsRecommender LLM, Recommender |
| **4. Paper trading & income tracking** | ✅ done | Executor, IncomeTracker, full dividend + covered-call simulation, feedback |
| **5. Dashboard & learning loop** | 5a done / 5b planned | Backend (5a): weekly Learner, alerts/notifier (email digest), learning + settings APIs — done. Frontend (5b): all 5 React tabs wired — planned |
| **Phase 2 (later)** | designed-in | Auto-approval per rec type, safety rails enforcement, kill switch |
| **Phase 3 (later)** | out of scope | Real broker integration (Alpaca / IBKR), live trading |

Each sub-project has its own implementation plan in `docs/superpowers/plans/`.

---

## Cost estimates

**Build:** ~3 months calendar (evenings/weekends); ~$15–75 in LLM tokens during development.

**Runtime (steady state):**
- LLM (Haiku routine + Sonnet weekly learner): ~$2–5/month
- Data feeds: $0 with free yfinance + RSS; +$30/month if paid news API added in v1.5
- Hosting: $0 local; ~$10–30/month if later moved to cloud
- **Total v1 runtime: ~$5/month**

---

## Disclaimer

This is a **personal research project**. Nothing here is investment advice. The agent makes mistakes. Paper trading exists precisely so the agent has to prove itself before any real money is risked. The probability estimates above reflect honest expectations, not promises.
