// ---- Portfolio ----
export interface Holding {
  id: number;
  ticker: string;
  shares: number;
  avg_entry_price: number;
  current_price: number | null;
  price_date: string | null;
  unrealized_pnl: number | null;
  opened_at: string;
  active_call: { strike: number | null; expiration_date: string | null; premium: number } | null;
}

export interface LivePosition {
  id: number;
  ticker: string;
  shares: number;
  avg_entry_price: number;
  live_price: number | null;
  live_pnl: number | null;
  live_pnl_pct: number | null;
  stale: boolean;
  opened_at: string;
}

export interface LiveResponse {
  as_of: string;
  positions: LivePosition[];
}

export type IncomeType = "dividend" | "call_premium" | "assignment_gain";

export interface IncomeEvent {
  id: number;
  ticker: string;
  type: IncomeType;
  amount: number;
  event_date: string;
  source_position_id: number | null;
}

export interface IncomeCalendar {
  upcoming_dividends: {
    ticker: string;
    ex_date: string;
    amount_per_share: number;
    estimated_income: number;
  }[];
  expiring_calls: {
    ticker: string;
    expiration_date: string | null;
    strike: number | null;
    premium: number;
  }[];
}

export interface Performance {
  ytd_income: number;
  cost_basis: number;
  ytd_capital_pnl: number;
  ytd_total_return_pct: number; // fraction (0.05 == 5%)
  spy_total_return_pct: number | null; // fraction or null when fetch failed
  treasury_1m_yield_pct: number; // already a percent number (4.2 == 4.2%)
  treasury_ytd_return_pct: number; // fraction
}

// ---- Recommendations ----
export type RecType = "add_position" | "sell_position" | "sell_covered_call";
export type RecStatus = "pending" | "approved" | "rejected";

export interface RecommendationSummary {
  id: number;
  run_id: number;
  type: RecType;
  ticker: string;
  name: string | null;
  confidence: string;
  status: RecStatus;
  reasoning: string | null;
  created_at: string;
}

export interface RecommendationDetail extends RecommendationSummary {
  payload: Record<string, unknown>;
  signals_snapshot: Record<string, unknown>;
  llm_model: string | null;
  llm_prompt_version: string | null;
  approval_mode: string | null;
  decided_by: string | null;
  decided_at: string | null;
}

// ---- Stocks ----
export interface StockDetail {
  ticker: string;
  name: string | null;
  sector: string | null;
  industry: string | null;
  active: boolean;
  latest_screening: {
    dividend_quality_score: number;
    passed_screen: boolean;
    signals: Record<string, unknown>;
    created_at: string;
  } | null;
  latest_safety_score: {
    score: number;
    concerns: string[];
    reasoning: string | null;
    scored_at: string;
  } | null;
}

export interface PriceBar {
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  adj_close: number;
  volume: number;
}

export interface DividendRow {
  ex_date: string;
  pay_date: string | null;
  amount_per_share: number;
  frequency: string | null;
}

export interface NewsItem {
  id: number;
  published_at: string;
  source: string | null;
  url: string | null;
  title: string;
  summary: string | null;
  sentiment_score: number | null;
}

export interface SafetyScorePoint {
  score: number;
  concerns: string[];
  scored_at: string;
}

// ---- Pipeline ----
export interface PipelineRun {
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  steps_completed: string[];
  error_count: number;
}

// ---- Lessons ----
export interface Lesson {
  id: number;
  pattern: string;
  sample_size: number;
  evidence_recommendation_ids: number[];
  effective_from: string;
  effective_until: string | null;
  user_ignored: boolean;
  retired_reason: string | null;
}

// ---- Feedback ----
export interface Feedback {
  id: number;
  recommendation_id: number | null;
  position_id: number | null;
  entry_price: number;
  exit_price: number | null;
  capital_pnl: number;
  dividends_received: number;
  premiums_collected: number;
  total_return_pct: number;
  held_days: number | null;
  outcome: string | null;
  exit_reason: string | null;
  created_at: string;
}

// ---- Settings ----
export interface Settings {
  approval_modes: Record<RecType, string>;
  auto_execution_enabled: boolean;
  notifications: { enabled: boolean; smtp_configured: boolean; email_to: string | null };
  llm_model: string;
  llm_cost_mtd: number;
}
