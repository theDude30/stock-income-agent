import { apiGet, apiPost } from "./client";
import type { RecommendationSummary, RecommendationDetail } from "./types";

export const fetchPendingRecommendations = () =>
  apiGet<RecommendationSummary[]>("/recommendations?status=pending");
export const approveRecommendation = (id: number) =>
  apiPost<RecommendationDetail>(`/recommendations/${id}/approve`);
export const rejectRecommendation = (id: number, reason?: string) =>
  apiPost<RecommendationDetail>(`/recommendations/${id}/reject`, { reason });
