# Learning Loop & Notifier — Sub-project 5a Design

**Date:** 2026-06-09
**Depends on:** Sub-projects 1–4 — the FastAPI app, async SQLAlchemy, Alembic, the pipeline runner/step framework, `PipelineScheduler`, the `LLMClient` seam, the `recommendations` / `dividend_safety_scores` tables (SP3), and the `positions` / `trades` / `income_events` / `feedback` tables + `PipelineRepo` portfolio methods (SP4).

> **Scope split:** "Sub-project 5 — Dashboard & learning loop" in the master design is split into two independently-buildable specs. **This is 5a (backend learning loop + notifier).** The React dashboard is **5b** (`…-dashboard-design.md`), which consumes the endpoints this spec adds. 5a ships first because 5b's Settings, Learning, and alert-surfacing views depend on it.

---

## 1. What this sub-project delivers

Sub-project 4 closed the trading loop (approved recs → paper trades → income tracking → feedback). This sub-project closes the **learning loop** and adds **outbound notification**:

1. The weekly **Learner** reviews closed-position `feedback`, income events, safety-score deltas, and user rejections; proposes new `agent_lessons` and retirements; gates them; persists them.
2. Active lessons are **injected into the SafetyAnalyst prompt** — the dormant `active_lessons=[]` argument that has been threaded since SP3 finally carries real data.
3. The **Notifier** (pipeline Step 8) writes `alerts` rows each run and sends an email digest when SMTP is configured (off by default).
4. New REST endpoints expose lessons and feedback so the 5b dashboard can render the Learning and Settings views.

After this sub-project, the daily pipeline runs `… → Executor → IncomeTracker → Notifier`, and a **separate Friday job** runs the Learner after the regular pipeline.

**Explicitly out of scope (Sub-project 5b — dashboard):**
- All React UI / tabs / charts.
- `GET /portfolio/live` (mark-to-market with 2-minute yfinance price cache) — only meaningful with the dashboard.
- Full SPY total-return + 1-month-Treasury baseline in `/portfolio/performance` (SP4 left a partial close-price proxy; 5b completes the honesty view).

**Explicitly out of scope (Phase 2):**
- `PATCH /settings` and `POST /settings/kill-switch` mutation endpoints — they flip `auto_approve.<type>` / `auto_execution_enabled`, which only matter once auto-approval exists. 5a ships a **read-only** `GET /settings` so the dashboard can render current config. `POST /lessons/{id}/ignore` (the per-lesson kill switch) **is** in scope — it is meaningful in Phase 1.

---

## 2. New database tables (2)

### PK type convention

Consistent with SP3/SP4: **`INTEGER` PKs**. `agent_lessons.evidence_recommendation_ids` references `recommendations.id` (INTEGER) values; `alerts` has no outbound FKs. Migration file: `backend/alembic/versions/0004_learning_tables.py`.

### `agent_lessons` — Distilled patterns the agent has learned
```
id                        INTEGER PK (autoincrement)
pattern                   TEXT NOT NULL              -- the falsifiable lesson, injected into prompts
evidence_recommendation_ids  INTEGER[] NOT NULL DEFAULT '{}'   -- recs that evidence this pattern
sample_size               INTEGER NOT NULL           -- count of supporting closed positions
effective_from            TIMESTAMPTZ NOT NULL
effective_until           TIMESTAMPTZ NULL           -- NULL = active; set = retired (audit trail)
user_ignored              BOOLEAN NOT NULL DEFAULT false
retired_reason            TEXT NULL                  -- why the Learner retired it
created_at                TIMESTAMPTZ NOT NULL
```

**"Active" definition (single source of truth):** `effective_until IS NULL AND user_ignored = false`. The `active_lessons()` repo method and the `?active=true` API filter both use exactly this predicate. A retired lesson keeps its row forever (audit); an ignored lesson is suppressed from prompts but still listed in the UI.

### `alerts` — Outbound notification log
```
id          INTEGER PK (autoincrement)
type        TEXT CHECK IN ('new_recommendations', 'dividend_safety_alert',
                           'dividend_payment_upcoming', 'position_closed',
                           'call_expiring', 'monthly_summary')
payload     JSONB NOT NULL              -- type-specific structured body (see §3)
channel     TEXT CHECK IN ('email', 'web') NOT NULL
run_id      INTEGER FK → pipeline_runs.id ON DELETE RESTRICT   -- run that generated it
sent_at     TIMESTAMPTZ NULL           -- NULL = generated but not emailed (web-only or SMTP off)
created_at  TIMESTAMPTZ NOT NULL
```

Every generated alert is written with `channel='web'` (always, so the dashboard can surface it). When SMTP is configured and `notifications_enabled=true`, a **second** row with `channel='email'` is written and `sent_at` is stamped on successful send. `position_closed` from the master enum is included in the CHECK for forward-compatibility but is **not emitted in 5a** (closed-position alerts are folded into `monthly_summary`); emitting it per-close is deferred.

---

## 3. Notifier — pipeline Step 8

Runs **after** IncomeTrackerStep. `name = "notifier"`, `is_critical = False`. It reads state produced earlier in the same run and writes `alerts` rows. Email send is a side-effect through an injectable seam.

### Alert types and triggers (all scoped to the current `run_id` or "as of today")

| Type | Trigger | Payload shape |
|---|---|---|
| `new_recommendations` | ≥1 `recommendations` row with `status='pending'` created in this run | `{count, by_type: {add_position, sell_position, sell_covered_call}, ids: [...]}` |
| `dividend_safety_alert` | Any held ticker whose **latest** safety score dropped > 10 points vs. its **previous** score | `{ticker, current_score, previous_score, drop, concerns: [...]}` (one alert row per ticker) |
| `dividend_payment_upcoming` | Held stock tickers with an ex-date in the next 7 days (from `dividend_history`) | `{ticker, ex_date, amount_per_share, shares, expected_amount}` |
| `call_expiring` | Open `short_call` positions expiring within 5 days | `{ticker, strike, expiration_date, days_to_expiry}` |
| `monthly_summary` | Run date is the **1st of the month** | `{month, total_income, by_type, positions_closed, wins, losses}` |

`new_recommendations` is a single summary alert; the others emit **one row per ticker/position** so the dashboard can list them individually. Email digest groups all of a run's web alerts into one message.

### Email seam

```python
# app/notify/email.py
class EmailSender(Protocol):
    def send(self, *, subject: str, body: str) -> None: ...

class SmtpEmailSender:    # uses stdlib smtplib + Settings SMTP fields
class FakeEmailSender:    # records sent messages in-memory; default in tests
class NullEmailSender:    # no-op; used when notifications disabled / SMTP unconfigured
```

`StepContext` gains an `email: EmailSender` field (mirrors the existing `llm` seam). `main.py` injects `SmtpEmailSender` when `settings.smtp_host` is set **and** `settings.notifications_enabled` is true, else `NullEmailSender`. The Notifier always writes web alerts; it calls `email.send(...)` once per run with the digest, and only `NullEmailSender` no-ops.

**Idempotency:** Re-running the pipeline for the same `run_id` is the dedup boundary — alerts are keyed on `run_id`; the Notifier deletes any existing alert rows for `run_id` before regenerating (or uses `ON CONFLICT` on a `(run_id, type, payload->>'ticker')` unique index). 5a uses the **delete-then-insert per run_id** approach for simplicity, since a manual re-run of a single run is the only realistic duplicate path.

---

## 4. Weekly Learner — separate Friday job

The Learner is **not** in `default_steps()`. It is a `LearnerStep` (`name = "learner"`, `is_critical = False`) executed by a dedicated scheduler job on **Fridays at 17:30 ET**, after the 17:15 daily pipeline. It reuses `StepContext` (repo + llm).

### Loop

1. **Gather evidence** since the last Learner run (lookback = 7 days, or since the most-recent lesson `created_at`, whichever is later — see decision #5):
   - Closed `feedback` rows (the post-mortems) with their `outcome`, `total_return_pct`, `exit_reason`.
   - `income_events` in the window.
   - Safety-score deltas (latest vs. previous `dividend_safety_scores`) for held tickers.
   - User-rejected recommendations (`status='rejected'`) — counterfactuals.
   - Currently-active lessons (so the LLM can propose retirements).
2. **LLM call** (quality matters → uses the configured `llm_model`, Sonnet by default; see decision #7). Structured output via the existing `complete_structured` seam.
3. **Validation gates** (pure functions in `app/analysis/learning.py`) — applied to every proposed new lesson:
   - **Sample-size gate:** `sample_size >= LESSON_MIN_SAMPLE` (= 5).
   - **Falsifiability gate:** `pattern` non-empty, trimmed length ≥ 20 chars, and not a banned vacuous phrase (e.g. "diversify", "be careful").
   - **Non-duplication gate:** rejected if its `pattern` is a near-duplicate (normalized case/whitespace token-overlap ≥ 0.8) of an already-active lesson.
   - **Contradiction dominance gate:** if the LLM flags the proposal as contradicting an active lesson (`contradicts_lesson_id`), the proposal is adopted **only if** its `sample_size` strictly exceeds that lesson's, and that lesson is retired in the same transaction. Otherwise the proposal is dropped.
4. **Adopt:** insert surviving lessons (`effective_from=now`, `effective_until=NULL`).
5. **Retire:** for each LLM-proposed retirement (and each contradiction-dominated lesson), set `effective_until=now` and `retired_reason`. Never hard-delete (audit trail).
6. Adopted lessons take effect on the **next** SafetyStep run (Monday), via `active_lessons()`.

`LearnerStep` runs inside its own `run_pipeline(ctx, steps=[LearnerStep()])` invocation so it gets a `pipeline_runs` row of its own and the same per-step error isolation/logging.

---

## 5. Active-lessons injection

`SafetyStep` currently calls `build_safety_prompt(..., active_lessons=[])`. Change it to:

```python
active = await ctx.repo.active_lessons()           # list[str] of patterns
... build_safety_prompt(..., active_lessons=active)
```

`build_safety_prompt` already renders a lessons block (`"(none yet)"` when empty) — no prompt-template change needed. This is the only injection point in 5a. (Injecting lessons into the OptionsRecommender prompt is deferred; the master spec scopes lessons to the analyst/safety call.)

---

## 6. Scheduler changes

`PipelineScheduler.__init__` gains an optional second callable:

```python
def __init__(self, job_callable: Callable, learner_callable: Callable | None = None) -> None
```

`start()` registers the daily job (unchanged) and, when `learner_callable` is provided, a second job:

```python
def build_learner_cron_trigger() -> CronTrigger:
    return CronTrigger(day_of_week="fri", hour=17, minute=30, timezone="America/New_York")
```

`main.py` defines `_scheduled_learner_job()` (mirrors `_scheduled_pipeline_job()`: build a session + `StepContext`, `run_pipeline(ctx, steps=[LearnerStep()])`, commit/rollback) and passes it as `learner_callable`. The 30-minute gap after the 17:15 daily run is intentional — the Learner reads the feedback the daily run just produced.

---

## 7. REST API

### `app/api/lessons.py` (router prefix `/lessons`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/lessons?active=true` | List lessons. `active=true` (default) → `effective_until IS NULL AND NOT user_ignored`; `active=false` → all, including retired/ignored, newest first. Each row includes `pattern`, `sample_size`, `effective_from`, `effective_until`, `user_ignored`, `evidence_recommendation_ids`. |
| `POST` | `/lessons/{id}/ignore` | Toggle `user_ignored` (body `{"ignored": true}`); 404 if not found. The per-lesson kill switch. Returns the updated lesson. |

### `app/api/feedback.py` (no prefix — mounts `/feedback`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/feedback?from=&to=` | Closed-position post-mortems in date range (by `created_at`), newest first. Each row: all `feedback` columns + the linked `recommendation.ticker` and `recommendation.type`. `from`/`to` use `Query(None, alias="from")` (same `from_` alias pattern as `/portfolio/income`). |

### `app/api/settings.py` (router prefix `/settings`)

| Method | Path | Description |
|---|---|---|
| `GET` | `/settings` | **Read-only** snapshot for the dashboard Settings tab: `{approval_modes: {add_position: "manual", ...}, auto_execution_enabled: false, notifications: {enabled, smtp_configured, email_to}, llm_model, llm_cost_mtd}`. Approval modes are hard-coded `"manual"` in Phase 1 (no settings table yet). `llm_cost_mtd` sums `pipeline_runs.llm_cost_usd` for the current calendar month. |

`PATCH /settings` and `POST /settings/kill-switch` are deferred to Phase 2 (documented in §1).

All three routers are registered in `main.py` (`lessons_router`, `feedback_router`, `settings_router`), matching the existing include pattern.

---

## 8. PipelineRepo additions

New methods in `app/pipeline/repo.py`. Convention unchanged: identifiers first, scalars next, `now` last; `type_` trailing underscore avoids the builtin.

```python
# lessons
async def insert_lesson(self, pattern: str, evidence_recommendation_ids: list[int],
    sample_size: int, now: datetime) -> int
async def active_lessons(self) -> list[str]                 # patterns only, for prompt injection
async def list_lessons(self, active: bool = True) -> list[AgentLesson]
async def retire_lesson(self, lesson_id: int, reason: str, now: datetime) -> None
async def set_lesson_ignored(self, lesson_id: int, ignored: bool) -> AgentLesson | None
async def get_lesson(self, lesson_id: int) -> AgentLesson | None

# alerts
async def insert_alert(self, run_id: int, type_: str, payload: dict,
    channel: str, sent_at: datetime | None, now: datetime) -> int
async def delete_alerts_for_run(self, run_id: int) -> None  # Notifier idempotency
async def list_alerts(self, run_id: int | None = None, limit: int = 50) -> list[Alert]

# learner / notifier evidence
async def feedback_since(self, since: date) -> list[Feedback]
async def list_feedback(self, from_: date | None = None,
    to: date | None = None) -> list[Feedback]
async def rejected_recs_since(self, since: date) -> list[Recommendation]
async def pending_recs_for_run(self, run_id: int) -> list[Recommendation]
async def safety_score_delta(self, ticker: str) -> tuple[int, int] | None
    # (latest_score, previous_score) from dividend_safety_scores ordered by created_at desc; None if <2 scores
async def calls_expiring_within(self, days: int, today: date) -> list[Position]
async def llm_cost_month_to_date(self, today: date) -> Decimal
    # SUM(pipeline_runs.llm_cost_usd) WHERE started_at >= first-of-month
```

`upcoming_dividends`-style logic for `dividend_payment_upcoming` reuses the SP4 calendar helper (held tickers + `dividend_history` ex-dates in the next 7 days).

---

## 9. Pure analysis logic

`app/analysis/learning.py` — no DB/network. The Learner's gates live here so they're unit-testable independent of the LLM.

```python
LESSON_MIN_SAMPLE = 5
MIN_PATTERN_LEN = 20
BANNED_PHRASES = frozenset({"diversify", "be careful", "do more research"})

def passes_sample_size_gate(sample_size: int) -> bool          # >= LESSON_MIN_SAMPLE
def is_falsifiable(pattern: str) -> bool                        # len + not-banned
def is_duplicate(pattern: str, active_patterns: list[str]) -> bool   # token-overlap >= 0.8
def survives_contradiction(proposed_sample: int, active_sample: int) -> bool   # strictly >

def accept_lesson(*, pattern: str, sample_size: int, active_patterns: list[str]) -> bool
    # passes_sample_size_gate AND is_falsifiable AND NOT is_duplicate
```

`app/analysis/alerts.py` — pure builders that turn raw state into alert payload dicts (so the Notifier's branching is data-in/data-out and testable without a DB):

```python
def build_safety_alert(ticker, current, previous) -> dict | None   # None if drop <= 10
def build_dividend_upcoming(ticker, ex_date, amount_per_share, shares) -> dict
def build_call_expiring(pos, today) -> dict
def build_new_recs_summary(recs: list) -> dict | None              # None if empty
def build_monthly_summary(income_events, closed_feedback, month) -> dict
```

---

## 10. LLM prompt & schema (Learner)

`app/llm/prompts.py` additions:

```python
LEARNER_PROMPT_VERSION = "learner-v1"
LEARNER_SYSTEM = (... "You are a portfolio post-mortem analyst. Propose only falsifiable, "
    "evidence-backed lessons with sample size >= 5. Flag any proposal that contradicts an "
    "active lesson. Propose retirements for lessons the evidence no longer supports.")
def build_learner_prompt(*, active_lessons: list[str], feedback: list[dict],
    income_events: list[dict], safety_deltas: list[dict], rejections: list[dict]) -> str
```

`app/llm/schemas.py` additions:

```python
class ProposedLesson(BaseModel):
    pattern: str
    sample_size: int
    evidence_recommendation_ids: list[int]
    contradicts_lesson_id: int | None = None

class LessonRetirement(BaseModel):
    lesson_id: int
    reason: str

class LearnerOutput(BaseModel):
    new_lessons: list[ProposedLesson]
    retirements: list[LessonRetirement]
```

The Learner calls `ctx.llm.complete_structured(system=LEARNER_SYSTEM, prompt=..., schema=LearnerOutput, prompt_version=LEARNER_PROMPT_VERSION, key="learner")` and records token usage via `add_llm_usage` against its own run.

---

## 11. Config & settings additions

`app/config.py` (`Settings`) gains:

```python
notifications_enabled: bool = Field(default=False)
smtp_host: str = Field(default="")
smtp_port: int = Field(default=587)
smtp_user: str = Field(default="")
smtp_password: str = Field(default="")
smtp_from: str = Field(default="")
notify_email_to: str = Field(default="")
```

`smtp_configured` is the derived predicate `bool(smtp_host and notify_email_to)`. Email is sent only when `notifications_enabled and smtp_configured`. `.env.example` is updated with these keys (all blank/false by default). No secrets committed.

---

## 12. Default pipeline step order (updated)

```python
def default_steps() -> list[Step]:
    return [
        UniverseStep(), PricesStep(), DividendsStep(), FundamentalsStep(),
        ScreenerStep(), OptionsStep(), NewsStep(), SafetyStep(),
        OptionsRecommenderStep(), RecommenderStep(),
        ExecutorStep(), IncomeTrackerStep(),
        NotifierStep(),        # NEW (Step 8)
    ]
# LearnerStep is NOT here — it runs on the separate Friday scheduler job.
```

---

## 13. Key design decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | INTEGER PKs for `agent_lessons`, `alerts` | Consistent with SP3/SP4; `evidence_recommendation_ids` holds INTEGER rec ids. |
| 2 | "Active lesson" = `effective_until IS NULL AND NOT user_ignored`, defined once | One predicate shared by `active_lessons()`, the API filter, and prompt injection — no drift. |
| 3 | Retire (set `effective_until`), never delete lessons | Audit trail; the master spec requires retired lessons remain visible. |
| 4 | Learner is a separate Friday job, not in `default_steps()` | Master spec frames it as a weekly loop after the daily pipeline. Keeping it out of the daily run avoids re-learning every weekday and gives it its own `pipeline_runs` row. |
| 5 | Learner lookback = max(7 days, since last lesson) | The Friday cadence implies a 7-day window; tying to the last lesson's `created_at` makes a missed Friday self-healing rather than silently dropping a week of evidence. |
| 6 | Lesson gates are pure functions, separate from the LLM call | Gates (sample size, falsifiability, dedup, contradiction dominance) are unit-testable without the LLM; the LLM only proposes, the code decides. |
| 7 | Learner uses the configured `llm_model` (Sonnet) | Master spec wants Sonnet for the learner, Haiku for routine. The codebase has a single `llm_model` (currently Sonnet) and one client seam; a per-call model split is a future config addition. The Learner is correct today because the default is already Sonnet. |
| 8 | Notifier always writes `channel='web'` alerts; email is opt-in | Master spec: notifications "off by default until SMTP set up". The web alert log is the durable record the dashboard reads; email is a second `channel='email'` row sent only when configured. |
| 9 | `EmailSender` is an injected seam (Smtp/Fake/Null) | Mirrors the `LLMClient` seam. Tests use `FakeEmailSender` (deterministic, no network); production uses `Smtp` or `Null`. No live SMTP in the default test suite. |
| 10 | Notifier idempotency = delete-then-insert alerts per `run_id` | A manual single-run re-trigger is the only realistic duplicate path; deleting the run's prior alerts before regenerating is simpler than a composite unique index and matches the run-scoped model. |
| 11 | `GET /settings` read-only; PATCH/kill-switch deferred to Phase 2 | Approval-mode/kill-switch mutation only matters once auto-approval exists. The dashboard still needs to *render* current config, so the read endpoint ships now. |
| 12 | `position_closed` alert type defined but not emitted in 5a | Per-close emails would be noisy; closed positions are summarized in `monthly_summary`. The CHECK value exists for forward-compatibility. |

---

## 14. Test strategy

- **Pure functions** (`app/analysis/learning.py`, `app/analysis/alerts.py`): unit tests, no DB/network — gate boundaries (sample=4 reject / 5 accept), banned phrases, dedup token-overlap threshold, contradiction dominance, each alert builder's None/empty edge cases.
- **Migration** (`test_migration_learning.py`): assert `agent_lessons` and `alerts` exist with correct columns, CHECK constraints, and the `INTEGER[]` evidence column.
- **Repo methods**: integration tests against the testcontainer Postgres (same `session`/`pg_container` fixtures) — `active_lessons` predicate (retired/ignored excluded), `retire_lesson`/`set_lesson_ignored`, `safety_score_delta` with <2 vs ≥2 scores, `llm_cost_month_to_date` month boundary, alert delete-then-insert idempotency.
- **NotifierStep**: with a `FakeEmailSender` and seeded state — verifies one web alert per trigger, `dividend_safety_alert` only above the 10-point drop, `monthly_summary` only on the 1st, email sent once when enabled / not sent when `NullEmailSender`, and re-run replaces (not duplicates) the run's alerts.
- **LearnerStep**: with a `FakeLLMClient` returning a canned `LearnerOutput` — adopted lessons pass gates, sub-threshold/duplicate proposals dropped, contradiction with larger sample retires the active lesson, retirements set `effective_until`, and `active_lessons()` reflects the result on the next read.
- **SafetyStep injection**: a lesson inserted → SafetyStep's prompt contains it (assert via the `FakeLLMClient` captured prompt).
- **APIs** (`/lessons`, `/feedback`, `/settings`): HTTPX `ASGITransport` tests (same pattern as SP4 API tests) — `?active=` filter, ignore-toggle 404, feedback `from`/`to` alias, settings snapshot shape incl. `llm_cost_mtd`.

---

## 15. What activates after this sub-project

- The SafetyAnalyst prompt carries real lessons starting the first Monday after the first Friday Learner run.
- The `alerts` table accumulates every run; the 5b dashboard's Income/Recommendations/Settings views read it.
- `GET /lessons`, `GET /feedback`, `GET /settings` are live for 5b to consume.
- Email digests begin only once an operator sets the SMTP env vars and `notifications_enabled=true`.
- **Still deferred:** the React dashboard (5b), `/portfolio/live`, the full SPY-total-return/Treasury performance view (5b), and Phase-2 settings mutation/kill-switch.
