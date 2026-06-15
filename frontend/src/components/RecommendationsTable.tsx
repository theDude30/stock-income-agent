import { useState } from "react";

import type { RecommendationSummary } from "../api/types";
import styles from "../styles/components.module.css";

const TYPE_LABELS: Record<string, string> = {
  add_position: "Add Position",
  sell_position: "Sell Position",
  sell_covered_call: "Sell Covered Call",
};

export interface RecommendationsTableProps {
  rows: RecommendationSummary[];
  busyId: number | null;
  onApprove: (id: number) => void;
  onReject: (id: number, reason: string) => void;
}

export default function RecommendationsTable({
  rows,
  busyId,
  onApprove,
  onReject,
}: RecommendationsTableProps) {
  return (
    <table className={styles.table}>
      <thead>
        <tr>
          <th>Name</th>
          <th>Position</th>
          <th>Recommendation</th>
          <th>Details</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <RecommendationRow
            key={r.id}
            row={r}
            pending={busyId === r.id}
            onApprove={onApprove}
            onReject={onReject}
          />
        ))}
      </tbody>
    </table>
  );
}

function RecommendationRow({
  row,
  pending,
  onApprove,
  onReject,
}: {
  row: RecommendationSummary;
  pending: boolean;
  onApprove: (id: number) => void;
  onReject: (id: number, reason: string) => void;
}) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");

  return (
    <tr>
      <td>{row.name ?? row.ticker}</td>
      <td>{row.ticker}</td>
      <td>
        {TYPE_LABELS[row.type] ?? row.type}{" "}
        <span className={styles.badge}>{row.confidence}</span>
      </td>
      <td>
        {row.reasoning && <p>{row.reasoning}</p>}
        {!rejecting ? (
          <div className={styles.recActions}>
            <button
              className={`${styles.btn} ${styles.btnPrimary} ${pending ? styles.btnDisabled : ""}`}
              disabled={pending}
              onClick={() => onApprove(row.id)}
            >
              Approve
            </button>
            <button className={styles.btn} disabled={pending} onClick={() => setRejecting(true)}>
              Reject
            </button>
          </div>
        ) : (
          <div className={styles.recActions}>
            <input
              placeholder="Reason (optional)"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
            <button
              className={styles.btn}
              disabled={pending}
              onClick={() => onReject(row.id, reason)}
            >
              Confirm reject
            </button>
          </div>
        )}
      </td>
    </tr>
  );
}
