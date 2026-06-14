import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { server } from "../msw/server";
import { fetchLive, fetchIncome } from "../../src/api/portfolio";
import { rejectRecommendation } from "../../src/api/recommendations";
import { triggerRun } from "../../src/api/pipeline";

describe("api modules", () => {
  it("fetchLive parses the live response", async () => {
    server.use(
      http.get("/api/portfolio/live", () =>
        HttpResponse.json({
          as_of: "2026-06-14T12:00:00Z",
          positions: [
            { id: 1, ticker: "KO", shares: 100, avg_entry_price: 60, live_price: 63,
              live_pnl: 300, live_pnl_pct: 0.05, stale: false, opened_at: "2026-01-02T00:00:00Z" },
          ],
        }),
      ),
    );
    const data = await fetchLive();
    expect(data.positions[0].ticker).toBe("KO");
    expect(data.positions[0].live_pnl_pct).toBe(0.05);
  });

  it("fetchIncome appends from/to query params", async () => {
    server.use(
      http.get("/api/portfolio/income", ({ request }) => {
        const url = new URL(request.url);
        return HttpResponse.json([
          { id: 1, ticker: "KO", type: "dividend", amount: 42,
            event_date: url.searchParams.get("from"), source_position_id: 1 },
        ]);
      }),
    );
    const data = await fetchIncome("2026-01-01", "2026-06-01");
    expect(data[0].event_date).toBe("2026-01-01");
  });

  it("rejectRecommendation posts the reason", async () => {
    server.use(
      http.post("/api/recommendations/7/reject", async ({ request }) => {
        const body = (await request.json()) as { reason: string };
        return HttpResponse.json({
          id: 7, run_id: 1, type: "add_position", ticker: "KO", confidence: "high",
          status: "rejected", created_at: "2026-06-14T00:00:00Z", payload: {},
          reasoning: null, signals_snapshot: {}, llm_model: null, llm_prompt_version: null,
          approval_mode: null, decided_by: "user", decided_at: "2026-06-14T01:00:00Z",
          rejected_reason: body.reason,
        });
      }),
    );
    const rec = await rejectRecommendation(7, "too risky");
    expect(rec.status).toBe("rejected");
  });

  it("triggerRun adds the step query param", async () => {
    server.use(
      http.post("/api/pipeline/run", ({ request }) => {
        const url = new URL(request.url);
        return HttpResponse.json({ run_id: url.searchParams.get("step") === "screen" ? 99 : 1 });
      }),
    );
    expect((await triggerRun("screen")).run_id).toBe(99);
  });
});
