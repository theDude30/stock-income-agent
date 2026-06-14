import { apiGet, apiPost } from "./client";
import type { PipelineRun } from "./types";

export const fetchRuns = (limit = 30) => apiGet<PipelineRun[]>(`/pipeline/runs?limit=${limit}`);
export const triggerRun = (step?: string) =>
  apiPost<{ run_id: number }>(`/pipeline/run${step ? `?step=${step}` : ""}`);
