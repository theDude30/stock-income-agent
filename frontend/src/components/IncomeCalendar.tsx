import type { IncomeCalendar as IncomeCalendarData } from "../api/types";
import { formatCurrency, formatDate } from "../lib/format";
import styles from "../styles/components.module.css";

export default function IncomeCalendar({ data }: { data: IncomeCalendarData }) {
  return (
    <div>
      <h3 className={styles.heading}>Next 30 days</h3>
      <h4 className={styles.muted}>Dividends</h4>
      {data.upcoming_dividends.length === 0 && <p className={styles.muted}>None</p>}
      <ul>
        {data.upcoming_dividends.map((d) => (
          <li key={`${d.ticker}-${d.ex_date}`}>
            {d.ticker} — ex {formatDate(d.ex_date)} — {formatCurrency(d.estimated_income)}
          </li>
        ))}
      </ul>
      <h4 className={styles.muted}>Option expirations</h4>
      {data.expiring_calls.length === 0 && <p className={styles.muted}>None</p>}
      <ul>
        {data.expiring_calls.map((c, i) => (
          <li key={`${c.ticker}-${c.expiration_date}-${i}`}>
            {c.ticker} — exp {formatDate(c.expiration_date)} — strike {c.strike ?? "—"} —{" "}
            {formatCurrency(c.premium)}
          </li>
        ))}
      </ul>
    </div>
  );
}
