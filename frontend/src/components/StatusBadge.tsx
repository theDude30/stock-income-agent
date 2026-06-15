import styles from "../styles/components.module.css";

const STATUS_CLASS: Record<string, string> = {
  running: styles.running,
  success: styles.success,
  partial: styles.partial,
  failed: styles.failed,
};

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`${styles.badge} ${STATUS_CLASS[status] ?? styles.unknown}`}>{status}</span>
  );
}
