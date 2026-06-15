import StatCard from "./StatCard";
import MonthlyIncomeChart from "./MonthlyIncomeChart";
import type { Performance } from "../api/types";
import type { MonthlyIncome } from "../lib/income";
import type { FeedbackSummary } from "../lib/feedback";
import { formatPercent } from "../lib/format";
import styles from "../styles/components.module.css";

export interface PerformanceChartsProps {
  performance: Performance;
  monthly: MonthlyIncome[];
  feedback: FeedbackSummary;
}

export default function PerformanceCharts({
  performance,
  monthly,
  feedback,
}: PerformanceChartsProps) {
  return (
    <div>
      <div className={styles.cardGrid}>
        <StatCard label="Total Return YTD" value={formatPercent(performance.ytd_total_return_pct)} />
        <StatCard label="SPY Total Return" value={formatPercent(performance.spy_total_return_pct)} />
        <StatCard
          label="1-mo Treasury YTD"
          value={formatPercent(performance.treasury_ytd_return_pct)}
        />
      </div>

      <div className={styles.section} style={{ marginTop: "var(--space-4)" }}>
        <MonthlyIncomeChart data={monthly} />
      </div>

      <div className={styles.section}>
        <h3 className={styles.heading}>Closed positions</h3>
        <div className={styles.cardGrid}>
          <StatCard label="Positions closed" value={String(feedback.count)} />
          <StatCard label="Win rate" value={formatPercent(feedback.winRate)} />
          {Object.entries(feedback.byOutcome).map(([outcome, n]) => (
            <StatCard key={outcome} label={`Outcome: ${outcome}`} value={String(n)} />
          ))}
        </div>
      </div>
    </div>
  );
}
