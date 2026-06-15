import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Performance from "../../src/pages/Performance";
import { renderWithProviders } from "../test-utils";
import { server } from "../msw/server";

describe("Performance", () => {
  it("renders total-return tiles, the income chart caption, and outcome tiles", async () => {
    server.use(
      http.get("/api/portfolio/performance", () =>
        HttpResponse.json({
          ytd_income: 500, cost_basis: 10000, ytd_capital_pnl: 800, ytd_total_return_pct: 0.13,
          spy_total_return_pct: 0.1, treasury_1m_yield_pct: 4.2, treasury_ytd_return_pct: 0.02,
        }),
      ),
      http.get("/api/portfolio/income", () =>
        HttpResponse.json([
          { id: 1, ticker: "KO", type: "dividend", amount: 40, event_date: "2026-01-15", source_position_id: 1 },
        ]),
      ),
      http.get("/api/feedback", () =>
        HttpResponse.json([
          { id: 1, recommendation_id: 1, position_id: 1, entry_price: 60, exit_price: 65,
            capital_pnl: 500, dividends_received: 40, premiums_collected: 0, total_return_pct: 0.09,
            held_days: 120, outcome: "win", exit_reason: "target", created_at: "2026-05-01T00:00:00Z" },
        ]),
      ),
    );

    renderWithProviders(<Performance />);

    await waitFor(() => expect(screen.getByText(/Total Return YTD/i)).toBeInTheDocument());
    expect(screen.getByText("13.0%")).toBeInTheDocument(); // portfolio total return
    expect(screen.getByText("10.0%")).toBeInTheDocument(); // SPY
    expect(screen.getByText(/monthly income/i)).toBeInTheDocument();
    expect(screen.getByText(/Win rate/i)).toBeInTheDocument();
    expect(screen.getByText("100.0%")).toBeInTheDocument(); // 1/1 wins
  });
});
