import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import {
  fetchPendingRecommendations,
  approveRecommendation,
  rejectRecommendation,
} from "../api/recommendations";
import RecommendationsTable from "../components/RecommendationsTable";
import styles from "../styles/components.module.css";

export default function Recommendations() {
  const queryClient = useQueryClient();
  const [busyId, setBusyId] = useState<number | null>(null);

  const recs = useQuery({
    queryKey: ["recommendations", "pending"],
    queryFn: fetchPendingRecommendations,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["recommendations", "pending"] });

  const approve = useMutation({
    mutationFn: (id: number) => approveRecommendation(id),
    onMutate: (id) => setBusyId(id),
    onSettled: () => setBusyId(null),
    onSuccess: invalidate,
  });

  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: number; reason: string }) =>
      rejectRecommendation(id, reason || undefined),
    onMutate: ({ id }) => setBusyId(id),
    onSettled: () => setBusyId(null),
    onSuccess: invalidate,
  });

  if (recs.isLoading) {
    return (
      <div>
        <h2>Recommendations</h2>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }
  if (recs.isError) {
    return (
      <div>
        <h2>Recommendations</h2>
        <p className={styles.muted}>Failed to load recommendations.</p>
      </div>
    );
  }

  const rows = recs.data ?? [];

  return (
    <div>
      <h2>Recommendations</h2>
      {rows.length === 0 && <p className={styles.muted}>No pending recommendations.</p>}
      {rows.length > 0 && (
        <RecommendationsTable
          rows={rows}
          busyId={busyId}
          onApprove={(id) => approve.mutate(id)}
          onReject={(id, reason) => reject.mutate({ id, reason })}
        />
      )}
    </div>
  );
}
