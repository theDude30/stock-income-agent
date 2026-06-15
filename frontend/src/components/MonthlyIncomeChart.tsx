import { BarChart, Bar, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from "recharts";

import type { MonthlyIncome } from "../lib/income";
import styles from "../styles/components.module.css";

export default function MonthlyIncomeChart({ data }: { data: MonthlyIncome[] }) {
  if (data.length === 0) {
    return (
      <figure className={styles.figure}>
        <figcaption className={styles.figcaption}>Monthly income by source</figcaption>
        <p className={styles.muted}>No income recorded yet.</p>
      </figure>
    );
  }

  return (
    <figure className={styles.figure}>
      <figcaption className={styles.figcaption}>Monthly income by source</figcaption>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data}>
          <XAxis dataKey="month" stroke="var(--color-muted)" />
          <YAxis stroke="var(--color-muted)" />
          <Tooltip />
          <Legend />
          <Bar dataKey="dividend" stackId="i" fill="var(--color-green)" name="Dividends" />
          <Bar dataKey="call_premium" stackId="i" fill="var(--color-accent)" name="Call premiums" />
          <Bar dataKey="assignment_gain" stackId="i" fill="var(--color-yellow)" name="Assignment gains" />
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}
