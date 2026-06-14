import type { Holding, LivePosition } from "../api/types";

export interface HoldingRow extends Holding {
  live_price: number | null;
  live_pnl: number | null;
  live_pnl_pct: number | null;
  stale: boolean;
  pct_of_portfolio: number; // fraction
}

export function mergeHoldings(holdings: Holding[], live: LivePosition[]): HoldingRow[] {
  const liveById = new Map(live.map((p) => [p.id, p]));
  const enriched = holdings.map((h) => {
    const l = liveById.get(h.id);
    const live_price = l?.live_price ?? h.current_price ?? null;
    const mv = (live_price ?? h.avg_entry_price) * h.shares;
    return {
      ...h,
      live_price,
      live_pnl: l?.live_pnl ?? null,
      live_pnl_pct: l?.live_pnl_pct ?? null,
      stale: l ? l.stale : true,
      mv,
    };
  });
  const total = enriched.reduce((s, r) => s + r.mv, 0);
  return enriched.map(({ mv, ...r }) => ({
    ...r,
    pct_of_portfolio: total > 0 ? mv / total : 0,
  }));
}
