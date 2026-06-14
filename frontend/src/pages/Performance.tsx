import { useQuery } from "@tanstack/react-query";

import { fetchPerformance, fetchIncome } from "../api/portfolio";
import { fetchFeedback } from "../api/feedback";
import PerformanceCharts from "../components/PerformanceCharts";
import { groupIncomeByMonth } from "../lib/income";
import { summarizeFeedback } from "../lib/feedback";
import styles from "../styles/components.module.css";

export default function Performance() {
  const perf = useQuery({ queryKey: ["portfolio", "performance"], queryFn: fetchPerformance });
  const income = useQuery({ queryKey: ["portfolio", "income"], queryFn: () => fetchIncome() });
  const feedback = useQuery({ queryKey: ["feedback"], queryFn: () => fetchFeedback() });

  if (perf.isLoading || income.isLoading || feedback.isLoading) {
    return (
      <div>
        <h2>Performance</h2>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }
  if (perf.isError || income.isError || feedback.isError) {
    return (
      <div>
        <h2>Performance</h2>
        <p className={styles.muted}>Failed to load performance data.</p>
      </div>
    );
  }

  return (
    <div>
      <h2>Performance</h2>
      <PerformanceCharts
        performance={perf.data!}
        monthly={groupIncomeByMonth(income.data ?? [])}
        feedback={summarizeFeedback(feedback.data ?? [])}
      />
    </div>
  );
}
