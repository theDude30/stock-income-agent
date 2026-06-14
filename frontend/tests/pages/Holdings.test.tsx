import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Holdings from "../../src/pages/Holdings";
import { renderWithProviders } from "../test-utils";
import { server } from "../msw/server";

describe("Holdings", () => {
  it("renders rows and opens the drawer with lazily-fetched detail on row click", async () => {
    server.use(
      http.get("/api/portfolio/holdings", () =>
        HttpResponse.json([
          { id: 1, ticker: "KO", shares: 100, avg_entry_price: 60, current_price: 62,
            price_date: "2026-06-13", unrealized_pnl: 200, opened_at: "2026-01-02T00:00:00Z",
            active_call: null },
        ]),
      ),
      http.get("/api/portfolio/live", () =>
        HttpResponse.json({
          as_of: "2026-06-14T00:00:00Z",
          positions: [
            { id: 1, ticker: "KO", shares: 100, avg_entry_price: 60, live_price: 63, live_pnl: 300,
              live_pnl_pct: 0.05, stale: false, opened_at: "2026-01-02T00:00:00Z" },
          ],
        }),
      ),
      http.get("/api/stocks/KO", () =>
        HttpResponse.json({
          ticker: "KO", name: "Coca-Cola", sector: "Consumer", industry: "Beverages", active: true,
          latest_screening: { dividend_quality_score: 88, passed_screen: true, signals: {}, created_at: "2026-06-01T00:00:00Z" },
          latest_safety_score: { score: 90, concerns: ["payout creeping up"], reasoning: "Strong moat.", scored_at: "2026-06-01T00:00:00Z" },
        }),
      ),
      http.get("/api/stocks/KO/news", () => HttpResponse.json([])),
      http.get("/api/stocks/KO/dividends", () => HttpResponse.json([])),
      http.get("/api/stocks/KO/safety-score/history", () => HttpResponse.json([])),
    );

    renderWithProviders(<Holdings />);

    await waitFor(() => expect(screen.getByText("KO")).toBeInTheDocument());
    // live price overlaid
    expect(screen.getByText("$63.00")).toBeInTheDocument();

    fireEvent.click(screen.getByText("KO"));

    // drawer fetches /stocks/KO and shows the LLM reasoning
    await waitFor(() => expect(screen.getByText(/Strong moat/)).toBeInTheDocument());
    expect(screen.getByText(/payout creeping up/)).toBeInTheDocument();
  });
});
