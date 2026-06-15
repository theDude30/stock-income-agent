import { apiGet, qs } from "./client";
import type { Feedback } from "./types";

export const fetchFeedback = (from?: string, to?: string) =>
  apiGet<Feedback[]>(`/feedback${qs({ from, to })}`);
