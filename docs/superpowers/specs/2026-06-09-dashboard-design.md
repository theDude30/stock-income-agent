# Dashboard — Sub-project 5b Design

**Date:** 2026-06-09
**Depends on:** Sub-projects 1–4 (all REST endpoints: health, pipeline, recommendations, portfolio, trades, positions) **and Sub-project 5a** (`GET /lessons`, `POST /lessons/{id}/ignore`, `GET /feedback`, `GET /settings`). Frontend scaffold from SP1: React 18 + Vite + TypeScript + TanStack Query, with `apiGet` in `src/api/client.ts` and the health-check pattern in `src/api/health.ts` / `App.tsx`.

> **Scope split:** "Sub-project 5 — Dashboard & learning loop" is split into **5a (backend learning loop + notifier, built first)** and **this, 5b (the React dashboard)**. 5b consumes 5a's endpoints, so 5a must be merged before 5b's Learning/Settings views work end-to-end. See `2026-06-09-learning-loop-notifier-design.md`.

---

## 1. What this sub-project delivers

The five-tab React dashboard from master design §7, wired to live data. **Income, not P&L, is the headline** — the default route is the Income Overview.

5b also adds the **handful of read-only backend endpoints the UI requires that don't exist yet**: `GET /portfolio/live` (mark-to-market), the **completed** `GET /portfolio/performance` honesty view (SPY total return + Treasury baseline — SP4 shipped only a close-price proxy), and the stock-detail read endpoints for the Holdings drawer. Everything else the UI needs already exists from SP1–4 + 5a.

After this sub-project the product is feature-complete for Phase 1: a user opens `localhost:3000`, sees income/holdings/recommendations/performance, approves recs, and inspects the agent's lessons and run history.

**Explicitly out of scope (Phase 2):**
- Mutating settings (`PATCH /settings`, kill switch), approval-mode **toggles** that actually flip `auto_approve.<type>`. In 5b these controls render **read-only / disabled** with a "Phase 2" affordance.
- Auth / remote exposure (master: localhost only in v1).

---

## 2. Backend additions (read-only endpoints the UI needs)

These are thin SELECT-or-cache endpoints; they live in the existing `app/api/` files and reuse `PipelineRepo` + the market-data source seam.

### `app/api/portfolio.py` additions

| Method | Path | Description |
|---|---|---|
| `GET` | `/portfolio/live` | Open positions enriched with **mark-to-market** P&L. Live prices come from a per-ticker **2-minute TTL cache** wrapping the existing market-data client (`_make_sources()`), to avoid hammering yfinance on every dashboard poll. Response per position: holdings fields + `live_price`, `live_pnl`, `live_pnl_pct`, and a top-level `as_of` timestamp. Falls back to latest DB close (with `stale: true`) if the live fetch fails. |
| `GET` | `/portfolio/performance` (**completed**) | Extends the SP4 partial view to the full honesty check: YTD **total return** (capital appreciation + dividends + premiums + assignment gains), **SPY total return** (yfinance SPY adjusted-close incl. dividends over the same window), and the **1-month Treasury** baseline. Treasury yield is a config value (`treasury_1m_yield_pct`, default annualized %), optionally refreshed from `^IRX`; documented as a config constant, not a live requirement. |

`PriceCache` (new, `app/market/price_cache.py`): `async def get(ticker) -> tuple[Decimal, datetime]` with a 120-second TTL dict; injected into the portfolio router via the same factory pattern as the pipeline sources. Pure-ish and unit-testable with a fake clock + fake client.

### `app/api/stocks.py` additions (Holdings drawer)

| Method | Path | Description |
|---|---|---|
| `GET` | `/stocks/{ticker}` | Stock row + latest screening signals + latest safety score. |
| `GET` | `/stocks/{ticker}/prices?from=&to=` | OHLCV history (for the drawer price/dividend chart). |
| `GET` | `/stocks/{ticker}/dividends` | Dividend history (amount_per_share, ex_date), newest first. |
| `GET` | `/stocks/{ticker}/news?limit=` | Recent `news_items` for the ticker. |
| `GET` | `/stocks/{ticker}/safety-score/history?limit=` | Safety-score series from `dividend_safety_scores` (the existing `…/safety-score` returns only the latest). |

All five are straight reads against SP1–3 tables; `from`/`to` use the `Query(None, alias="from")` pattern. They flip the corresponding README rows from `planned` → `✅ implemented`.

---

## 3. Frontend architecture

**Stack (additions to existing):** `react-router-dom@6` (5 tab routes with real URLs), `recharts@2` (master-named charting). Existing: React 18, TanStack Query, TypeScript, Vite, Vitest + Testing Library + MSW.

**Data layer:** TanStack Query for **all** server state. One typed client module per resource calls `apiGet`/`apiPost`. Query keys are arrays (`["portfolio","live"]`). `staleTime` 30 s default; `/portfolio/live` uses `refetchInterval: 120_000` to match the backend cache TTL. Mutations (approve/reject, ignore-lesson, manual step re-run) invalidate the relevant query keys on success.

**Styling:** CSS Modules + a single `styles/tokens.css` (colors, spacing, typography) — **no UI framework** (Tailwind/MUI), consistent with the project's "stay local & cheap / minimal" ethos and the existing inline-style baseline. Green/yellow/red status colors are tokens shared by run-history and safety badges.

**No auth, no global state library** beyond TanStack Query (master: localhost only).

### File structure

```
frontend/src/
  main.tsx                 # add <BrowserRouter> + <QueryClientProvider>
  App.tsx                  # layout shell: <NavTabs/> + <Outlet/>
  api/
    client.ts              # existing apiGet; ADD apiPost<T>(path, body)
    types.ts               # shared response types (one per endpoint)
    portfolio.ts  recommendations.ts  trades.ts
    stocks.ts  lessons.ts  feedback.ts  settings.ts  pipeline.ts
  pages/
    IncomeOverview.tsx     # route "/" (default) and "/income"
    Holdings.tsx           # "/holdings"
    Recommendations.tsx    # "/recommendations"
    Performance.tsx        # "/performance"
    Settings.tsx           # "/settings"
  components/
    NavTabs.tsx  StatCard.tsx  StatusBadge.tsx
    MonthlyIncomeChart.tsx  IncomeCalendar.tsx
    HoldingsTable.tsx  HoldingDrawer.tsx
    RecommendationCard.tsx  PerformanceCharts.tsx
    RunHistory.tsx  LessonsPanel.tsx
  styles/ tokens.css  *.module.css
```

---

## 4. The five tabs

### Tab 1 — Income Overview *(default route)*
- **Stat cards:** forward-12mo projected income, MTD income, trailing-12mo income, current portfolio yield, vs. SPY dividend yield, vs. 1-month Treasury.
- **Main chart** (`MonthlyIncomeChart`, Recharts stacked bar): monthly income split by `dividend` / `call_premium` / `assignment_gain`, with an SPY-equivalent-dividends comparison line.
- **Right panel** (`IncomeCalendar`): next-30-day expected dividends + option expirations.
- **Data:** `GET /portfolio/income?from=&to=`, `GET /portfolio/income/calendar?days=30`, `GET /portfolio/performance` (yields + baselines).

### Tab 2 — Holdings
- **Table** (`HoldingsTable`): ticker, shares, avg cost, current (live) price, % of portfolio, annual yield, projected annual income, DividendQualityScore + trend arrow, active covered call (strike/exp/premium), days to next ex-div, last safety review.
- **Row click → drawer** (`HoldingDrawer`): full LLM safety reasoning, recent news, dividend-history chart, safety-score-history sparkline.
- **Data:** `GET /portfolio/holdings` + `GET /portfolio/live` (price/PnL overlay); drawer: `GET /stocks/{ticker}`, `/news`, `/dividends`, `/safety-score/history`.

### Tab 3 — Recommendations
- **Cards grouped by type** (`add_position`, `sell_position`, `sell_covered_call`); each shows full LLM reasoning + `signals_snapshot` and `[Approve]` / `[Reject]` (reject opens a reason field).
- Approve/reject calls the existing POST endpoints; on success, invalidate the recommendations query so the card disappears.
- **Data:** `GET /recommendations?status=pending`, `POST /recommendations/{id}/approve`, `/reject`.

### Tab 4 — Performance
- **Total return YTD** (capital + income + premiums) vs. **SPY total return** vs. **1-month Treasury** — the honesty check.
- **Realized income** monthly chart, trailing 24 months.
- **Hit rates:** `add_position` outcomes, % of calls expired worthless / assigned / rolled, % of safety warnings that proved correct.
- **Dividend cuts:** how many holdings cut dividends and whether the agent warned.
- **Data:** completed `GET /portfolio/performance`, `GET /feedback?from=&to=`, `GET /portfolio/income`.

### Tab 5 — Settings & Agent Status
- **Pipeline run history** (`RunHistory`): last 30 runs with green/yellow/red `StatusBadge`; **manual re-run per step** via `POST /pipeline/run?step=`.
- **Approval-mode toggles** per rec type — rendered **read-only/disabled** (Phase 1: always `manual`).
- **Safety rails** + **API-key** state — read-only display (configured / not configured; keys masked).
- **Notifications:** show `enabled` + `smtp_configured` + `email_to` from `GET /settings`.
- **Universe selector:** S&P 500 only (static in v1).
- **Active lessons viewer** (`LessonsPanel`): list active lessons, toggle ignored (`POST /lessons/{id}/ignore`), expand to see retired ones (`GET /lessons?active=false`).
- **LLM cost month-to-date** from `GET /settings`.
- **Data:** `GET /pipeline/runs`, `POST /pipeline/run?step=`, `GET /settings`, `GET /lessons`, `POST /lessons/{id}/ignore`.

---

## 5. API client modules & types

Each module is a thin typed wrapper. `client.ts` gains:

```ts
export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}
```

Example module (`api/portfolio.ts`):

```ts
import { apiGet } from "./client";
import type { Holding, LivePosition, IncomeRange, IncomeCalendar, Performance } from "./types";

export const fetchHoldings    = () => apiGet<Holding[]>("/portfolio/holdings");
export const fetchLive        = () => apiGet<{ as_of: string; positions: LivePosition[] }>("/portfolio/live");
export const fetchIncome      = (from?: string, to?: string) =>
  apiGet<IncomeRange>(`/portfolio/income${qs({ from, to })}`);
export const fetchCalendar    = (days = 30) => apiGet<IncomeCalendar>(`/portfolio/income/calendar?days=${days}`);
export const fetchPerformance = () => apiGet<Performance>("/portfolio/performance");
```

`types.ts` declares one interface per response shape, matching the FastAPI dict keys exactly (Decimals serialize as `number`, dates/datetimes as ISO `string`). A small `qs()` helper builds query strings and omits undefined params.

---

## 6. Shared components

| Component | Responsibility |
|---|---|
| `NavTabs` | The five `<NavLink>`s; highlights the active route. |
| `StatCard` | Label + big value + optional comparison sub-line; used across Income & Performance. |
| `StatusBadge` | Maps `running`/`success`/`partial`/`failed` → token colors; reused by run history and safety. |
| `MonthlyIncomeChart` | Recharts stacked bar + comparison line; pure props in. |
| `IncomeCalendar` | Grouped list of upcoming dividends + expirations. |
| `HoldingsTable` + `HoldingDrawer` | Table with row-select; drawer fetches detail lazily on open. |
| `RecommendationCard` | Reasoning + approve/reject with pending state. |
| `PerformanceCharts` | Total-return comparison + 24-month income chart + hit-rate tiles. |
| `RunHistory` + `LessonsPanel` | Settings-tab widgets. |

Every component takes data via props; pages own the TanStack Query calls and pass results down (keeps components pure and trivially testable).

---

## 7. Key design decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | 5b owns the read endpoints the UI needs but that don't exist (`/portfolio/live`, completed `/performance`, `/stocks/{ticker}` detail trio + safety history) | Keeps the dashboard self-contained and shippable; these are thin reads, not a separate sub-project. |
| 2 | `react-router-dom` with real URLs over state-based tabs | Bookmarkable/linkable tabs, browser back/forward, and clean code-splitting per page. |
| 3 | Recharts for all charts | Named in the master design; declarative, good stacked-bar + comparison-line support. |
| 4 | TanStack Query owns all server state; `/portfolio/live` polls at 120 s | Matches the backend 2-minute price cache exactly — no redundant fetches, no extra state library. |
| 5 | CSS Modules + token stylesheet, no UI framework | Consistent with the minimal existing setup and the project's cost/footprint goals; avoids a heavy dependency for ~10 components. |
| 6 | `/portfolio/live` uses a 120 s server-side per-ticker price cache with stale-fallback | Honors yfinance politeness; the dashboard can poll freely; a fetch failure degrades to last DB close (`stale:true`) instead of erroring the whole tab. |
| 7 | Phase-2 controls (approval toggles, kill switch, settings mutation) render read-only/disabled | The backend mutation doesn't exist in Phase 1 (5a deferred it); showing the controls disabled communicates the seam without faking behavior. |
| 8 | Treasury baseline is a config constant (optionally `^IRX`-refreshed) | Avoids a hard dependency on a live rates feed for the honesty check; the value is explicit and auditable. |
| 9 | Pages fetch, components are pure-props | Components render deterministically from props → fast, isolated Testing-Library tests with no query mocking inside components. |

---

## 8. Test strategy

- **Per page** (Vitest + Testing Library + **MSW**, extending the existing `tests/setup.ts` + health test pattern): mock each endpoint, assert the key data renders, and assert loading + error states.
  - **IncomeOverview:** stat cards show formatted income; stacked chart receives the monthly series; calendar lists upcoming events.
  - **Holdings:** table rows render from holdings+live; clicking a row opens the drawer and triggers the lazy detail fetch.
  - **Recommendations:** approve fires `POST …/approve` and the card is removed after invalidation; reject sends the reason.
  - **Performance:** total-return vs SPY vs Treasury tiles render; 24-month chart gets data.
  - **Settings:** run history maps statuses to badge colors; manual re-run posts `?step=`; lessons panel toggles ignore via POST; Phase-2 controls are disabled.
- **Components** (pure): `StatCard`, `StatusBadge`, `MonthlyIncomeChart` (snapshot of props→DOM), `IncomeCalendar` grouping.
- **Client:** `apiPost` success + non-2xx throw; `qs()` omits undefined.
- **Backend additions** (pytest + testcontainers / ASGITransport, matching SP4): `PriceCache` TTL + stale-fallback with a fake clock/client; `/portfolio/live` shape; completed `/performance` includes SPY-total-return + Treasury fields; each `/stocks/{ticker}/…` read endpoint.
- **No live network** in the default suite — yfinance behind the existing fake source; MSW for the frontend.

---

## 9. What's complete after this sub-project

- The Phase-1 product is feature-complete: all five dashboard tabs live at `localhost:3000`, reading real pipeline output.
- README API tables flip to `✅ implemented` for `/portfolio/live`, the completed `/portfolio/performance`, and the `/stocks/{ticker}` read endpoints; the Phasing table marks **Phase 5 — Dashboard & learning loop ✅ done**.
- **Still deferred (Phase 2):** auto-approval per rec type, settings mutation + kill switch, safety-rail enforcement, and any real-broker/live-trading work (Phase 3).
