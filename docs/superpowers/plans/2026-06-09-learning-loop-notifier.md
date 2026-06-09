# Learning Loop & Notifier Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the learning loop (weekly Learner produces `agent_lessons` injected into prompts) and add outbound notification (NotifierStep writes `alerts`, emails when SMTP configured).

**Architecture:** Two new ORM tables (`agent_lessons`, `alerts`) + Alembic migration `0004`. Pure gate/builder functions in `app/analysis/learning.py` and `app/analysis/alerts.py`. A `NotifierStep` (Step 8, in `default_steps`) and a `LearnerStep` (run by a separate Friday scheduler job, NOT in `default_steps`). An injectable `EmailSender` seam mirroring the `LLMClient` seam. New repo methods, a Learner LLM prompt/schema, and read-only `/lessons` `/feedback` `/settings` REST endpoints.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.x async, Alembic, APScheduler, pydantic-settings, pytest + testcontainers, httpx (ASGITransport). Design spec: `docs/superpowers/specs/2026-06-09-learning-loop-notifier-design.md`.

---

## File map

| Action | Path | Responsibility |
|---|---|---|
| Create | `backend/app/models/learning.py` | `AgentLesson`, `Alert` ORM models |
| Modify | `backend/app/models/__init__.py` | Register `learning` models |
| Create | `backend/alembic/versions/0004_learning_tables.py` | DB migration |
| Create | `backend/app/analysis/learning.py` | Pure lesson-gate functions |
| Create | `backend/app/analysis/alerts.py` | Pure alert-payload builders |
| Modify | `backend/app/pipeline/repo.py` | Lesson/alert/evidence repo methods |
| Create | `backend/app/notify/__init__.py` | (empty package marker) |
| Create | `backend/app/notify/email.py` | `EmailSender` seam (Smtp/Fake/Null) + factory |
| Modify | `backend/app/pipeline/steps/base.py` | Add `email` field to `StepContext` |
| Modify | `backend/app/config.py` | SMTP settings + `smtp_configured` + `notifications_enabled` |
| Create | `backend/app/pipeline/steps/notifier.py` | `NotifierStep` (Step 8) |
| Modify | `backend/app/pipeline/steps/__init__.py` | Add `NotifierStep` to `default_steps`; export `LearnerStep` |
| Modify | `backend/app/llm/prompts.py` | Learner system + builder |
| Modify | `backend/app/llm/schemas.py` | `ProposedLesson`, `LessonRetirement`, `LearnerOutput` |
| Create | `backend/app/pipeline/steps/learner.py` | `LearnerStep` |
| Modify | `backend/app/pipeline/steps/safety.py` | Inject `active_lessons()` into prompt |
| Modify | `backend/app/pipeline/scheduler.py` | Friday learner job + trigger |
| Modify | `backend/app/main.py` | Wire learner job + email + new routers |
| Modify | `backend/app/api/pipeline.py` | Pass `email` into background-run `StepContext` |
| Create | `backend/app/api/lessons.py` | `/lessons` endpoints |
| Create | `backend/app/api/feedback.py` | `/feedback` endpoint |
| Create | `backend/app/api/settings.py` | `/settings` read-only endpoint |
| Modify | `backend/.env.example` | SMTP keys |
| Create | `backend/tests/test_migration_learning.py` | Migration smoke test |
| Create | `backend/tests/analysis/test_learning.py` | Gate unit tests |
| Create | `backend/tests/analysis/test_alerts.py` | Builder unit tests |
| Create | `backend/tests/pipeline/test_repo_learning.py` | Repo integration tests |
| Create | `backend/tests/notify/test_email.py` | Email seam unit tests |
| Create | `backend/tests/pipeline/test_step_notifier.py` | NotifierStep integration tests |
| Create | `backend/tests/pipeline/test_step_learner.py` | LearnerStep integration tests |
| Create | `backend/tests/pipeline/test_safety_lessons.py` | Safety prompt injection test |
| Create | `backend/tests/test_learning_api.py` | `/lessons` `/feedback` `/settings` tests |

**Test-fixture conventions (existing):** `pg_container`/`engine`/`session` fixtures are in `backend/tests/conftest.py`. Integration test files add a module-scoped `_migrate` fixture that runs `alembic upgrade head`; its `cwd` uses `os.path.dirname` **3×** for files under `tests/pipeline/` or `tests/notify/` or `tests/analysis/`, **2×** for files directly under `tests/`. Async tests use `@pytest.mark.asyncio(loop_scope="session")`. Run the suite with `TESTCONTAINERS_RYUK_DISABLED=true`. All commands run from `backend/` using `.venv/bin/...`.

---

### Task 0: ORM models (agent_lessons, alerts)

**Files:**
- Create: `backend/app/models/learning.py`
- Modify: `backend/app/models/__init__.py`
- Test: `backend/tests/test_models_import.py` (add assertion to existing test)

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_models_import.py`:

```python
def test_learning_models_registered():
    import app.models  # noqa: F401
    from app.models import Base
    tables = set(Base.metadata.tables)
    assert {"agent_lessons", "alerts"} <= tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_models_import.py::test_learning_models_registered -v`
Expected: FAIL (`agent_lessons`/`alerts` not in metadata).

- [ ] **Step 3: Create the models** — `backend/app/models/learning.py`:

```python
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class AgentLesson(Base):
    __tablename__ = "agent_lessons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_recommendation_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    effective_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user_ignored: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retired_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        CheckConstraint(
            "type IN ('new_recommendations', 'dividend_safety_alert', "
            "'dividend_payment_upcoming', 'position_closed', 'call_expiring', 'monthly_summary')",
            name="ck_alerts_type",
        ),
        CheckConstraint("channel IN ('email', 'web')", name="ck_alerts_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    channel: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pipeline_runs.id", ondelete="RESTRICT"), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

> Note: `alerts.run_id` is `BigInteger` to match `pipeline_runs.id` (BIGINT from SP2) and avoid an FK type mismatch.

- [ ] **Step 4: Register the module** — in `backend/app/models/__init__.py`, add `learning,` to the side-effect import block, alphabetically (between `fundamentals` and `news`):

```python
from app.models import (  # noqa: E402, F401
    fundamentals,
    learning,
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

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/test_models_import.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/learning.py app/models/__init__.py tests/test_models_import.py
git commit -m "feat(backend): ORM models for agent_lessons and alerts"
```

---

### Task 1: Alembic migration 0004

**Files:**
- Create: `backend/alembic/versions/0004_learning_tables.py`
- Test: `backend/tests/test_migration_learning.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_migration_learning.py`:

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
async def test_learning_tables_exist(session):
    rows = await session.execute(text(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"))
    names = {r[0] for r in rows.all()}
    assert {"agent_lessons", "alerts"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_learning.py -v`
Expected: FAIL (tables missing — migration not yet written).

- [ ] **Step 3: Write the migration** — `backend/alembic/versions/0004_learning_tables.py`:

```python
"""learning tables: agent_lessons, alerts

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-09
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_lessons",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("evidence_recommendation_ids", postgresql.ARRAY(sa.Integer()),
                  nullable=False, server_default=sa.text("'{}'::integer[]")),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_ignored", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("retired_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "alerts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("type", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("channel", sa.Text(), nullable=False),
        sa.Column("run_id", sa.BigInteger(),
                  sa.ForeignKey("pipeline_runs.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "type IN ('new_recommendations', 'dividend_safety_alert', "
            "'dividend_payment_upcoming', 'position_closed', 'call_expiring', 'monthly_summary')",
            name="ck_alerts_type",
        ),
        sa.CheckConstraint("channel IN ('email', 'web')", name="ck_alerts_channel"),
    )


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("agent_lessons")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_migration_learning.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/0004_learning_tables.py tests/test_migration_learning.py
git commit -m "feat(backend): alembic migration for learning tables"
```

---

### Task 2: Pure lesson-gate functions

**Files:**
- Create: `backend/app/analysis/learning.py`
- Test: `backend/tests/analysis/test_learning.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/analysis/test_learning.py`:

```python
from app.analysis.learning import (
    LESSON_MIN_SAMPLE,
    accept_lesson,
    is_duplicate,
    is_falsifiable,
    passes_sample_size_gate,
    survives_contradiction,
)


def test_sample_size_gate():
    assert passes_sample_size_gate(LESSON_MIN_SAMPLE) is True
    assert passes_sample_size_gate(LESSON_MIN_SAMPLE - 1) is False


def test_is_falsifiable():
    assert is_falsifiable("REITs with payout ratio above 95% cut within two quarters") is True
    assert is_falsifiable("be careful") is False          # banned phrase
    assert is_falsifiable("too short") is False           # under MIN_PATTERN_LEN
    assert is_falsifiable("   ") is False                 # empty after strip


def test_is_duplicate():
    active = ["High debt utilities cut dividends in rate-hike cycles consistently"]
    assert is_duplicate("high debt utilities cut dividends in rate hike cycles consistently", active) is True
    assert is_duplicate("Monthly payers with low FCF coverage tend to reduce distributions", active) is False


def test_survives_contradiction():
    assert survives_contradiction(8, 5) is True    # strictly greater
    assert survives_contradiction(5, 5) is False
    assert survives_contradiction(4, 5) is False


def test_accept_lesson():
    active = ["Existing lesson about something specific and falsifiable here"]
    assert accept_lesson(
        pattern="New falsifiable lesson with adequate descriptive length here",
        sample_size=5, active_patterns=active) is True
    assert accept_lesson(pattern="be careful", sample_size=9, active_patterns=active) is False
    assert accept_lesson(
        pattern="New falsifiable lesson with adequate descriptive length here",
        sample_size=3, active_patterns=active) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analysis/test_learning.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation** — `backend/app/analysis/learning.py`:

```python
"""Pure validation gates for Learner-proposed lessons. No DB, no network."""

LESSON_MIN_SAMPLE = 5
MIN_PATTERN_LEN = 20
BANNED_PHRASES = frozenset({"diversify", "be careful", "do more research"})
_DUP_OVERLAP_THRESHOLD = 0.8


def passes_sample_size_gate(sample_size: int) -> bool:
    return sample_size >= LESSON_MIN_SAMPLE


def is_falsifiable(pattern: str) -> bool:
    text = pattern.strip()
    if len(text) < MIN_PATTERN_LEN:
        return False
    return text.lower() not in BANNED_PHRASES


def _tokens(s: str) -> set[str]:
    return {t for t in s.lower().replace("-", " ").split() if t}


def is_duplicate(pattern: str, active_patterns: list[str]) -> bool:
    candidate = _tokens(pattern)
    if not candidate:
        return False
    for existing in active_patterns:
        other = _tokens(existing)
        if not other:
            continue
        overlap = len(candidate & other) / len(candidate | other)
        if overlap >= _DUP_OVERLAP_THRESHOLD:
            return True
    return False


def survives_contradiction(proposed_sample: int, active_sample: int) -> bool:
    return proposed_sample > active_sample


def accept_lesson(*, pattern: str, sample_size: int, active_patterns: list[str]) -> bool:
    return (
        passes_sample_size_gate(sample_size)
        and is_falsifiable(pattern)
        and not is_duplicate(pattern, active_patterns)
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/analysis/test_learning.py -v`
Expected: PASS (all 5 tests).

- [ ] **Step 5: Commit**

```bash
git add app/analysis/learning.py tests/analysis/test_learning.py
git commit -m "feat(backend): pure lesson-gate functions"
```

---

### Task 3: Pure alert-payload builders

**Files:**
- Create: `backend/app/analysis/alerts.py`
- Test: `backend/tests/analysis/test_alerts.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/analysis/test_alerts.py`:

```python
from datetime import date
from decimal import Decimal

from app.analysis.alerts import (
    build_call_expiring,
    build_dividend_upcoming,
    build_monthly_summary,
    build_new_recs_summary,
    build_safety_alert,
)


def test_build_safety_alert_only_above_threshold():
    assert build_safety_alert("KO", 60, 75, ["payout rising"]) == {
        "ticker": "KO", "current_score": 60, "previous_score": 75, "drop": 15,
        "concerns": ["payout rising"],
    }
    assert build_safety_alert("KO", 70, 75, []) is None       # drop of 5 <= 10
    assert build_safety_alert("KO", 80, 75, []) is None       # improvement


def test_build_dividend_upcoming():
    out = build_dividend_upcoming("JNJ", date(2026, 6, 12), Decimal("1.19"), Decimal("100"))
    assert out["ticker"] == "JNJ"
    assert out["ex_date"] == "2026-06-12"
    assert out["expected_amount"] == 119.0


def test_build_call_expiring():
    class P:
        ticker = "KO"; strike = Decimal("65"); expiration_date = date(2026, 6, 12)
    out = build_call_expiring(P(), date(2026, 6, 9))
    assert out == {"ticker": "KO", "strike": 65.0,
                   "expiration_date": "2026-06-12", "days_to_expiry": 3}


def test_build_new_recs_summary_none_when_empty():
    assert build_new_recs_summary([]) is None


def test_build_new_recs_summary_counts_by_type():
    class R:
        def __init__(self, id, type):
            self.id = id; self.type = type
    recs = [R(1, "add_position"), R(2, "add_position"), R(3, "sell_covered_call")]
    out = build_new_recs_summary(recs)
    assert out["count"] == 3
    assert out["by_type"]["add_position"] == 2
    assert out["by_type"]["sell_covered_call"] == 1
    assert set(out["ids"]) == {1, 2, 3}


def test_build_monthly_summary():
    class IE:
        def __init__(self, type, amount):
            self.type = type; self.amount = amount
    class FB:
        def __init__(self, outcome):
            self.outcome = outcome
    income = [IE("dividend", Decimal("50")), IE("call_premium", Decimal("120"))]
    fb = [FB("win"), FB("win"), FB("loss")]
    out = build_monthly_summary(income, fb, "2026-05")
    assert out["month"] == "2026-05"
    assert out["total_income"] == 170.0
    assert out["by_type"] == {"dividend": 50.0, "call_premium": 120.0}
    assert out["positions_closed"] == 3
    assert out["wins"] == 2 and out["losses"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/analysis/test_alerts.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the implementation** — `backend/app/analysis/alerts.py`:

```python
"""Pure builders turning raw state into alert payload dicts. No DB, no network.

All Decimal money values are converted to float for JSON payloads.
"""
from collections import Counter
from datetime import date
from decimal import Decimal

SAFETY_DROP_THRESHOLD = 10


def build_safety_alert(ticker: str, current: int, previous: int,
                       concerns: list[str]) -> dict | None:
    drop = previous - current
    if drop <= SAFETY_DROP_THRESHOLD:
        return None
    return {"ticker": ticker, "current_score": current, "previous_score": previous,
            "drop": drop, "concerns": concerns}


def build_dividend_upcoming(ticker: str, ex_date: date, amount_per_share: Decimal,
                            shares: Decimal) -> dict:
    return {"ticker": ticker, "ex_date": ex_date.isoformat(),
            "amount_per_share": float(amount_per_share), "shares": float(shares),
            "expected_amount": float(amount_per_share * shares)}


def build_call_expiring(pos, today: date) -> dict:
    return {"ticker": pos.ticker, "strike": float(pos.strike),
            "expiration_date": pos.expiration_date.isoformat(),
            "days_to_expiry": (pos.expiration_date - today).days}


def build_new_recs_summary(recs: list) -> dict | None:
    if not recs:
        return None
    by_type = Counter(r.type for r in recs)
    return {"count": len(recs), "by_type": dict(by_type), "ids": [r.id for r in recs]}


def build_monthly_summary(income_events: list, closed_feedback: list, month: str) -> dict:
    by_type: dict[str, float] = {}
    total = Decimal("0")
    for ie in income_events:
        total += ie.amount
        by_type[ie.type] = by_type.get(ie.type, 0.0) + float(ie.amount)
    wins = sum(1 for f in closed_feedback if f.outcome == "win")
    losses = sum(1 for f in closed_feedback if f.outcome == "loss")
    return {"month": month, "total_income": float(total), "by_type": by_type,
            "positions_closed": len(closed_feedback), "wins": wins, "losses": losses}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest tests/analysis/test_alerts.py -v`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add app/analysis/alerts.py tests/analysis/test_alerts.py
git commit -m "feat(backend): pure alert-payload builders"
```

---

### Task 4: PipelineRepo additions (lessons, alerts, evidence)

**Files:**
- Modify: `backend/app/pipeline/repo.py`
- Test: `backend/tests/pipeline/test_repo_learning.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/pipeline/test_repo_learning.py`:

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


_now = datetime(2026, 6, 9, 17, 30, tzinfo=UTC)
_today = _now.date()


@pytest.mark.asyncio(loop_scope="session")
async def test_lesson_lifecycle(session):
    repo = PipelineRepo(session)
    lid = await repo.insert_lesson("Utilities with high leverage cut in rate cycles", [1, 2], 6, _now)
    assert lid > 0
    assert "Utilities with high leverage cut in rate cycles" in await repo.active_lessons()

    # ignore suppresses from active_lessons but keeps the row listed
    updated = await repo.set_lesson_ignored(lid, True)
    assert updated is not None and updated.user_ignored is True
    assert "Utilities with high leverage cut in rate cycles" not in await repo.active_lessons()
    assert any(x.id == lid for x in await repo.list_lessons(active=False))

    # un-ignore then retire
    await repo.set_lesson_ignored(lid, False)
    await repo.retire_lesson(lid, "no longer supported", _now)
    assert "Utilities with high leverage cut in rate cycles" not in await repo.active_lessons()
    row = await repo.get_lesson(lid)
    assert row.effective_until is not None and row.retired_reason == "no longer supported"
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_alert_delete_then_insert_idempotency(session):
    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=_now)
    await repo.insert_alert(run_id, "call_expiring", {"ticker": "KO"}, "web", None, _now)
    assert len(await repo.list_alerts(run_id=run_id)) == 1
    await repo.delete_alerts_for_run(run_id)
    await repo.insert_alert(run_id, "call_expiring", {"ticker": "KO"}, "web", None, _now)
    assert len(await repo.list_alerts(run_id=run_id)) == 1
    await session.commit()


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_score_delta_and_cost_mtd(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PEP", "Pepsi", "S", "B")], today=_today)
    assert await repo.safety_score_delta("PEP") is None  # < 2 scores
    await repo.insert_safety_score(
        ticker="PEP", score=80, payout_ratio=None, fcf_coverage=None, debt_to_equity=None,
        consecutive_years_paid=None, concerns=[], reasoning="r", model="m",
        prompt_version="v", now=datetime(2026, 6, 1, tzinfo=UTC))
    await repo.insert_safety_score(
        ticker="PEP", score=66, payout_ratio=None, fcf_coverage=None, debt_to_equity=None,
        consecutive_years_paid=None, concerns=["margin pressure"], reasoning="r", model="m",
        prompt_version="v", now=datetime(2026, 6, 8, tzinfo=UTC))
    assert await repo.safety_score_delta("PEP") == (66, 80)

    cost = await repo.llm_cost_month_to_date(_today)
    assert cost >= Decimal("0")
    await session.commit()
```

> Note: confirm `insert_safety_score`'s exact signature in `app/pipeline/repo.py` before running; the call above mirrors `SafetyStep`'s usage. Adjust kwarg names if they differ.

- [ ] **Step 2: Run test to verify it fails**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo_learning.py -v`
Expected: FAIL (`insert_lesson` and friends not defined).

- [ ] **Step 3: Add imports** — at the top of `backend/app/pipeline/repo.py`, add to the model imports:

```python
from app.models.learning import AgentLesson, Alert
```

- [ ] **Step 4: Add the methods** — append to the `PipelineRepo` class in `backend/app/pipeline/repo.py`:

```python
    # ----- lessons -----

    async def insert_lesson(self, pattern: str, evidence_recommendation_ids: list[int],
                            sample_size: int, now: datetime) -> int:
        lesson = AgentLesson(
            pattern=pattern, evidence_recommendation_ids=evidence_recommendation_ids,
            sample_size=sample_size, effective_from=now, effective_until=None,
            user_ignored=False, created_at=now,
        )
        self.session.add(lesson)
        await self.session.flush()
        return lesson.id

    async def active_lessons(self) -> list[str]:
        rows = await self.session.execute(
            select(AgentLesson.pattern).where(
                AgentLesson.effective_until.is_(None),
                AgentLesson.user_ignored.is_(False),
            ).order_by(AgentLesson.effective_from)
        )
        return [r[0] for r in rows.all()]

    async def list_lessons(self, active: bool = True) -> list[AgentLesson]:
        stmt = select(AgentLesson).order_by(AgentLesson.created_at.desc())
        if active:
            stmt = stmt.where(
                AgentLesson.effective_until.is_(None),
                AgentLesson.user_ignored.is_(False),
            )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def get_lesson(self, lesson_id: int) -> AgentLesson | None:
        return await self.session.get(AgentLesson, lesson_id)

    async def retire_lesson(self, lesson_id: int, reason: str, now: datetime) -> None:
        lesson = await self.session.get(AgentLesson, lesson_id)
        if lesson is not None and lesson.effective_until is None:
            lesson.effective_until = now
            lesson.retired_reason = reason
            await self.session.flush()

    async def set_lesson_ignored(self, lesson_id: int, ignored: bool) -> AgentLesson | None:
        lesson = await self.session.get(AgentLesson, lesson_id)
        if lesson is None:
            return None
        lesson.user_ignored = ignored
        await self.session.flush()
        return lesson

    # ----- alerts -----

    async def insert_alert(self, run_id: int, type_: str, payload: dict, channel: str,
                           sent_at: datetime | None, now: datetime) -> int:
        alert = Alert(run_id=run_id, type=type_, payload=payload, channel=channel,
                      sent_at=sent_at, created_at=now)
        self.session.add(alert)
        await self.session.flush()
        return alert.id

    async def delete_alerts_for_run(self, run_id: int) -> None:
        await self.session.execute(
            Alert.__table__.delete().where(Alert.run_id == run_id))

    async def list_alerts(self, run_id: int | None = None, limit: int = 50) -> list[Alert]:
        stmt = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
        if run_id is not None:
            stmt = select(Alert).where(Alert.run_id == run_id).order_by(Alert.created_at.desc())
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    # ----- learner / notifier evidence -----

    async def feedback_since(self, since: date) -> list[Feedback]:
        from datetime import time
        rows = await self.session.execute(
            select(Feedback).where(
                Feedback.created_at >= datetime.combine(since, time.min, tzinfo=UTC)
            ).order_by(Feedback.created_at.desc())
        )
        return list(rows.scalars().all())

    async def list_feedback(self, from_: date | None = None,
                            to: date | None = None) -> list[Feedback]:
        from datetime import time
        stmt = select(Feedback).order_by(Feedback.created_at.desc())
        if from_ is not None:
            stmt = stmt.where(Feedback.created_at >= datetime.combine(from_, time.min, tzinfo=UTC))
        if to is not None:
            stmt = stmt.where(Feedback.created_at <= datetime.combine(to, time.max, tzinfo=UTC))
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def rejected_recs_since(self, since: date) -> list[Recommendation]:
        from datetime import time
        rows = await self.session.execute(
            select(Recommendation).where(
                Recommendation.status == "rejected",
                Recommendation.decided_at >= datetime.combine(since, time.min, tzinfo=UTC),
            )
        )
        return list(rows.scalars().all())

    async def pending_recs_for_run(self, run_id: int) -> list[Recommendation]:
        rows = await self.session.execute(
            select(Recommendation).where(
                Recommendation.run_id == run_id,
                Recommendation.status == "pending",
            )
        )
        return list(rows.scalars().all())

    async def safety_score_delta(self, ticker: str) -> tuple[int, int] | None:
        rows = await self.session.execute(
            select(DividendSafetyScore.score).where(DividendSafetyScore.ticker == ticker)
            .order_by(DividendSafetyScore.scored_at.desc()).limit(2)
        )
        scores = [r[0] for r in rows.all()]
        if len(scores) < 2:
            return None
        return (scores[0], scores[1])  # (latest, previous)

    async def calls_expiring_within(self, days: int, today: date) -> list[Position]:
        end = today + timedelta(days=days)
        rows = await self.session.execute(
            select(Position).where(
                Position.status == "open",
                Position.kind == "short_call",
                Position.expiration_date >= today,
                Position.expiration_date <= end,
            )
        )
        return list(rows.scalars().all())

    async def dividends_between(self, ticker: str, start: date, end: date) -> list[DividendHistory]:
        rows = await self.session.execute(
            select(DividendHistory).where(
                DividendHistory.ticker == ticker,
                DividendHistory.ex_date >= start,
                DividendHistory.ex_date <= end,
            ).order_by(DividendHistory.ex_date)
        )
        return list(rows.scalars().all())

    async def llm_cost_month_to_date(self, today: date) -> Decimal:
        first = today.replace(day=1)
        from datetime import time
        row = await self.session.execute(
            select(func.coalesce(func.sum(PipelineRun.llm_cost_usd), 0)).where(
                PipelineRun.started_at >= datetime.combine(first, time.min, tzinfo=UTC)
            )
        )
        return Decimal(str(row.scalar() or 0))
```

- [ ] **Step 5: Add the `timedelta` import** — ensure the top of `repo.py` imports `timedelta`. Change the existing datetime import line to:

```python
from datetime import UTC, date, datetime, timedelta
```

- [ ] **Step 6: Run test to verify it passes**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_repo_learning.py -v`
Expected: PASS (3 tests).

- [ ] **Step 7: Commit**

```bash
git add app/pipeline/repo.py tests/pipeline/test_repo_learning.py
git commit -m "feat(backend): repo methods for lessons, alerts, learner evidence"
```

---

### Task 5: Email seam + StepContext.email + config

**Files:**
- Create: `backend/app/notify/__init__.py` (empty)
- Create: `backend/app/notify/email.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/pipeline/steps/base.py`
- Test: `backend/tests/notify/test_email.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/notify/test_email.py`:

```python
from app.config import Settings
from app.notify.email import FakeEmailSender, NullEmailSender, make_email_sender


def _settings(**over) -> Settings:
    base = dict(postgres_user="u", postgres_password="p", postgres_db="d",
                postgres_host="h", postgres_port=5432)
    base.update(over)
    return Settings(**base)


def test_fake_records_messages():
    sender = FakeEmailSender()
    assert sender.enabled is True
    sender.send(subject="hi", body="there")
    assert sender.sent == [("hi", "there")]


def test_null_is_disabled_and_noop():
    sender = NullEmailSender()
    assert sender.enabled is False
    sender.send(subject="x", body="y")  # no-op, must not raise


def test_smtp_configured_predicate():
    assert _settings().smtp_configured is False
    assert _settings(smtp_host="smtp.example.com", notify_email_to="me@example.com").smtp_configured is True


def test_make_email_sender_null_when_disabled():
    s = _settings(smtp_host="smtp.example.com", notify_email_to="me@example.com",
                  notifications_enabled=False)
    assert make_email_sender(s).enabled is False  # disabled -> Null


def test_make_email_sender_null_when_unconfigured():
    s = _settings(notifications_enabled=True)  # no smtp host
    assert make_email_sender(s).enabled is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/notify/test_email.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Add config fields** — in `backend/app/config.py`, add inside `Settings` (after `llm_model`):

```python
    notifications_enabled: bool = Field(default=False)
    smtp_host: str = Field(default="")
    smtp_port: int = Field(default=587)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="")
    notify_email_to: str = Field(default="")

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host and self.notify_email_to)
```

> Place the `smtp_configured` property next to the existing `postgres_url` property.

- [ ] **Step 4: Create the package marker** — `backend/app/notify/__init__.py`:

```python
```

(empty file)

- [ ] **Step 5: Create the email seam** — `backend/app/notify/email.py`:

```python
import logging
import smtplib
from email.message import EmailMessage
from typing import Protocol

from app.config import Settings

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    enabled: bool

    def send(self, *, subject: str, body: str) -> None: ...


class NullEmailSender:
    """No-op sender used when notifications are disabled or SMTP is unconfigured."""

    enabled = False

    def send(self, *, subject: str, body: str) -> None:  # noqa: D401
        return None


class FakeEmailSender:
    """Test double recording sent messages in memory."""

    enabled = True

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def send(self, *, subject: str, body: str) -> None:
        self.sent.append((subject, body))


class SmtpEmailSender:
    enabled = True

    def __init__(self, *, host: str, port: int, user: str, password: str,
                 sender: str, to: str) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from = sender or user
        self._to = to

    def send(self, *, subject: str, body: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self._from
        msg["To"] = self._to
        msg.set_content(body)
        with smtplib.SMTP(self._host, self._port) as smtp:
            smtp.starttls()
            if self._user:
                smtp.login(self._user, self._password)
            smtp.send_message(msg)
        logger.info("notifier: sent email '%s' to %s", subject, self._to)


def make_email_sender(settings: Settings) -> EmailSender:
    if not (settings.notifications_enabled and settings.smtp_configured):
        return NullEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host, port=settings.smtp_port, user=settings.smtp_user,
        password=settings.smtp_password, sender=settings.smtp_from, to=settings.notify_email_to,
    )
```

- [ ] **Step 6: Add `email` to StepContext** — in `backend/app/pipeline/steps/base.py`, add an import and a field. After `from app.llm.base import LLMClient` add:

```python
from app.notify.email import EmailSender
```

And add to the `StepContext` dataclass (after the `llm` field):

```python
    email: EmailSender | None = None
```

- [ ] **Step 7: Run test to verify it passes**

Run: `.venv/bin/pytest tests/notify/test_email.py -v`
Expected: PASS (5 tests). Also run `.venv/bin/pytest tests/pipeline/test_default_steps_portfolio.py -v` to confirm `StepContext` import still works.

- [ ] **Step 8: Commit**

```bash
git add app/notify/__init__.py app/notify/email.py app/config.py app/pipeline/steps/base.py tests/notify/test_email.py
git commit -m "feat(backend): EmailSender seam + SMTP config + StepContext.email"
```

---

### Task 6: NotifierStep (Step 8)

**Files:**
- Create: `backend/app/pipeline/steps/notifier.py`
- Modify: `backend/app/pipeline/steps/__init__.py`
- Modify: `backend/app/api/pipeline.py` (pass `email` into background-run ctx)
- Test: `backend/tests/pipeline/test_step_notifier.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/pipeline/test_step_notifier.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.models.stocks import DividendHistory
from app.notify.email import FakeEmailSender, NullEmailSender
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.notifier import NotifierStep
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


_now = datetime(2026, 6, 9, 17, 20, tzinfo=UTC)  # not the 1st -> no monthly summary
_today = _now.date()
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id, email):
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: _now, email=email)


@pytest.mark.asyncio(loop_scope="session")
async def test_notifier_writes_web_alerts_and_emails(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("KO", "Coca-Cola", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)

    # one pending rec in this run -> new_recommendations alert
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    # an open stock position + an upcoming dividend -> dividend_payment_upcoming
    await repo.open_position(rec_id=rec_id, ticker="KO", kind="stock", shares=Decimal("100"),
                             avg_entry_price=Decimal("60"), strike=None, expiration_date=None, now=_now)
    session.add(DividendHistory(ticker="KO", ex_date=date(2026, 6, 12), pay_date=None,
                                amount_per_share=Decimal("0.485"), frequency="quarterly"))
    # a call expiring in 3 days -> call_expiring
    call_rec = await repo.insert_recommendation(
        run_id=run_id, type="sell_covered_call", ticker="KO", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(rec_id=call_rec, ticker="KO", kind="short_call", shares=Decimal("1"),
                             avg_entry_price=Decimal("1.20"), strike=Decimal("65"),
                             expiration_date=date(2026, 6, 12), now=_now)
    await session.flush()

    email = FakeEmailSender()
    result = await NotifierStep().run(_ctx(repo, run_id, email))
    await session.commit()

    alerts = await repo.list_alerts(run_id=run_id)
    types = {a.type for a in alerts if a.channel == "web"}
    assert {"new_recommendations", "dividend_payment_upcoming", "call_expiring"} <= types
    # email enabled -> a single email-channel alert with sent_at, and one email sent
    email_rows = [a for a in alerts if a.channel == "email"]
    assert len(email_rows) == 1 and email_rows[0].sent_at is not None
    assert len(email.sent) == 1
    assert result.ok_count >= 3


@pytest.mark.asyncio(loop_scope="session")
async def test_notifier_no_email_when_null_sender_and_idempotent(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("PG", "P&G", "S", "B")], today=_today)
    run_id = await repo.start_run(now=_now)
    rec_id = await repo.insert_recommendation(
        run_id=run_id, type="add_position", ticker="PG", confidence="high",
        payload={}, reasoning="r", signals_snapshot={}, model="m", prompt_version="v", now=_now)
    await repo.open_position(rec_id=rec_id, ticker="PG", kind="stock", shares=Decimal("50"),
                             avg_entry_price=Decimal("150"), strike=None, expiration_date=None, now=_now)
    await session.flush()

    await NotifierStep().run(_ctx(repo, run_id, NullEmailSender()))
    await session.commit()
    first = await repo.list_alerts(run_id=run_id)
    assert all(a.channel == "web" for a in first)  # no email channel rows

    # re-run replaces, does not duplicate
    await NotifierStep().run(_ctx(repo, run_id, NullEmailSender()))
    await session.commit()
    second = await repo.list_alerts(run_id=run_id)
    assert len(second) == len(first)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_notifier.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the NotifierStep** — `backend/app/pipeline/steps/notifier.py`:

```python
import logging
from datetime import timedelta

from app.analysis.alerts import (
    build_call_expiring,
    build_dividend_upcoming,
    build_monthly_summary,
    build_new_recs_summary,
    build_safety_alert,
)
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

CALL_EXPIRY_WINDOW_DAYS = 5
DIVIDEND_LOOKAHEAD_DAYS = 7


class NotifierStep(Step):
    name = "notifier"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        today = ctx.now().date()
        now = ctx.now()
        repo = ctx.repo

        # Idempotency: clear any alerts previously generated for this run.
        await repo.delete_alerts_for_run(ctx.run_id)

        web_payloads: list[tuple[str, dict]] = []

        # 1. New recommendations created in this run
        pending = await repo.pending_recs_for_run(ctx.run_id)
        summary = build_new_recs_summary(pending)
        if summary is not None:
            web_payloads.append(("new_recommendations", summary))

        held = await repo.held_tickers()

        # 2. Dividend safety drops on held tickers
        for ticker in held:
            delta = await repo.safety_score_delta(ticker)
            if delta is None:
                continue
            current, previous = delta
            score = await repo.latest_safety_score(ticker)
            concerns = list(score.concerns) if score is not None else []
            payload = build_safety_alert(ticker, current, previous, concerns)
            if payload is not None:
                web_payloads.append(("dividend_safety_alert", payload))

        # 3. Upcoming dividends (next 7 days) for held stock positions
        end = today + timedelta(days=DIVIDEND_LOOKAHEAD_DAYS)
        for ticker in held:
            positions = await repo.list_open_positions(ticker=ticker, kind="stock")
            shares = sum((p.shares for p in positions), start=positions[0].shares * 0) if positions else None
            if shares is None:
                continue
            for div in await repo.dividends_between(ticker, today, end):
                web_payloads.append(
                    ("dividend_payment_upcoming",
                     build_dividend_upcoming(ticker, div.ex_date, div.amount_per_share, shares)))

        # 4. Calls expiring within 5 days
        for pos in await repo.calls_expiring_within(CALL_EXPIRY_WINDOW_DAYS, today):
            web_payloads.append(("call_expiring", build_call_expiring(pos, today)))

        # 5. Monthly summary on the 1st
        if today.day == 1:
            prev_month_end = today - timedelta(days=1)
            prev_month_start = prev_month_end.replace(day=1)
            income = await repo.list_income_events(from_=prev_month_start, to=prev_month_end)
            closed = await repo.list_feedback(from_=prev_month_start, to=prev_month_end)
            month_label = prev_month_start.strftime("%Y-%m")
            web_payloads.append(
                ("monthly_summary", build_monthly_summary(income, closed, month_label)))

        # Persist web alerts
        for type_, payload in web_payloads:
            await repo.insert_alert(ctx.run_id, type_, payload, "web", None, now)

        # Email digest (only when a real sender is wired and there is something to say)
        if ctx.email is not None and ctx.email.enabled and web_payloads:
            subject = f"Stock Income Agent — {len(web_payloads)} alert(s) for {today.isoformat()}"
            body = _render_digest(today, web_payloads)
            try:
                ctx.email.send(subject=subject, body=body)
                await repo.insert_alert(
                    ctx.run_id, "new_recommendations" if summary else web_payloads[0][0],
                    {"digest": True, "alert_count": len(web_payloads)}, "email", now, now)
            except Exception as e:  # noqa: BLE001
                logger.warning("notifier: email send failed: %s", e)

        return StepResult(ok_count=len(web_payloads))


def _render_digest(today, web_payloads: list[tuple[str, dict]]) -> str:
    lines = [f"Stock Income Agent digest for {today.isoformat()}", ""]
    for type_, payload in web_payloads:
        lines.append(f"[{type_}] {payload}")
    return "\n".join(lines)
```

> The `shares` summation seeds with `positions[0].shares * 0` to keep a `Decimal` (avoids int/Decimal mixing). The email-channel alert's `type` reuses an allowed CHECK value (the digest row is a marker, surfaced as a sent record, not a per-type alert).

- [ ] **Step 4: Register the step** — in `backend/app/pipeline/steps/__init__.py`:

Add the import (alphabetical with the others):
```python
from app.pipeline.steps.notifier import NotifierStep
```
Append `NotifierStep()` to the list returned by `default_steps()`, after `IncomeTrackerStep()`:
```python
        ExecutorStep(),
        IncomeTrackerStep(),
        NotifierStep(),
```
Add `"NotifierStep",` to `__all__`.

- [ ] **Step 5: Pass `email` into the API background run** — in `backend/app/api/pipeline.py`, where `_run_in_background` builds the `StepContext` (currently `ctx = StepContext(repo=repo, sources=_make_sources(), run_id=run_id, llm=_make_llm())`), add the email seam:

```python
        from app.notify.email import make_email_sender
        ctx = StepContext(repo=repo, sources=_make_sources(), run_id=run_id,
                          llm=_make_llm(), email=make_email_sender(get_settings()))
```

> `get_settings` is already imported in `app/api/pipeline.py` (used by `_make_llm`). If not, add `from app.config import get_settings`.

- [ ] **Step 6: Run test to verify it passes**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_notifier.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add app/pipeline/steps/notifier.py app/pipeline/steps/__init__.py app/api/pipeline.py tests/pipeline/test_step_notifier.py
git commit -m "feat(backend): NotifierStep (Step 8) with web alerts + email digest"
```

---

### Task 7: Learner LLM prompt + schemas

**Files:**
- Modify: `backend/app/llm/prompts.py`
- Modify: `backend/app/llm/schemas.py`
- Test: `backend/tests/llm/test_learner_prompt.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/llm/test_learner_prompt.py`:

```python
from app.llm.prompts import LEARNER_PROMPT_VERSION, build_learner_prompt
from app.llm.schemas import LearnerOutput, LessonRetirement, ProposedLesson


def test_learner_prompt_includes_evidence_and_lessons():
    prompt = build_learner_prompt(
        active_lessons=["Old lesson about utilities"],
        feedback=[{"ticker": "KO", "outcome": "win", "total_return_pct": "0.03"}],
        income_events=[{"ticker": "KO", "type": "dividend", "amount": "48.5"}],
        safety_deltas=[{"ticker": "PEP", "current": 66, "previous": 80}],
        rejections=[{"ticker": "T", "type": "add_position"}],
    )
    assert "Old lesson about utilities" in prompt
    assert "KO" in prompt and "PEP" in prompt
    assert LEARNER_PROMPT_VERSION == "learner-v1"


def test_learner_output_schema():
    out = LearnerOutput(
        new_lessons=[ProposedLesson(pattern="x", sample_size=6, evidence_recommendation_ids=[1])],
        retirements=[LessonRetirement(lesson_id=3, reason="stale")],
    )
    assert out.new_lessons[0].sample_size == 6
    assert out.new_lessons[0].contradicts_lesson_id is None
    assert out.retirements[0].lesson_id == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/llm/test_learner_prompt.py -v`
Expected: FAIL (symbols not defined).

- [ ] **Step 3: Add the schemas** — append to `backend/app/llm/schemas.py`:

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

- [ ] **Step 4: Add the prompt** — append to `backend/app/llm/prompts.py`:

```python
LEARNER_PROMPT_VERSION = "learner-v1"

LEARNER_SYSTEM = (
    "You are a portfolio post-mortem analyst for a dividend + covered-call income agent. "
    "Review the past week's closed-position outcomes, income, dividend-safety changes, and "
    "user-rejected recommendations. Propose only falsifiable, evidence-backed lessons with a "
    "sample size of at least 5 closed positions. Flag any proposal that contradicts an active "
    "lesson by setting contradicts_lesson_id. Propose retirements for active lessons the "
    "evidence no longer supports. Do not propose vague advice like 'diversify' or 'be careful'."
)


def build_learner_prompt(*, active_lessons: list[str], feedback: list[dict],
                         income_events: list[dict], safety_deltas: list[dict],
                         rejections: list[dict]) -> str:
    lessons_block = "\n".join(f"- {x}" for x in active_lessons) or "(none yet)"
    return (
        f"Active lessons (propose retirements by id if unsupported):\n{lessons_block}\n\n"
        f"Closed-position feedback:\n{json.dumps(feedback, indent=2, default=str)}\n\n"
        f"Income events:\n{json.dumps(income_events, indent=2, default=str)}\n\n"
        f"Dividend-safety score changes:\n{json.dumps(safety_deltas, indent=2, default=str)}\n\n"
        f"User-rejected recommendations:\n{json.dumps(rejections, indent=2, default=str)}\n\n"
        "Propose new_lessons (each with pattern, sample_size, evidence_recommendation_ids, "
        "optional contradicts_lesson_id) and retirements (lesson_id + reason)."
    )
```

> `json` is already imported at the top of `prompts.py`.

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/llm/test_learner_prompt.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/llm/prompts.py app/llm/schemas.py tests/llm/test_learner_prompt.py
git commit -m "feat(backend): Learner LLM prompt and output schema"
```

---

### Task 8: LearnerStep + active-lessons injection into SafetyStep

**Files:**
- Create: `backend/app/pipeline/steps/learner.py`
- Modify: `backend/app/pipeline/steps/__init__.py` (export `LearnerStep`)
- Modify: `backend/app/pipeline/steps/safety.py` (inject `active_lessons()`)
- Test: `backend/tests/pipeline/test_step_learner.py`
- Test: `backend/tests/pipeline/test_safety_lessons.py`

- [ ] **Step 1: Write the failing LearnerStep test** — `backend/tests/pipeline/test_step_learner.py`:

```python
import os
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.llm.base import FakeLLMClient, LLMUsage
from app.llm.schemas import LearnerOutput, LessonRetirement, ProposedLesson
from app.pipeline.repo import PipelineRepo
from app.pipeline.steps.base import StepContext
from app.pipeline.steps.learner import LearnerStep
from app.sources.base import Sources


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


_now = datetime(2026, 6, 12, 17, 30, tzinfo=UTC)  # a Friday
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


def _ctx(repo, run_id, llm):
    return StepContext(repo=repo, sources=_sources, run_id=run_id, now=lambda: _now, llm=llm)


@pytest.mark.asyncio(loop_scope="session")
async def test_learner_adopts_gates_and_retires(session):
    repo = PipelineRepo(session)
    # an existing active lesson that will be contradicted by a larger-sample proposal
    old_id = await repo.insert_lesson("Small sample lesson to be superseded later", [1], 5, _now)
    run_id = await repo.start_run(now=_now)

    output = LearnerOutput(
        new_lessons=[
            ProposedLesson(pattern="REITs above 95% payout cut within two quarters reliably",
                           sample_size=7, evidence_recommendation_ids=[10, 11]),
            ProposedLesson(pattern="too short", sample_size=9, evidence_recommendation_ids=[]),  # fails falsifiability
            ProposedLesson(pattern="Low sample idea that should be dropped by the gate here",
                           sample_size=3, evidence_recommendation_ids=[]),  # fails sample size
            ProposedLesson(pattern="Bigger-sample replacement for the superseded lesson here now",
                           sample_size=9, evidence_recommendation_ids=[12],
                           contradicts_lesson_id=old_id),  # supersedes old_id
        ],
        retirements=[],
    )
    llm = FakeLLMClient(by_key={"learner": output}, usage=LLMUsage(10, 10, 0.001))

    result = await LearnerStep().run(_ctx(repo, run_id, llm))
    await session.commit()

    active = await repo.active_lessons()
    assert "REITs above 95% payout cut within two quarters reliably" in active
    assert "Bigger-sample replacement for the superseded lesson here now" in active
    assert "too short" not in active
    assert "Low sample idea that should be dropped by the gate here" not in active
    # the contradicted lesson was retired
    old = await repo.get_lesson(old_id)
    assert old.effective_until is not None
    assert "Small sample lesson to be superseded later" not in active
    assert result.ok_count == 2


@pytest.mark.asyncio(loop_scope="session")
async def test_learner_noop_without_llm(session):
    repo = PipelineRepo(session)
    run_id = await repo.start_run(now=_now)
    result = await LearnerStep().run(_ctx(repo, run_id, None))
    assert result.ok_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_learner.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Write the LearnerStep** — `backend/app/pipeline/steps/learner.py`:

```python
import asyncio
import logging
from datetime import timedelta

from app.analysis.learning import accept_lesson, survives_contradiction
from app.llm.prompts import LEARNER_PROMPT_VERSION, LEARNER_SYSTEM, build_learner_prompt
from app.llm.schemas import LearnerOutput
from app.pipeline.steps.base import Step, StepContext, StepResult

logger = logging.getLogger(__name__)

LEARNER_LOOKBACK_DAYS = 7


class LearnerStep(Step):
    name = "learner"
    is_critical = False

    async def run(self, ctx: StepContext) -> StepResult:
        if ctx.llm is None:
            logger.warning("learner: no LLM client configured; skipping")
            return StepResult(ok_count=0)

        repo = ctx.repo
        now = ctx.now()
        since = (now - timedelta(days=LEARNER_LOOKBACK_DAYS)).date()

        feedback = await repo.feedback_since(since)
        income = await repo.list_income_events(from_=since, to=now.date())
        rejections = await repo.rejected_recs_since(since)
        held = await repo.held_tickers()

        safety_deltas = []
        for ticker in held:
            delta = await repo.safety_score_delta(ticker)
            if delta is not None:
                safety_deltas.append({"ticker": ticker, "current": delta[0], "previous": delta[1]})

        active = await repo.list_lessons(active=True)
        active_patterns = [lesson.pattern for lesson in active]
        active_by_id = {lesson.id: lesson for lesson in active}

        prompt = build_learner_prompt(
            active_lessons=active_patterns,
            feedback=[{"ticker": f.recommendation_id, "outcome": f.outcome,
                       "total_return_pct": str(f.total_return_pct),
                       "exit_reason": f.exit_reason} for f in feedback],
            income_events=[{"ticker": ie.ticker, "type": ie.type,
                            "amount": str(ie.amount)} for ie in income],
            safety_deltas=safety_deltas,
            rejections=[{"ticker": r.ticker, "type": r.type} for r in rejections],
        )

        output, usage = await asyncio.to_thread(
            ctx.llm.complete_structured,
            system=LEARNER_SYSTEM, prompt=prompt, schema=LearnerOutput,
            prompt_version=LEARNER_PROMPT_VERSION, key="learner",
        )
        await repo.add_llm_usage(ctx.run_id, tokens=usage.input_tokens + usage.output_tokens,
                                 cost=usage.cost_usd)

        # LLM-proposed retirements first
        for retirement in output.retirements:
            await repo.retire_lesson(retirement.lesson_id, retirement.reason, now)

        adopted = 0
        for proposal in output.new_lessons:
            if not accept_lesson(pattern=proposal.pattern, sample_size=proposal.sample_size,
                                 active_patterns=active_patterns):
                continue
            if proposal.contradicts_lesson_id is not None:
                target = active_by_id.get(proposal.contradicts_lesson_id)
                if target is None or target.effective_until is not None:
                    continue
                if not survives_contradiction(proposal.sample_size, target.sample_size):
                    continue
                await repo.retire_lesson(target.id, "superseded by larger-sample lesson", now)
            await repo.insert_lesson(proposal.pattern, proposal.evidence_recommendation_ids,
                                     proposal.sample_size, now)
            active_patterns.append(proposal.pattern)  # catch in-batch duplicates
            adopted += 1

        logger.info("learner: adopted %d lessons, %d retirements proposed",
                    adopted, len(output.retirements))
        return StepResult(ok_count=adopted)
```

- [ ] **Step 4: Export LearnerStep** — in `backend/app/pipeline/steps/__init__.py` add the import `from app.pipeline.steps.learner import LearnerStep` and add `"LearnerStep",` to `__all__`. **Do not** add it to `default_steps()` — it runs on the Friday job only.

- [ ] **Step 5: Run the LearnerStep test to verify it passes**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_step_learner.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Write the SafetyStep injection test** — `backend/tests/pipeline/test_safety_lessons.py`:

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
                       cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    assert r.returncode == 0, r.stderr


_now = datetime(2026, 6, 9, 17, 15, tzinfo=UTC)
_today = _now.date()
_sources = Sources(universe=None, prices=None, dividends=None, options=None, news=None, fundamentals=None)


class CapturingLLM(FakeLLMClient):
    def __init__(self, by_key, usage):
        super().__init__(by_key=by_key, usage=usage)
        self.prompts: list[str] = []

    def complete_structured(self, *, system, prompt, schema, prompt_version, key):
        self.prompts.append(prompt)
        return super().complete_structured(
            system=system, prompt=prompt, schema=schema, prompt_version=prompt_version, key=key)


@pytest.mark.asyncio(loop_scope="session")
async def test_safety_prompt_includes_active_lessons(session):
    repo = PipelineRepo(session)
    await repo.upsert_stocks([StockMeta("MMM", "3M", "I", "B")], today=_today)
    await repo.insert_lesson("Industrials with falling FCF coverage cut within a year", [1], 6, _now)
    run_id = await repo.start_run(now=_now)
    # screen MMM so SafetyStep picks it up as a finalist (top_screened_tickers)
    await repo.insert_screening(run_id, "MMM", 80, {}, True, _now)
    await session.flush()

    assessment = SafetyAssessment(score=72, concerns=[], outlook="stable", reasoning="ok")
    llm = CapturingLLM(by_key={"MMM": assessment}, usage=LLMUsage(5, 5, 0.0005))
    await SafetyStep().run(StepContext(repo=repo, sources=_sources, run_id=run_id,
                                       now=lambda: _now, llm=llm))
    await session.commit()
    assert any("Industrials with falling FCF coverage cut within a year" in p for p in llm.prompts)
```

> `insert_screening(run_id, ticker, score, signals, passed, now)` is the real signature (verified). The goal is only to make MMM a finalist (`top_screened_tickers`) so SafetyStep issues a prompt for it.

- [ ] **Step 7: Inject active lessons in SafetyStep** — in `backend/app/pipeline/steps/safety.py`, replace the `active_lessons=[]` argument. Before the per-ticker loop, fetch once:

```python
        active = await ctx.repo.active_lessons()
```

and change the `build_safety_prompt(...)` call's `active_lessons=[]` to `active_lessons=active`. Remove the stale `# empty until Sub-project 5` comment.

- [ ] **Step 8: Run the safety injection test to verify it passes**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/pipeline/test_safety_lessons.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add app/pipeline/steps/learner.py app/pipeline/steps/__init__.py app/pipeline/steps/safety.py tests/pipeline/test_step_learner.py tests/pipeline/test_safety_lessons.py
git commit -m "feat(backend): LearnerStep + inject active lessons into SafetyStep"
```

---

### Task 9: Scheduler Friday learner job + main wiring

**Files:**
- Modify: `backend/app/pipeline/scheduler.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/pipeline/test_scheduler_learner.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/pipeline/test_scheduler_learner.py`:

```python
from app.pipeline.scheduler import PipelineScheduler, build_learner_cron_trigger


def test_learner_cron_trigger_is_friday_1730():
    trig = build_learner_cron_trigger()
    fields = {f.name: str(f) for f in trig.fields}
    assert fields["day_of_week"] == "fri"
    assert fields["hour"] == "17"
    assert fields["minute"] == "30"


def test_scheduler_registers_two_jobs_when_learner_given():
    called = []
    sched = PipelineScheduler(job_callable=lambda: called.append("daily"),
                              learner_callable=lambda: called.append("learner"))
    sched.start()
    try:
        ids = {job.id for job in sched._scheduler.get_jobs()}
        assert {"daily_pipeline", "weekly_learner"} <= ids
    finally:
        sched.stop()


def test_scheduler_single_job_when_no_learner():
    sched = PipelineScheduler(job_callable=lambda: None)
    sched.start()
    try:
        ids = {job.id for job in sched._scheduler.get_jobs()}
        assert ids == {"daily_pipeline"}
    finally:
        sched.stop()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/pipeline/test_scheduler_learner.py -v`
Expected: FAIL (`build_learner_cron_trigger` / `learner_callable` not defined).

- [ ] **Step 3: Update the scheduler** — in `backend/app/pipeline/scheduler.py`:

Add the trigger builder after `build_cron_trigger`:
```python
def build_learner_cron_trigger() -> CronTrigger:
    return CronTrigger(
        day_of_week="fri",
        hour=17,
        minute=30,
        timezone="America/New_York",
    )
```

Change `__init__` and `start`:
```python
    def __init__(self, job_callable: Callable, learner_callable: Callable | None = None) -> None:
        self._scheduler = AsyncIOScheduler()
        self._job_callable = job_callable
        self._learner_callable = learner_callable
        self._started = False

    def start(self) -> None:
        if self._started:
            return
        self._scheduler.add_job(
            func=self._job_callable,
            trigger=build_cron_trigger(),
            id="daily_pipeline",
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=3600,
        )
        if self._learner_callable is not None:
            self._scheduler.add_job(
                func=self._learner_callable,
                trigger=build_learner_cron_trigger(),
                id="weekly_learner",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=3600,
            )
        self._scheduler.start()
        self._started = True
        logger.info("pipeline scheduler started (weekdays 17:15; learner Fridays 17:30 ET)")
```

- [ ] **Step 4: Wire main.py** — in `backend/app/main.py`:

Add imports:
```python
from app.notify.email import make_email_sender
from app.config import get_settings
from app.pipeline.steps.learner import LearnerStep
```

Add an email seam to the existing `_scheduled_pipeline_job` ctx (so the Notifier can email there too):
```python
        ctx = StepContext(
            repo=repo, sources=_make_sources(), run_id=0,
            now=lambda: datetime.now(tz=UTC), llm=_make_llm(),
            email=make_email_sender(get_settings()),
        )
```

Add the learner job function (after `_scheduled_pipeline_job`):
```python
async def _scheduled_learner_job() -> None:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        ctx = StepContext(
            repo=repo, sources=_make_sources(), run_id=0,
            now=lambda: datetime.now(tz=UTC), llm=_make_llm(),
            email=make_email_sender(get_settings()),
        )
        try:
            await run_pipeline(ctx, steps=[LearnerStep()])
            await session.commit()
        except Exception:
            logger.exception("scheduled learner failed")
            await session.rollback()
```

Pass it to the scheduler in `lifespan`:
```python
    scheduler = PipelineScheduler(
        job_callable=_scheduled_pipeline_job,
        learner_callable=_scheduled_learner_job,
    )
```

- [ ] **Step 5: Run test to verify it passes**

Run: `.venv/bin/pytest tests/pipeline/test_scheduler_learner.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add app/pipeline/scheduler.py app/main.py tests/pipeline/test_scheduler_learner.py
git commit -m "feat(backend): Friday learner scheduler job + main wiring"
```

---

### Task 10: REST API — /lessons, /feedback, /settings

**Files:**
- Create: `backend/app/api/lessons.py`
- Create: `backend/app/api/feedback.py`
- Create: `backend/app/api/settings.py`
- Modify: `backend/app/main.py` (register routers)
- Test: `backend/tests/test_learning_api.py`

- [ ] **Step 1: Write the failing test** — `backend/tests/test_learning_api.py`:

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
async def test_lessons_feedback_settings_endpoints(session, monkeypatch, pg_container):
    # Point create_app()/get_session_factory() at the testcontainer (matches test_portfolio_api.py)
    for k, v in {
        "POSTGRES_USER": pg_container.username, "POSTGRES_PASSWORD": pg_container.password,
        "POSTGRES_DB": pg_container.dbname, "POSTGRES_HOST": pg_container.get_container_host_ip(),
        "POSTGRES_PORT": str(pg_container.get_exposed_port(5432)),
    }.items():
        monkeypatch.setenv(k, v)

    repo = PipelineRepo(session)
    now = datetime(2026, 6, 9, 17, 30, tzinfo=UTC)
    lid = await repo.insert_lesson("API lesson visible while active and falsifiable", [1], 6, now)
    ignored_id = await repo.insert_lesson("Ignored lesson should not appear when active only", [2], 6, now)
    await repo.set_lesson_ignored(ignored_id, True)
    await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # active only (default)
        r = await client.get("/lessons")
        assert r.status_code == 200
        ids = {row["id"] for row in r.json()}
        assert lid in ids and ignored_id not in ids

        # include all
        r = await client.get("/lessons?active=false")
        ids = {row["id"] for row in r.json()}
        assert {lid, ignored_id} <= ids

        # ignore toggle
        r = await client.post(f"/lessons/{lid}/ignore", json={"ignored": True})
        assert r.status_code == 200 and r.json()["user_ignored"] is True
        r = await client.post("/lessons/999999/ignore", json={"ignored": True})
        assert r.status_code == 404

        # feedback (empty range is fine — shape check)
        r = await client.get("/feedback")
        assert r.status_code == 200 and isinstance(r.json(), list)

        # settings snapshot
        r = await client.get("/settings")
        body = r.json()
        assert body["approval_modes"]["add_position"] == "manual"
        assert body["auto_execution_enabled"] is False
        assert "smtp_configured" in body["notifications"]
        assert "llm_cost_mtd" in body
```

> Env injection mirrors `tests/test_portfolio_api.py` (verified): a module `_migrate` fixture runs the migration (cwd = `dirname` **2×** for a top-level `tests/` file), and the test itself takes `monkeypatch` + `pg_container` and `monkeypatch.setenv(...)`s the `POSTGRES_*` vars so `create_app()` / `get_session_factory()` resolve to the testcontainer. No new conftest fixture is needed.

- [ ] **Step 2: Run test to verify it fails**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_learning_api.py -v`
Expected: FAIL (routers not mounted).

- [ ] **Step 3: Create the lessons router** — `backend/app/api/lessons.py`:

```python
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/lessons")


class IgnoreBody(BaseModel):
    ignored: bool = True


def _lesson(row) -> dict:
    return {
        "id": row.id,
        "pattern": row.pattern,
        "sample_size": row.sample_size,
        "evidence_recommendation_ids": list(row.evidence_recommendation_ids or []),
        "effective_from": row.effective_from.isoformat(),
        "effective_until": row.effective_until.isoformat() if row.effective_until is not None else None,
        "user_ignored": row.user_ignored,
        "retired_reason": row.retired_reason,
    }


@router.get("")
async def list_lessons(active: bool = True) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_lessons(active=active)
        return [_lesson(r) for r in rows]


@router.post("/{lesson_id}/ignore")
async def ignore_lesson(lesson_id: int, body: IgnoreBody) -> dict:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        updated = await repo.set_lesson_ignored(lesson_id, body.ignored)
        if updated is None:
            raise HTTPException(status_code=404, detail="lesson not found")
        await session.commit()
        return _lesson(updated)
```

- [ ] **Step 4: Create the feedback router** — `backend/app/api/feedback.py`:

```python
from datetime import date

from fastapi import APIRouter, Query

from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter()


def _feedback(row) -> dict:
    return {
        "id": row.id,
        "recommendation_id": row.recommendation_id,
        "position_id": row.position_id,
        "entry_price": float(row.entry_price),
        "exit_price": float(row.exit_price) if row.exit_price is not None else None,
        "capital_pnl": float(row.capital_pnl),
        "dividends_received": float(row.dividends_received),
        "premiums_collected": float(row.premiums_collected),
        "total_return_pct": float(row.total_return_pct),
        "held_days": row.held_days,
        "outcome": row.outcome,
        "exit_reason": row.exit_reason,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/feedback")
async def list_feedback(
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
) -> list[dict]:
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        rows = await repo.list_feedback(from_=from_, to=to)
        return [_feedback(r) for r in rows]
```

- [ ] **Step 5: Create the settings router** — `backend/app/api/settings.py`:

```python
from datetime import UTC, datetime

from fastapi import APIRouter

from app.config import get_settings
from app.db import get_session_factory
from app.pipeline.repo import PipelineRepo

router = APIRouter(prefix="/settings")

_REC_TYPES = ("add_position", "sell_position", "sell_covered_call")


@router.get("")
async def get_settings_snapshot() -> dict:
    settings = get_settings()
    factory = get_session_factory()
    async with factory() as session:
        repo = PipelineRepo(session)
        cost_mtd = await repo.llm_cost_month_to_date(datetime.now(tz=UTC).date())
    return {
        "approval_modes": {t: "manual" for t in _REC_TYPES},
        "auto_execution_enabled": False,
        "notifications": {
            "enabled": settings.notifications_enabled,
            "smtp_configured": settings.smtp_configured,
            "email_to": settings.notify_email_to,
        },
        "llm_model": settings.llm_model,
        "llm_cost_mtd": float(cost_mtd),
    }
```

- [ ] **Step 6: Register the routers** — in `backend/app/main.py`, add imports and `include_router` calls alongside the existing ones:

```python
from app.api.lessons import router as lessons_router
from app.api.feedback import router as feedback_router
from app.api.settings import router as settings_router
```
```python
    app.include_router(lessons_router)
    app.include_router(feedback_router)
    app.include_router(settings_router)
```

- [ ] **Step 7: Run test to verify it passes**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest tests/test_learning_api.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add app/api/lessons.py app/api/feedback.py app/api/settings.py app/main.py tests/test_learning_api.py
git commit -m "feat(backend): /lessons, /feedback, /settings REST endpoints"
```

---

### Task 11: Full suite, lint, README & .env.example

**Files:**
- Modify: `README.md`
- Modify: `backend/.env.example`

- [ ] **Step 1: Run the full default suite**

Run: `TESTCONTAINERS_RYUK_DISABLED=true .venv/bin/pytest -m "not slow" -q`
Expected: all pass. Fix any failures before proceeding. Pay attention to step-ordering tests (e.g. `tests/pipeline/test_default_steps_portfolio.py`) — if such a test asserts the exact `default_steps()` list, update it to include `NotifierStep` after `IncomeTrackerStep`.

- [ ] **Step 2: Lint**

Run: `.venv/bin/ruff check .`
Expected: no errors. Fix import-order/unused-import findings, then re-run.

- [ ] **Step 3: Update `backend/.env.example`** — append the SMTP/notification keys (blank/off by default):

```bash
# Notifications (Sub-project 5a) — email digest is OFF unless enabled AND SMTP configured
NOTIFICATIONS_ENABLED=false
SMTP_HOST=
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
NOTIFY_EMAIL_TO=
```

- [ ] **Step 4: Update README API tables** — in `README.md`, change `planned` → `✅ implemented` for:
  - `GET /lessons?active=true`
  - `POST /lessons/{id}/ignore`
  - `GET /feedback?from=&to=`
  - `GET /settings`

  In the daily-pipeline mermaid/prose, the Notifier (Step 8) is now implemented; remove any "planned" qualifier on it. Update the "Status" note under "## REST API" to mention learning + notifier endpoints landed in 5a. Update the backend test count in the dev-instructions block to the new total reported by Step 1.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "chore(backend): SP5a suite green + lint clean; update README and .env.example"
```

---

## Self-Review

### Spec coverage check

| Spec section | Task |
|---|---|
| §2 `agent_lessons` table | Task 0 (ORM) + Task 1 (migration) |
| §2 `alerts` table (CHECK constraints, run_id FK) | Task 0 + Task 1 |
| §2 "active" predicate defined once | Task 4 (`active_lessons`/`list_lessons`) |
| §3 NotifierStep, 5 alert types | Task 6 |
| §3 web-always + email-when-configured | Task 5 (seam) + Task 6 |
| §3 EmailSender seam (Smtp/Fake/Null) | Task 5 |
| §3 Notifier idempotency (delete-then-insert per run) | Task 4 (`delete_alerts_for_run`) + Task 6 |
| §4 Weekly Learner loop + gates | Task 8 |
| §4 contradiction dominance + retire-not-delete | Task 2 + Task 8 |
| §5 active-lessons injection into SafetyStep | Task 8 |
| §6 Friday scheduler job (17:30 ET) | Task 9 |
| §7 `/lessons`, `/feedback`, `/settings` (read-only) | Task 10 |
| §8 repo methods | Task 4 |
| §9 pure gates + alert builders | Task 2 + Task 3 |
| §10 Learner prompt + schema | Task 7 |
| §11 SMTP config fields + `smtp_configured` | Task 5 |
| §12 default_steps adds NotifierStep, Learner excluded | Task 6 + Task 8 |
| §13 design decisions | applied across Tasks 2–10 |
| §14 test strategy | tests in every task |

### Type-consistency check

- `insert_lesson(pattern, evidence_recommendation_ids, sample_size, now) -> int` — used by Task 8 ✓
- `active_lessons() -> list[str]` (patterns) — used by Task 6 (notifier concerns lookup is separate) and Task 8 SafetyStep ✓
- `list_lessons(active: bool=True) -> list[AgentLesson]` — used by `/lessons` (Task 10) and Learner (Task 8) ✓
- `safety_score_delta(ticker) -> tuple[int,int] | None` returns `(latest, previous)` — consumed by Notifier (`current, previous = delta`) and Learner (`delta[0], delta[1]`) consistently ✓
- `insert_alert(run_id, type_, payload, channel, sent_at, now) -> int` — Task 6 calls with all 6 args ✓
- `EmailSender` exposes `.enabled` and `.send(*, subject, body)` — Task 6 checks `ctx.email.enabled` and calls `.send(subject=, body=)` ✓
- `LearnerOutput.new_lessons[*].contradicts_lesson_id: int | None` — Task 8 reads it ✓
- `make_email_sender(settings) -> EmailSender` — Task 6 (api) + Task 9 (main) both call it ✓
- `StepContext.email: EmailSender | None = None` — Notifier guards `if ctx.email is not None` ✓

### Placeholder scan

No TBD/TODO/"handle edge cases". All referenced existing signatures were verified against `app/pipeline/repo.py`: `insert_safety_score(ticker, score, payout_ratio, fcf_coverage, debt_to_equity, consecutive_years_paid, concerns, reasoning, model, prompt_version, now)`, `insert_screening(run_id, ticker, score, signals, passed, now)`, `top_screened_tickers(run_id, limit)`, and the `monkeypatch`+`pg_container` API-test env pattern from `test_portfolio_api.py`. All new code is shown in full.
