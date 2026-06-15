import { describe, expect, it } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import SettingsPage from "../../src/pages/Settings";
import { renderWithProviders } from "../test-utils";
import { server } from "../msw/server";

describe("Settings", () => {
  it("renders run badges, settings, lessons; re-runs a step; toggles a lesson", async () => {
    let triggeredStep: string | null = null;
    let ignoredCalled = false;
    server.use(
      http.get("/api/pipeline/runs", () =>
        HttpResponse.json([
          { id: 10, started_at: "2026-06-14T00:00:00Z", finished_at: "2026-06-14T00:05:00Z",
            status: "success", steps_completed: ["screen", "safety"], error_count: 0 },
        ]),
      ),
      http.post("/api/pipeline/run", ({ request }) => {
        triggeredStep = new URL(request.url).searchParams.get("step");
        return HttpResponse.json({ run_id: 11 });
      }),
      http.get("/api/settings", () =>
        HttpResponse.json({
          approval_modes: { add_position: "manual", sell_position: "manual", sell_covered_call: "manual" },
          auto_execution_enabled: false,
          notifications: { enabled: true, smtp_configured: true, email_to: "me@example.com" },
          llm_model: "claude-sonnet", llm_cost_mtd: 1.23,
        }),
      ),
      http.get("/api/lessons", () =>
        HttpResponse.json([
          { id: 1, pattern: "Avoid high payout REITs", sample_size: 5,
            evidence_recommendation_ids: [1, 2], effective_from: "2026-05-01T00:00:00Z",
            effective_until: null, user_ignored: false, retired_reason: null },
        ]),
      ),
      http.post("/api/lessons/1/ignore", async () => {
        ignoredCalled = true;
        return HttpResponse.json({
          id: 1, pattern: "Avoid high payout REITs", sample_size: 5,
          evidence_recommendation_ids: [1, 2], effective_from: "2026-05-01T00:00:00Z",
          effective_until: null, user_ignored: true, retired_reason: null,
        });
      }),
    );

    renderWithProviders(<SettingsPage />);

    await waitFor(() => expect(screen.getByText("success")).toBeInTheDocument());
    // settings read-only display
    expect(screen.getByText(/me@example.com/)).toBeInTheDocument();
    expect(screen.getByText(/claude-sonnet/)).toBeInTheDocument();
    // approval toggle rendered disabled
    const toggles = screen.getAllByRole("checkbox");
    expect(toggles[0]).toBeDisabled();

    // manual re-run
    fireEvent.click(screen.getByRole("button", { name: /re-run screen/i }));
    await waitFor(() => expect(triggeredStep).toBe("screen"));

    // lesson ignore toggle
    fireEvent.click(screen.getByRole("button", { name: /ignore/i }));
    await waitFor(() => expect(ignoredCalled).toBe(true));
  });
});
