// NOTE: more response types are added here by Task 3 of the dashboard-frontend plan.

export type RecType = "add_position" | "sell_position" | "sell_covered_call";

export interface Settings {
  approval_modes: Record<RecType, string>;
  auto_execution_enabled: boolean;
  notifications: { enabled: boolean; smtp_configured: boolean; email_to: string | null };
  llm_model: string;
  llm_cost_mtd: number;
}
