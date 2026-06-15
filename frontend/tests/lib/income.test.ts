import { describe, expect, it } from "vitest";
import { groupIncomeByMonth, sumIncomeSince } from "../../src/lib/income";
import type { IncomeEvent } from "../../src/api/types";

const events: IncomeEvent[] = [
  { id: 1, ticker: "KO", type: "dividend", amount: 40, event_date: "2026-01-15", source_position_id: 1 },
  { id: 2, ticker: "KO", type: "call_premium", amount: 60, event_date: "2026-01-20", source_position_id: 1 },
  { id: 3, ticker: "PG", type: "dividend", amount: 30, event_date: "2026-02-10", source_position_id: 2 },
];

describe("income aggregation", () => {
  it("groups by month and type, sorted ascending", () => {
    const rows = groupIncomeByMonth(events);
    expect(rows).toEqual([
      { month: "2026-01", dividend: 40, call_premium: 60, assignment_gain: 0, total: 100 },
      { month: "2026-02", dividend: 30, call_premium: 0, assignment_gain: 0, total: 30 },
    ]);
  });
  it("sums income on/after a cutoff date", () => {
    expect(sumIncomeSince(events, "2026-02-01")).toBe(30);
  });
});
