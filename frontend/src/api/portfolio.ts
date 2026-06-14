import { apiGet, qs } from "./client";
import type { Holding, LiveResponse, IncomeEvent, IncomeCalendar, Performance } from "./types";

export const fetchHoldings = () => apiGet<Holding[]>("/portfolio/holdings");
export const fetchLive = () => apiGet<LiveResponse>("/portfolio/live");
export const fetchIncome = (from?: string, to?: string) =>
  apiGet<IncomeEvent[]>(`/portfolio/income${qs({ from, to })}`);
export const fetchCalendar = (days = 30) =>
  apiGet<IncomeCalendar>(`/portfolio/income/calendar?days=${days}`);
export const fetchPerformance = () => apiGet<Performance>("/portfolio/performance");
