import { apiGet } from "./client";

export type HealthResponse = {
  status: "ok" | "degraded";
  database: "ok" | "down";
};

export function fetchHealth(): Promise<HealthResponse> {
  return apiGet<HealthResponse>("/health");
}
