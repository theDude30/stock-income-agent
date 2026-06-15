import type { Feedback } from "../api/types";

export interface FeedbackSummary {
  count: number;
  winRate: number; // fraction of rows with total_return_pct > 0
  byOutcome: Record<string, number>;
}

export function summarizeFeedback(rows: Feedback[]): FeedbackSummary {
  if (rows.length === 0) return { count: 0, winRate: 0, byOutcome: {} };
  const wins = rows.filter((r) => r.total_return_pct > 0).length;
  const byOutcome: Record<string, number> = {};
  for (const r of rows) {
    const key = r.outcome ?? "unknown";
    byOutcome[key] = (byOutcome[key] ?? 0) + 1;
  }
  return { count: rows.length, winRate: wins / rows.length, byOutcome };
}
