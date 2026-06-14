import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchRecommendation } from "../api/recommendations";
import type { RecommendationSummary } from "../api/types";
import styles from "../styles/components.module.css";

export interface RecommendationCardProps {
  summary: RecommendationSummary;
  onApprove: (id: number) => void;
  onReject: (id: number, reason: string) => void;
  pending: boolean;
}

export default function RecommendationCard({
  summary,
  onApprove,
  onReject,
  pending,
}: RecommendationCardProps) {
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const detail = useQuery({
    queryKey: ["recommendation", summary.id],
    queryFn: () => fetchRecommendation(summary.id),
  });

  return (
    <div className={styles.card}>
      <div className={styles.label}>
        {summary.type} · {summary.confidence}
      </div>
      <div className={styles.value}>{summary.ticker}</div>
      {detail.isLoading && <p className={styles.muted}>Loading reasoning…</p>}
      {detail.data && <p>{detail.data.reasoning}</p>}

      {!rejecting ? (
        <div className={styles.recActions}>
          <button
            className={`${styles.btn} ${styles.btnPrimary} ${pending ? styles.btnDisabled : ""}`}
            disabled={pending}
            onClick={() => onApprove(summary.id)}
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
            onClick={() => onReject(summary.id, reason)}
          >
            Confirm reject
          </button>
        </div>
      )}
    </div>
  );
}
