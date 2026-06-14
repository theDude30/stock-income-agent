import { describe, expect, it } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import IncomeOverview from "../../src/pages/IncomeOverview";
import { renderWithProviders } from "../test-utils";
import { server } from "../msw/server";

describe("IncomeOverview", () => {
  it("renders income stat cards, the chart caption, and calendar events", async () => {
    server.use(
      http.get("/api/portfolio/income", () =>
        HttpResponse.json([
          { id: 1, ticker: "KO", type: "dividend", amount: 40, event_date: "2026-01-15", source_position_id: 1 },
          { id: 2, ticker: "KO", type: "call_premium", amount: 60, event_date: "2026-02-20", source_position_id: 1 },
        ]),
      ),
      http.get("/api/portfolio/performance", () =>
        HttpResponse.json({
          ytd_income: 100, cost_basis: 6000, ytd_capital_pnl: 300, ytd_total_return_pct: 0.0667,
          spy_total_return_pct: 0.05, treasury_1m_yield_pct: 4.2, treasury_ytd_return_pct: 0.02,
        }),
      ),
      http.get("/api/portfolio/income/calendar", () =>
        HttpResponse.json({
          upcoming_dividends: [
            { ticker: "KO", ex_date: "2026-06-20", amount_per_share: 0.46, estimated_income: 46 },
          ],
          expiring_calls: [
            { ticker: "KO", expiration_date: "2026-06-21", strike: 65, premium: 120 },
          ],
        }),
      ),
    );

    renderWithProviders(<IncomeOverview />);

    await waitFor(() => {
      expect(screen.getByText(/YTD Income/i)).toBeInTheDocument();
    });
    // YTD income value from performance (trailing-12mo may coincide for this fixture)
    expect(screen.getAllByText("$100.00").length).toBeGreaterThan(0);
    // SPY total return stat
    expect(screen.getByText(/SPY Total Return/i)).toBeInTheDocument();
    // chart caption present
    expect(screen.getByText(/monthly income/i)).toBeInTheDocument();
    // calendar lists the upcoming dividend
    expect(screen.getAllByText(/KO/).length).toBeGreaterThan(0);
    expect(screen.getByText(/\$46.00/)).toBeInTheDocument();
  });
});
