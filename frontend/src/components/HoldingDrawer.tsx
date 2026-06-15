import { useQuery } from "@tanstack/react-query";

import { fetchStock, fetchStockNews, fetchStockDividends, fetchSafetyHistory } from "../api/stocks";
import { formatCurrency, formatDate } from "../lib/format";
import styles from "../styles/components.module.css";

export default function HoldingDrawer({ ticker, onClose }: { ticker: string; onClose: () => void }) {
  const stock = useQuery({ queryKey: ["stock", ticker], queryFn: () => fetchStock(ticker) });
  const news = useQuery({ queryKey: ["stock", ticker, "news"], queryFn: () => fetchStockNews(ticker) });
  const dividends = useQuery({
    queryKey: ["stock", ticker, "dividends"],
    queryFn: () => fetchStockDividends(ticker),
  });
  const safety = useQuery({
    queryKey: ["stock", ticker, "safety-history"],
    queryFn: () => fetchSafetyHistory(ticker),
  });

  return (
    <aside className={styles.drawer}>
      <button className={styles.drawerClose} onClick={onClose} aria-label="Close">
        ×
      </button>
      <h3 className={styles.heading}>{ticker}</h3>

      {stock.isLoading && <p className={styles.muted}>Loading…</p>}
      {stock.data && (
        <>
          <p className={styles.muted}>
            {stock.data.name} · {stock.data.sector}
          </p>
          {stock.data.latest_safety_score && (
            <section className={styles.section}>
              <h4>Safety {stock.data.latest_safety_score.score}</h4>
              <p>{stock.data.latest_safety_score.reasoning}</p>
              <ul>
                {stock.data.latest_safety_score.concerns.map((c) => (
                  <li key={c}>{c}</li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      <section className={styles.section}>
        <h4>Recent news</h4>
        {(news.data ?? []).length === 0 && <p className={styles.muted}>None</p>}
        <ul>
          {(news.data ?? []).map((n) => (
            <li key={n.id}>
              {formatDate(n.published_at)} — {n.title}
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.section}>
        <h4>Dividend history</h4>
        {(dividends.data ?? []).length === 0 && <p className={styles.muted}>None</p>}
        <ul>
          {(dividends.data ?? []).map((d) => (
            <li key={d.ex_date}>
              {formatDate(d.ex_date)} — {formatCurrency(d.amount_per_share)}
            </li>
          ))}
        </ul>
      </section>

      <section className={styles.section}>
        <h4>Safety score history</h4>
        {(safety.data ?? []).length === 0 && <p className={styles.muted}>None</p>}
        <ul>
          {(safety.data ?? []).map((s) => (
            <li key={s.scored_at}>
              {formatDate(s.scored_at)} — {s.score}
            </li>
          ))}
        </ul>
      </section>
    </aside>
  );
}
