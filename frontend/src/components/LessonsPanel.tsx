import type { Lesson } from "../api/types";
import styles from "../styles/components.module.css";

export interface LessonsPanelProps {
  lessons: Lesson[];
  onToggleIgnore: (id: number, ignored: boolean) => void;
}

export default function LessonsPanel({ lessons, onToggleIgnore }: LessonsPanelProps) {
  return (
    <div>
      <h3 className={styles.heading}>Active lessons</h3>
      {lessons.length === 0 && <p className={styles.muted}>No active lessons.</p>}
      <ul>
        {lessons.map((l) => (
          <li key={l.id}>
            {l.pattern} <span className={styles.muted}>(n={l.sample_size})</span>{" "}
            <button className={styles.btn} onClick={() => onToggleIgnore(l.id, !l.user_ignored)}>
              {l.user_ignored ? "Un-ignore" : "Ignore"}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
