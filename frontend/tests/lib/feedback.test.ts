import { describe, expect, it } from "vitest";
import { summarizeFeedback } from "../../src/lib/feedback";
import type { Feedback } from "../../src/api/types";

const rows: Feedback[] = [
  { id: 1, recommendation_id: 1, position_id: 1, entry_price: 60, exit_price: 65, capital_pnl: 500,
    dividends_received: 40, premiums_collected: 0, total_return_pct: 0.09, held_days: 120,
    outcome: "win", exit_reason: "target", created_at: "2026-05-01T00:00:00Z" },
  { id: 2, recommendation_id: 2, position_id: 2, entry_price: 140, exit_price: 130, capital_pnl: -500,
    dividends_received: 20, premiums_collected: 0, total_return_pct: -0.03, held_days: 90,
    outcome: "loss", exit_reason: "stop", created_at: "2026-05-10T00:00:00Z" },
];

describe("summarizeFeedback", () => {
  it("computes count, win rate, and outcome counts", () => {
    const s = summarizeFeedback(rows);
    expect(s.count).toBe(2);
    expect(s.winRate).toBeCloseTo(0.5, 5);
    expect(s.byOutcome).toEqual({ win: 1, loss: 1 });
  });
  it("handles empty input without dividing by zero", () => {
    expect(summarizeFeedback([])).toEqual({ count: 0, winRate: 0, byOutcome: {} });
  });
});
