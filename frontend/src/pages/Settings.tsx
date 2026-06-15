import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";

import { fetchRuns, triggerRun } from "../api/pipeline";
import { fetchSettings } from "../api/settings";
import { fetchLessons, ignoreLesson } from "../api/lessons";
import RunHistory from "../components/RunHistory";
import LessonsPanel from "../components/LessonsPanel";
import { formatCurrency } from "../lib/format";
import type { RecType } from "../api/types";
import styles from "../styles/components.module.css";

const REC_TYPES: RecType[] = ["add_position", "sell_position", "sell_covered_call"];

export default function Settings() {
  const queryClient = useQueryClient();
  const runs = useQuery({ queryKey: ["pipeline", "runs"], queryFn: () => fetchRuns(30) });
  const settings = useQuery({ queryKey: ["settings"], queryFn: fetchSettings });
  const lessons = useQuery({ queryKey: ["lessons", true], queryFn: () => fetchLessons(true) });

  const [rerunMessage, setRerunMessage] = useState<string | null>(null);

  const rerun = useMutation({
    mutationFn: (step?: string) => triggerRun(step),
    onSuccess: (_data, step) => {
      setRerunMessage(step ? `Triggered ${step} run.` : "Triggered full pipeline run.");
      queryClient.invalidateQueries({ queryKey: ["pipeline", "runs"] });
    },
    onError: (_err, step) => {
      setRerunMessage(step ? `Failed to trigger ${step} run.` : "Failed to trigger full pipeline run.");
    },
  });
  const toggleIgnore = useMutation({
    mutationFn: ({ id, ignored }: { id: number; ignored: boolean }) => ignoreLesson(id, ignored),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["lessons", true] }),
  });

  if (settings.isLoading || runs.isLoading || lessons.isLoading) {
    return (
      <div>
        <h2>Settings</h2>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }

  if (settings.isError || runs.isError || lessons.isError) {
    return (
      <div>
        <h2>Settings</h2>
        <p className={styles.muted}>Failed to load settings.</p>
      </div>
    );
  }

  const s = settings.data;

  return (
    <div>
      <h2>Settings</h2>

      <section className={styles.section}>
        <RunHistory runs={runs.data ?? []} onRerun={(step) => rerun.mutate(step)} />
        {rerunMessage && <p className={styles.muted}>{rerunMessage}</p>}
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>Approval modes (Phase 2 — read-only)</h3>
        {REC_TYPES.map((t) => (
          <label key={t} style={{ display: "block" }}>
            <input
              type="checkbox"
              disabled
              checked={s?.approval_modes[t] === "auto"}
              readOnly
            />{" "}
            {t}: {s?.approval_modes[t]}
          </label>
        ))}
      </section>

      <section className={styles.section}>
        <h3 className={styles.heading}>Notifications</h3>
        <p className={styles.muted}>
          enabled: {String(s?.notifications.enabled)} · smtp:{" "}
          {String(s?.notifications.smtp_configured)} · to: {s?.notifications.email_to ?? "—"}
        </p>
        <h3 className={styles.heading}>LLM</h3>
        <p className={styles.muted}>
          {s?.llm_model} · cost MTD {formatCurrency(s?.llm_cost_mtd ?? 0)}
        </p>
      </section>

      <section className={styles.section}>
        <LessonsPanel
          lessons={lessons.data ?? []}
          onToggleIgnore={(id, ignored) => toggleIgnore.mutate({ id, ignored })}
        />
      </section>
    </div>
  );
}
