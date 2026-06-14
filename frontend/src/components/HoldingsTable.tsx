import type { HoldingRow } from "../lib/holdings";
import { formatCurrency, formatPercent } from "../lib/format";
import styles from "../styles/components.module.css";

export interface HoldingsTableProps {
  rows: HoldingRow[];
  onSelect: (ticker: string) => void;
}

export default function HoldingsTable({ rows, onSelect }: HoldingsTableProps) {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Ticker</th>
          <th>Shares</th>
          <th>Avg cost</th>
          <th>Live price</th>
          <th>% of portfolio</th>
          <th>P&L</th>
          <th>Covered call</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} className={styles.row} onClick={() => onSelect(r.ticker)}>
            <td>
              {r.ticker}
              {r.stale && <span className={styles.staleTag}>stale</span>}
            </td>
            <td>{r.shares}</td>
            <td>{formatCurrency(r.avg_entry_price)}</td>
            <td>{formatCurrency(r.live_price)}</td>
            <td>{formatPercent(r.pct_of_portfolio)}</td>
            <td className={(r.live_pnl ?? r.unrealized_pnl ?? 0) >= 0 ? styles.pos : styles.neg}>
              {formatCurrency(r.live_pnl ?? r.unrealized_pnl)}
            </td>
            <td>
              {r.active_call
                ? `${r.active_call.strike ?? "—"} @ ${formatCurrency(r.active_call.premium)}`
                : "—"}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
