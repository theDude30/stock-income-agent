import { describe, expect, it } from "vitest";
import { mergeHoldings } from "../../src/lib/holdings";
import type { Holding, LivePosition } from "../../src/api/types";

const holdings: Holding[] = [
  { id: 1, ticker: "KO", shares: 100, avg_entry_price: 60, current_price: 62, price_date: "2026-06-13",
    unrealized_pnl: 200, opened_at: "2026-01-02T00:00:00Z", active_call: null },
  { id: 2, ticker: "PG", shares: 50, avg_entry_price: 140, current_price: 150, price_date: "2026-06-13",
    unrealized_pnl: 500, opened_at: "2026-01-03T00:00:00Z", active_call: null },
];
const live: LivePosition[] = [
  { id: 1, ticker: "KO", shares: 100, avg_entry_price: 60, live_price: 63, live_pnl: 300,
    live_pnl_pct: 0.05, stale: false, opened_at: "2026-01-02T00:00:00Z" },
];

describe("mergeHoldings", () => {
  it("overlays live data and computes pct of portfolio by market value", () => {
    const rows = mergeHoldings(holdings, live);
    // KO mv = 63*100 = 6300; PG mv (no live -> current_price fallback) = 150*50 = 7500; total 13800
    expect(rows[0].live_price).toBe(63);
    expect(rows[0].pct_of_portfolio).toBeCloseTo(6300 / 13800, 5);
    expect(rows[1].stale).toBe(true); // no live row -> treated as stale
    expect(rows[1].live_price).toBe(150); // falls back to current_price
  });
});
