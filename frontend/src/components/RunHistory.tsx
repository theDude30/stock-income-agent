import StatusBadge from "./StatusBadge";
import type { PipelineRun } from "../api/types";
import { formatDate } from "../lib/format";
import styles from "../styles/components.module.css";

const STEPS = ["screen", "safety", "options", "recommend"];

export interface RunHistoryProps {
  runs: PipelineRun[];
  onRerun: (step: string) => void;
}

export default function RunHistory({ runs, onRerun }: RunHistoryProps) {
  return (
    <div>
      <h3 className={styles.heading}>Run history</h3>
      <div className={styles.recActions}>
        {STEPS.map((s) => (
          <button key={s} className={styles.btn} onClick={() => onRerun(s)}>
            Re-run {s}
          </button>
        ))}
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Run</th>
            <th>Started</th>
            <th>Status</th>
            <th>Steps</th>
            <th>Errors</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{formatDate(r.started_at)}</td>
              <td>
                <StatusBadge status={r.status} />
              </td>
              <td>{r.steps_completed.join(", ")}</td>
              <td>{r.error_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
