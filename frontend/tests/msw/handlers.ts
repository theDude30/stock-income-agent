import { http, HttpResponse } from "msw";

import type { Settings } from "../../src/api/types";

const emptySettings: Settings = {
  approval_modes: { add_position: "manual", sell_position: "manual", sell_covered_call: "manual" },
  auto_execution_enabled: false,
  notifications: { enabled: false, smtp_configured: false, email_to: null },
  llm_model: "claude-test",
  llm_cost_mtd: 0,
};

/** Handlers that return empty/zeroed data for every dashboard endpoint.
 *  Use in tests that only care about layout/navigation, not data. */
export const emptyHandlers = [
  http.get("/api/portfolio/holdings", () => HttpResponse.json([])),
  http.get("/api/portfolio/live", () =>
    HttpResponse.json({ as_of: "2026-06-14T00:00:00Z", positions: [] })),
  http.get("/api/portfolio/income", () => HttpResponse.json([])),
  http.get("/api/portfolio/income/calendar", () =>
    HttpResponse.json({ upcoming_dividends: [], expiring_calls: [] })),
  http.get("/api/portfolio/performance", () =>
    HttpResponse.json({
      ytd_income: 0, cost_basis: 0, ytd_capital_pnl: 0, ytd_total_return_pct: 0,
      spy_total_return_pct: null, treasury_1m_yield_pct: 4.2, treasury_ytd_return_pct: 0,
    })),
  http.get("/api/recommendations", () => HttpResponse.json([])),
  http.get("/api/pipeline/runs", () => HttpResponse.json([])),
  http.get("/api/lessons", () => HttpResponse.json([])),
  http.get("/api/feedback", () => HttpResponse.json([])),
  http.get("/api/settings", () => HttpResponse.json(emptySettings)),
];
