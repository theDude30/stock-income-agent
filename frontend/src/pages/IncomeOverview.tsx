import { useQuery } from "@tanstack/react-query";

import { fetchIncome, fetchCalendar, fetchPerformance } from "../api/portfolio";
import StatCard from "../components/StatCard";
import MonthlyIncomeChart from "../components/MonthlyIncomeChart";
import IncomeCalendar from "../components/IncomeCalendar";
import { groupIncomeByMonth, sumIncomeSince } from "../lib/income";
import { formatCurrency, formatPercent } from "../lib/format";
import styles from "../styles/components.module.css";

function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

function isoMonthStart(): string {
  const d = new Date();
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}-01`;
}

export default function IncomeOverview() {
  const income = useQuery({ queryKey: ["portfolio", "income"], queryFn: () => fetchIncome() });
  const perf = useQuery({ queryKey: ["portfolio", "performance"], queryFn: fetchPerformance });
  const calendar = useQuery({ queryKey: ["portfolio", "calendar"], queryFn: () => fetchCalendar(30) });

  if (income.isLoading || perf.isLoading || calendar.isLoading) {
    return (
      <div>
        <h2>Income Overview</h2>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }
  if (income.isError || perf.isError || calendar.isError) {
    return (
      <div>
        <h2>Income Overview</h2>
        <p className={styles.muted}>Failed to load income data.</p>
      </div>
    );
  }

  const events = income.data ?? [];
  const monthly = groupIncomeByMonth(events);
  const mtd = sumIncomeSince(events, isoMonthStart());
  const trailing12 = sumIncomeSince(events, isoDaysAgo(365));
  const p = perf.data!;

  return (
    <div>
      <h2>Income Overview</h2>
      <div className={styles.cardGrid}>
        <StatCard label="MTD Income" value={formatCurrency(mtd)} />
        <StatCard label="Trailing 12-mo Income" value={formatCurrency(trailing12)} />
        <StatCard label="YTD Income" value={formatCurrency(p.ytd_income)} />
        <StatCard label="YTD Total Return" value={formatPercent(p.ytd_total_return_pct)} />
        <StatCard label="SPY Total Return" value={formatPercent(p.spy_total_return_pct)} />
        <StatCard
          label="1-mo Treasury"
          value={`${p.treasury_1m_yield_pct.toFixed(1)}%`}
          sub={`YTD ${formatPercent(p.treasury_ytd_return_pct)}`}
        />
      </div>

      <div className={styles.section} style={{ marginTop: "var(--space-4)" }}>
        <MonthlyIncomeChart data={monthly} />
      </div>

      <div className={styles.section}>
        <IncomeCalendar data={calendar.data!} />
      </div>
    </div>
  );
}
