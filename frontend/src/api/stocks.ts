import { apiGet, qs } from "./client";
import type { StockDetail, PriceBar, DividendRow, NewsItem, SafetyScorePoint } from "./types";

export const fetchStock = (ticker: string) => apiGet<StockDetail>(`/stocks/${ticker}`);
export const fetchStockPrices = (ticker: string, from?: string, to?: string) =>
  apiGet<PriceBar[]>(`/stocks/${ticker}/prices${qs({ from, to })}`);
export const fetchStockDividends = (ticker: string) =>
  apiGet<DividendRow[]>(`/stocks/${ticker}/dividends`);
export const fetchStockNews = (ticker: string, limit = 20) =>
  apiGet<NewsItem[]>(`/stocks/${ticker}/news?limit=${limit}`);
export const fetchSafetyHistory = (ticker: string, limit = 20) =>
  apiGet<SafetyScorePoint[]>(`/stocks/${ticker}/safety-score/history?limit=${limit}`);
