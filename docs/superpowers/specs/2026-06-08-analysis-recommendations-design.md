# Analysis & Recommendations — Sub-project 3 Design

**Status:** approved (2026-06-08). Implementation plan to follow.

**Scope:** implement Steps 2–5 of the daily pipeline from the master design spec — **DividendScreener**, **DividendSafetyAnalyst** (LLM), **OptionsRecommender** (LLM), and **Recommender** — plus the fundamentals data they depend on, the LLM client seam, and the read/approve/reject HTTP surface for recommendations.

**Depends on:** Sub-project 1 (Foundation) and Sub-project 2 (Data Ingestion) — the FastAPI app, async SQLAlchemy, Alembic, the pipeline runner / step framework, the source-protocol pattern, and the `stocks` / `prices` / `dividend_history` / `options_chains` / `news_items` / `pipeline_runs` tables.

**Out of scope (lands in later sub-projects):**

- Executor, positions, trades, income events (Sub-project 4).
- IncomeTracker, dividend/covered-call simulation, feedback post-mortems (Sub-project 4).
- Weekly Learner, `agent_lessons` table, alerts/notifier (Sub-project 5).
- React dashboard wiring (Sub-project 5).
- News sentiment scoring (`news_items.sentiment_score` stays null).

---

## 1. Goals

1. Ingest quarterly **fundamentals** (revenue, EPS, free cash flow, net income, debt, equity, dividends paid) for active tickers into a new `fundamentals` table.
2. Run the **DividendScreener** over every active ticker each pipeline run: compute dividend-quality signals, persist a `screenings` row per ticker, and select the finalists that advance to the LLM.
3. Run the **DividendSafetyAnalyst** LLM over each finalist: produce a schema-validated safety assessment and persist it to `dividend_safety_scores`.
4. Build the **OptionsRecommender** LLM (covered-call strike/expiry selection) — fully implemented and unit-tested, but **dormant** in this sub-project because no holdings exist until Sub-project 4.
5. Run the **Recommender**: combine screener + safety (+ options) output into `recommendations` rows with full reasoning, a signals snapshot, and a prompt version.
6. Expose HTTP to **inspect** recommendations / safety scores / screenings and to **approve / reject** pending recommendations.
7. Track LLM token usage and cost per run in the existing `pipeline_runs.llm_tokens_used` / `llm_cost_usd` columns.

**Non-goals:**

- Acting on approved recommendations (Executor — Sub-project 4).
- Any concept of an open position, trade, or realized income.
- Injecting real `agent_lessons` into prompts — the prompt builder reserves a lessons section that stays empty until Sub-project 5.

---

## 2. Key decisions (resolved during brainstorming)

| # | Decision | Rationale |
|---|---|---|
| 1 | **Fundamentals get their own ingestion step + `fundamentals` table.** | The screener's fundamental metrics (payout ratio, FCF coverage, debt-to-equity, earnings growth) were never ingested in Sub-project 2. Persisting them keeps the screener pure (no yfinance import), makes `signals` auditable, and reuses the per-ticker isolation / retry pattern already built. |
| 2 | **OptionsRecommender + `sell_covered_call` / `sell_position` are built now but dormant.** | Both LLM analysts share the same client / prompt-versioning / schema-validation infrastructure; building them together is efficient. They are fully unit-tested against fixture holdings, but produce no live recommendations until Sub-project 4 supplies positions. |
| 3 | **Phase 3 ships read + approve/reject HTTP.** | Makes the sub-project independently demoable (run pipeline → inspect recs → `curl` approve) and gives Sub-project 4's Executor approved rows to consume. Endpoints are thin status flips. |
| 4 | **Analysts use Sonnet 4.6 with structured outputs.** | The user chose `claude-sonnet-4-6` for higher-quality safety reasoning. **This deviates from the master spec's "Haiku for routine analyst calls"** and costs ~3× more (~$0.15–1.50/day vs ~$0.05–0.50/day). The model is a config value (`llm_model`), so reverting to `claude-haiku-4-5` is a one-line change. Structured outputs (`messages.parse()` / `output_config.format`) make the JSON schema-guaranteed, removing most of the retry-on-bad-JSON handling. |

---

## 3. Architecture

### 3.1 Module layout

New and modified files, following the Sub-project 2 conventions (one source per provider, one step per phase, one model file per domain group, pure logic isolated from I/O):

```
backend/app/
  sources/
    base.py                      # + FundamentalsSource protocol, FundamentalsSnapshot DTO
    fakes.py                     # + InMemoryFundamentalsSource
    fundamentals_yfinance.py     # NEW: quarterly financials/cashflow/balance-sheet via yfinance
  llm/                           # NEW subpackage — the LLM seam
    __init__.py
    base.py                      # LLMClient protocol, LLMUsage dataclass, FakeLLMClient
    anthropic_client.py          # production: claude-sonnet-4-6 + messages.parse()
    prompts.py                   # versioned prompt templates (constants + version strings)
    schemas.py                   # Pydantic response models (SafetyAssessment, CallPick)
  analysis/                      # NEW — pure functions, no DB, no network, sub-5s tests
    __init__.py
    screener.py                  # yield, payout ratio, FCF coverage, D/E, growth, composite score, flags
    options_scoring.py           # OTM filter, premium yield, prob-of-assignment from IV, regret score
  pipeline/
    steps/
      fundamentals.py            # NEW: ingest fundamentals (data step)
      screener.py                # NEW: DividendScreener (pure scoring → screenings)
      safety.py                  # NEW: DividendSafetyAnalyst (LLM → dividend_safety_scores)
      options_recommender.py     # NEW: OptionsRecommender (LLM → sell_covered_call recs; dormant)
      recommender.py             # NEW: Recommender (combine → recommendations)
    repo.py                      # + reads/writes for the four new tables; LLM cost bookkeeping
    runner.py                    # StepContext gains `llm` + `fundamentals` source
  models/
    fundamentals.py              # NEW: Fundamentals
    screening.py                 # NEW: Screening
    safety.py                    # NEW: DividendSafetyScore
    recommendation.py            # NEW: Recommendation
  api/
    recommendations.py           # NEW: list / detail / approve / reject
    stocks.py                    # NEW: GET /stocks/{ticker}/safety-score, GET /screenings
    __init__ wiring in main.py   # register new routers
  config.py                      # + llm_model, llm_effort, llm pricing constants
  alembic/versions/0002_analysis_tables.py   # NEW: one migration, four tables
```

**Why this shape:** the LLM is isolated behind `LLMClient` exactly as upstream data sources are isolated behind the source protocols. Steps never import `anthropic`; they receive an `LLMClient` via `StepContext`. All scoring math lives in `analysis/` as pure functions so it is unit-tested without a database, network, or LLM. Tests inject `FakeLLMClient` + `InMemoryFundamentalsSource`.

### 3.2 FundamentalsSource protocol

```python
# app/sources/base.py
@dataclass(frozen=True)
class FundamentalsSnapshot:
    fiscal_period: str            # e.g. "2026Q1"
    revenue: float | None
    eps: float | None
    fcf: float | None             # free cash flow
    net_income: float | None
    total_debt: float | None
    total_equity: float | None
    dividends_paid: float | None  # absolute $ paid in the period

class FundamentalsSource(Protocol):
    def fetch(self, ticker: str) -> Iterable[FundamentalsSnapshot]: ...
```

`fundamentals_yfinance.py` wraps `yfinance` quarterly `income_stmt` / `cashflow` / `balance_sheet` and normalizes into `FundamentalsSnapshot`. It contains no business logic — only shape conversion — and is the only new module allowed to import `yfinance`.

### 3.3 LLM seam

```python
# app/llm/base.py
@dataclass(frozen=True)
class LLMUsage:
    input_tokens: int
    output_tokens: int
    cost_usd: float

T = TypeVar("T", bound=BaseModel)

class LLMClient(Protocol):
    def complete_structured(
        self, *, system: str, prompt: str, schema: type[T], prompt_version: str,
    ) -> tuple[T, LLMUsage]: ...
```

- **Production** (`anthropic_client.py`): calls `client.messages.parse(model=settings.llm_model, output_config={"effort": settings.llm_effort}, ...)` with the Pydantic `schema`, returning the parsed model plus a computed `LLMUsage` (tokens from `response.usage`, cost from per-model pricing constants in config). `claude-sonnet-4-6` supports structured outputs, so the response is schema-guaranteed; a `refusal` / `max_tokens` stop reason is treated as a per-ticker failure (logged, skipped), not a crash.
- **Fake** (`FakeLLMClient`): returns canned, deterministic `schema` instances keyed by ticker, with a configurable `LLMUsage`. Supports a "return invalid" mode so tests can exercise the skip-on-bad-output path.

**Prompt versioning:** prompts live in `llm/prompts.py` as module constants, each paired with a version string (`SAFETY_PROMPT`, `SAFETY_PROMPT_VERSION = "safety-v1"`). The version is logged into `dividend_safety_scores.llm_prompt_version` and `recommendations.llm_prompt_version` so the Sub-project 5 learning loop can reason about exactly which prompt produced each output. Bumping a prompt is a code change + version bump.

### 3.4 StepContext additions

```python
@dataclass
class Sources:
    universe: UniverseSource
    prices: PriceSource
    dividends: DividendSource
    options: OptionsSource
    news: NewsSource
    fundamentals: FundamentalsSource   # NEW

@dataclass
class StepContext:
    repo: PipelineRepo
    sources: Sources
    llm: LLMClient                      # NEW
    run_id: int
    now: Callable[[], datetime]
```

Production wiring constructs the real `AnthropicLLMClient` (reads `anthropic_api_key` from settings, already present) in `app/main.py`'s lifespan / dependency provider; tests construct `FakeLLMClient`.

---

## 4. Pipeline ordering

`DEFAULT_STEPS` becomes:

```
universe → prices → dividends → fundamentals → screener → options → news → safety → options_recommender → recommender
```

Rationale for the order:

- **fundamentals** runs after `dividends` (both are per-ticker data ingestion) and before `screener`, which consumes it.
- **screener** is moved **ahead of `options`** so the screener-derived ranking can replace the Sub-project 2 placeholder watchlist ("top 50 by trailing yield"). This closes the *"real watchlist ranking"* open question deferred from Sub-project 2. The screener is pure / in-memory (~5s), so running it before the options snapshot pull is cheap. The options step now selects its watchlist from the latest `screenings` (highest `dividend_quality_score`), unioned with holdings; it falls back to the yield-based ranking if no screenings exist yet.
- **safety**, **options_recommender**, **recommender** run last, in dependency order: safety scores feed the recommender; the options step's chain data feeds options_recommender; recommender combines everything.

**Criticality:** the four new steps are all **non-critical** (`is_critical = False`). A finalist whose LLM call fails validation, refuses, or errors is logged into `pipeline_runs.errors` and skipped — it never fails the run. Only the `prices` step remains critical, unchanged from Sub-project 2.

---

## 5. Per-step behavior

### 5.1 Fundamentals step

- **Source:** `FundamentalsSource.fetch(ticker)` (yfinance quarterly statements).
- **Tickers:** all active tickers (per-ticker isolation, semaphore-bounded concurrency, the same pattern as `prices`/`dividends`).
- **Write:** upsert on `(ticker, fiscal_period)`. Re-fetching a period overwrites it (statements get revised).
- **Failure:** non-critical. A ticker with no fundamentals is simply absent; the screener handles missing data by emitting a low/zero quality score rather than crashing.

### 5.2 Screener step (DividendScreener)

For each active ticker with sufficient history, `analysis/screener.py` computes (all pure functions):

- **Yield** = trailing-12-month dividends ÷ current price.
- **Payout ratio** = dividends ÷ earnings (sustainable < 70%).
- **FCF coverage** = free cash flow ÷ dividends paid (safe ≥ 1.5).
- **Consecutive years paid / raised** (from `dividend_history`).
- **Debt-to-equity** (from `fundamentals`).
- **5-year earnings growth** (from `fundamentals`).
- **Composite `dividend_quality_score`** (0–100) and boolean flags: `is_aristocrat`, `is_king`, `is_monthly_payer`.

- **Write:** one `screenings` row per ticker per run — `dividend_quality_score`, the full `signals` JSONB (every computed metric), `passed_screen`, `created_at`, `run_id`.
- **Finalists:** the top ~30 by score **plus all current holdings** (always re-evaluated) advance to the safety step. In Sub-project 3 there are no holdings, so finalists = top ~30. The cutoff (`SCREENER_FINALIST_COUNT = 30`) is a code constant.
- **Failure:** non-critical; a per-ticker computation error is logged and that ticker is skipped.

### 5.3 Safety step (DividendSafetyAnalyst LLM)

For each finalist:

- **Prompt:** built in `llm/prompts.py` from — the computed safety metrics (Step 5.2), last 4 quarters of fundamentals, last 8 dividend declarations, the last 7 days of relevant news headlines/summaries, and **an active-lessons section that is empty in Sub-project 3** (populated in Sub-project 5).
- **Call:** `ctx.llm.complete_structured(schema=SafetyAssessment, prompt_version=SAFETY_PROMPT_VERSION, ...)`.

```python
# app/llm/schemas.py
class SafetyAssessment(BaseModel):
    score: int                    # 0–100
    concerns: list[str]
    outlook: Literal["improving", "stable", "deteriorating"]
    reasoning: str
```

- **Write:** a `dividend_safety_scores` row — `score`, the computed `payout_ratio` / `fcf_coverage` / `debt_to_equity`, `consecutive_years_paid`, `concerns` (text[]), `llm_reasoning`, `llm_model`, `llm_prompt_version`, `scored_at`.
- **Cost:** accumulate `LLMUsage` into the run's running token/cost totals (written to `pipeline_runs` on finish).
- **Failure:** non-critical. A refusal, `max_tokens`, or validation failure logs the ticker into `errors` and skips it. (Structured outputs make malformed JSON rare; there is no separate "retry once with stricter instructions" loop — the schema is enforced server-side.)

### 5.4 Options recommender step (OptionsRecommender LLM) — *dormant in Sub-project 3*

For each **eligible holding** (a held ticker with no active covered call):

- Pull the options chain (30–45 DTE) from `options_chains`.
- `analysis/options_scoring.py` filters to calls 3–7% out of the money and scores each by premium yield, probability of assignment (derived from implied volatility), and regret-of-assignment (all pure functions).
- The LLM picks the best strike + expiration with reasoning.

```python
class CallPick(BaseModel):
    strike: float
    expiration_date: date
    expected_premium: float
    prob_assignment: float
    reasoning: str
```

- **Write:** a `recommendations` row of `type='sell_covered_call'`.
- **Dormancy:** there are no holdings in Sub-project 3, so the step iterates an empty set and writes nothing live. It is nonetheless fully implemented and unit-tested against a fixture holding + fixture chain so Sub-project 4 only has to wire real positions in. This is called out explicitly so the step is not mistaken for dead code.

### 5.5 Recommender step

Combines the upstream outputs into `recommendations` rows of three types, each `status='pending'`, `approval_mode='manual'`, with `signals_snapshot` (the screener `signals` + safety summary) and `llm_prompt_version`:

- **`add_position`** — high-scoring screener finalists with a strong safety score that are **not currently held**. Live in Sub-project 3 (no holdings ⇒ every qualifying finalist is a candidate).
- **`sell_position`** — holdings whose safety deteriorated sharply (score drop > 15 points week-over-week, or a critical LLM concern). **Dormant** — requires holdings + prior scores.
- **`sell_covered_call`** — pass-through of the options step's picks. **Dormant** — requires holdings.

Recommendations are immutable after creation except for `status`, `decided_by`, `decided_at`. The Phase-1→2 seam is preserved: in a future sub-project, an `auto_approve.<type>` flag makes the Recommender write `status='approved'` directly for opted-in types — no code path change here.

---

## 6. Schema (single Alembic migration `0002`)

| Table | Key columns | Notes |
|---|---|---|
| `fundamentals` | `(ticker, fiscal_period) PK`, `ticker FK→stocks`, `revenue NUMERIC(18,2)`, `eps NUMERIC(12,4)`, `fcf NUMERIC(18,2)`, `net_income NUMERIC(18,2)`, `total_debt NUMERIC(18,2)`, `total_equity NUMERIC(18,2)`, `dividends_paid NUMERIC(18,2)`, `snapshot_at` | All financial columns nullable (yfinance gaps). Index on `(ticker)`. |
| `screenings` | `id PK`, `run_id`, `ticker FK→stocks`, `dividend_quality_score NUMERIC(5,2)`, `signals JSONB`, `passed_screen BOOL`, `created_at` | Indexes: `(run_id)`, `(ticker, created_at DESC)`. |
| `dividend_safety_scores` | `id PK`, `ticker FK→stocks`, `score SMALLINT`, `payout_ratio NUMERIC(8,4)`, `fcf_coverage NUMERIC(8,4)`, `debt_to_equity NUMERIC(8,4)`, `consecutive_years_paid SMALLINT`, `concerns TEXT[]`, `llm_reasoning TEXT`, `llm_model TEXT`, `llm_prompt_version TEXT`, `scored_at` | Index `(ticker, scored_at DESC)`. |
| `recommendations` | `id PK`, `run_id`, `type TEXT`, `ticker FK→stocks`, `confidence TEXT`, `payload JSONB`, `reasoning TEXT`, `signals_snapshot JSONB`, `llm_model TEXT`, `llm_prompt_version TEXT`, `status TEXT`, `approval_mode TEXT`, `decided_by TEXT`, `decided_at`, `created_at` | Indexes: `(status)`, `(run_id)`, `(ticker, created_at DESC)`. `status` default `'pending'`, `approval_mode` default `'manual'`. |

Foreign keys to `stocks.ticker` are `ON DELETE RESTRICT` (consistent with Sub-project 2 — delisting flips `active`, never deletes). The `payload` shapes match the master spec:

- `add_position`: `{target_shares, target_price | "market", expected_yield}`
- `sell_position`: `{position_id, reason_codes}`
- `sell_covered_call`: `{strike, expiration_date, expected_premium, prob_assignment}`

Single migration file creates all four tables atomically.

---

## 7. HTTP API

| Method | Path | Behavior |
|---|---|---|
| `GET` | `/recommendations?status=&type=` | List recs, default `status=pending`. Each row: `{id, run_id, type, ticker, confidence, status, created_at}`. |
| `GET` | `/recommendations/{id}` | Full rec including `payload`, `reasoning`, `signals_snapshot`, `llm_model`, `llm_prompt_version`. |
| `POST` | `/recommendations/{id}/approve` | `pending → approved`; sets `decided_by='user'`, `decided_at=now`. 409 if not currently `pending`. |
| `POST` | `/recommendations/{id}/reject` | `pending → rejected`; optional `{reason}` body recorded in `payload.reject_reason`. 409 if not currently `pending`. |
| `GET` | `/stocks/{ticker}/safety-score` | Latest `dividend_safety_scores` row for the ticker + reasoning. 404 if none. |
| `GET` | `/screenings?run_id=` | Screenings for a run (defaults to the most recent run). |

Errors follow the existing envelope (`{"error": {"code", "message", "details"}}`); validation errors return 422. Approve/reject are synchronous DB updates — no background task needed.

---

## 8. LLM cost tracking

- `AnthropicLLMClient` computes `cost_usd` per call from `response.usage` and per-model pricing constants in `config.py` (`claude-sonnet-4-6`: $3.00 / 1M input, $15.00 / 1M output).
- The safety and options steps accumulate `LLMUsage` into the run; `runner.finish_run` writes the totals to `pipeline_runs.llm_tokens_used` (input + output) and `llm_cost_usd`.
- `FakeLLMClient` returns a fixed `LLMUsage` so cost-accounting assertions are deterministic in tests.

---

## 9. Error handling & retries

- **Per-ticker fault isolation** in every new step, identical to Sub-project 2: a single ticker's failure produces `(ticker, err_str)` and the step continues.
- **LLM call:** the Anthropic SDK's built-in retry (429 / 5xx, exponential backoff) is left enabled. A `refusal` or `max_tokens` stop reason, or a structured-output validation failure, is a per-ticker skip — logged into `errors`, never a crash. There is no custom JSON-repair loop; structured outputs make it unnecessary.
- **Fundamentals/yfinance:** reuse the Sub-project 2 retry helper (3× exponential backoff).
- **Step-level failure** is never triggered by the four new steps — they always complete; failures live in `pipeline_runs.errors`.
- **Logging:** structured JSON via stdlib logging, every event carrying `run_id` — step start/end, per-ticker failure, LLM refusal/validation skip, token/cost per step. No per-ticker success spam.

---

## 10. Testing strategy

```
backend/tests/
  analysis/
    test_screener.py             # pure: yield/payout/FCF/D-E/growth/score/flags, edge cases (missing data, zero earnings)
    test_options_scoring.py      # pure: OTM filter, premium yield, prob-assignment from IV, regret
  llm/
    test_fake_llm.py             # FakeLLMClient returns canned schema instances + invalid-output mode
    test_anthropic_client.py     # cost computation from usage; refusal/max_tokens → skip (mocked SDK)
  sources/
    test_fundamentals_fake.py    # InMemoryFundamentalsSource behaves per protocol
  pipeline/
    test_step_fundamentals.py    # upsert idempotency; per-ticker isolation
    test_step_screener.py        # screenings written; finalist selection = top-N + holdings
    test_step_safety.py          # safety rows written; bad-LLM-output ticker skipped, not fatal
    test_step_options_recommender.py  # dormant with no holdings; picks a call for a fixture holding
    test_step_recommender.py     # add_position written for unheld high-scorers; dormant sell paths
  test_recommendations_api.py    # list/detail/approve/reject; 409 on non-pending; reject reason recorded
  test_stocks_api.py             # GET /stocks/{t}/safety-score (+404), GET /screenings
  test_migration_analysis.py     # alembic upgrade creates all four tables
  test_anthropic_integration.py  # @pytest.mark.slow, skipped by default; one real Sonnet call, schema validates
```

Existing Sub-project 1 & 2 tests continue to pass unchanged. **Coverage target:** every pure function has happy-path + edge cases; every step has happy-path, one-ticker-fails, and (for LLM steps) bad-output-skipped; the API tests cover the full pending→approved/rejected lifecycle including the 409 guard.

**Fakes by default:** `FakeLLMClient` and `InMemoryFundamentalsSource` return deterministic responses; real Anthropic/yfinance only in slow, env-gated tests.

---

## 11. Operational notes

**First-run sequence (after the `0002` migration):**

- The daily pipeline now runs the four new steps automatically. No separate backfill is required — fundamentals are fetched on the first run; the screener/safety/recommender run off whatever data is present.
- A manual single-step run for debugging: `python -m app.pipeline run --step screener` (the CLI step dispatch from Sub-project 2 covers the new step names).

**LLM cost (steady state):** ~30 safety calls/day at Sonnet 4.6 pricing ≈ **$0.15–1.50/day** (~$5–45/month), above the master spec's $2–5/month target because of the Haiku→Sonnet deviation (decision #4). Reverting `llm_model` to `claude-haiku-4-5` drops this back to ~$0.05–0.50/day. The dashboard (Sub-project 5) will surface month-to-date cost from `pipeline_runs`.

**Disk impact (rough):** `fundamentals` ~ 500 tickers × ~8 quarters × ~120 B ≈ 0.5 MB; `screenings` ~ 500 rows/day × ~1 KB ≈ 0.5 MB/day; `dividend_safety_scores` ~ 30 rows/day; `recommendations` a handful/day. Negligible next to the Sub-project 2 footprint.

---

## 12. Open questions deferred to later sub-projects

- **Holdings-dependent recommendations go live** — `sell_position` and `sell_covered_call` activate in Sub-project 4 when positions exist; the code paths are built and tested here.
- **Active `agent_lessons` injection** — the safety prompt reserves a lessons section that stays empty until Sub-project 5 builds the `agent_lessons` table and Learner.
- **Roll-call recommendations** (`type='roll_call'`) — deferred to Sub-project 4's IncomeTracker, which detects deep-ITM expiring calls.
- **Revisit Haiku vs Sonnet for the analysts** — after observing safety-score quality over the first weeks of paper trading, reconsider flipping `llm_model` back to Haiku to hit the $5/month runtime target.
- **Prompt-caching the system prompt** — the safety system prompt is stable across the ~30 daily calls; a future optimization can add a `cache_control` breakpoint to cut input-token cost. Not done in v1.
