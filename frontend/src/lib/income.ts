import type { IncomeEvent } from "../api/types";
import { monthKey } from "./format";

export interface MonthlyIncome {
  month: string;
  dividend: number;
  call_premium: number;
  assignment_gain: number;
  total: number;
}

export function groupIncomeByMonth(events: IncomeEvent[]): MonthlyIncome[] {
  const map = new Map<string, MonthlyIncome>();
  for (const e of events) {
    const key = monthKey(e.event_date);
    const row =
      map.get(key) ?? { month: key, dividend: 0, call_premium: 0, assignment_gain: 0, total: 0 };
    row[e.type] += e.amount;
    row.total += e.amount;
    map.set(key, row);
  }
  return [...map.values()].sort((a, b) => a.month.localeCompare(b.month));
}

/** Sum of event amounts with event_date >= sinceIso (ISO date strings compare lexically). */
export function sumIncomeSince(events: IncomeEvent[], sinceIso: string): number {
  return events.filter((e) => e.event_date >= sinceIso).reduce((s, e) => s + e.amount, 0);
}
