import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import Recommendations from "../../src/pages/Recommendations";
import { renderWithProviders } from "../test-utils";
import { server } from "../msw/server";

const summary = {
  id: 5, run_id: 1, type: "add_position", ticker: "KO", name: "Coca-Cola Co",
  confidence: "high", status: "pending", reasoning: "Wide moat, safe payout.",
  created_at: "2026-06-14T00:00:00Z",
};

describe("Recommendations", () => {
  it("shows pending rows with reasoning and removes a row after approval", async () => {
    let approved = false;
    server.use(
      http.get("/api/recommendations", () =>
        HttpResponse.json(approved ? [] : [summary])),
      http.post("/api/recommendations/5/approve", () => {
        approved = true;
        return HttpResponse.json({ ...summary, status: "approved" });
      }),
    );

    renderWithProviders(<Recommendations />);

    await waitFor(() => expect(screen.getByText(/Wide moat/)).toBeInTheDocument());
    expect(screen.getByText(/KO/)).toBeInTheDocument();
    expect(screen.getByText(/Coca-Cola Co/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /approve/i }));

    await waitFor(() => expect(screen.queryByText(/Wide moat/)).not.toBeInTheDocument());
  });

  it("sends a reason when rejecting", async () => {
    let rejectedReason: string | null = null;
    server.use(
      http.get("/api/recommendations", () => HttpResponse.json([summary])),
      http.post("/api/recommendations/5/reject", async ({ request }) => {
        const body = (await request.json()) as { reason: string };
        rejectedReason = body.reason;
        return HttpResponse.json({ ...summary, status: "rejected" });
      }),
    );

    renderWithProviders(<Recommendations />);
    await waitFor(() => expect(screen.getByText(/Wide moat/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /reject/i }));
    fireEvent.change(screen.getByPlaceholderText(/reason/i), { target: { value: "overvalued" } });
    fireEvent.click(screen.getByRole("button", { name: /confirm reject/i }));

    await waitFor(() => expect(rejectedReason).toBe("overvalued"));
  });
});
