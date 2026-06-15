import { describe, expect, it } from "vitest";
import { http, HttpResponse } from "msw";

import { server } from "../msw/server";
import { apiPost, qs } from "../../src/api/client";

describe("qs", () => {
  it("omits undefined params and returns empty string when nothing left", () => {
    expect(qs({ from: undefined, to: undefined })).toBe("");
    expect(qs({ from: "2026-01-01", to: undefined })).toBe("?from=2026-01-01");
    expect(qs({ days: 30 })).toBe("?days=30");
  });
});

describe("apiPost", () => {
  it("posts JSON and returns parsed body", async () => {
    server.use(
      http.post("/api/things/1/do", async ({ request }) => {
        const body = (await request.json()) as { reason: string };
        return HttpResponse.json({ ok: true, reason: body.reason });
      }),
    );
    const result = await apiPost<{ ok: boolean; reason: string }>("/things/1/do", { reason: "x" });
    expect(result).toEqual({ ok: true, reason: "x" });
  });

  it("throws on non-2xx", async () => {
    server.use(http.post("/api/boom", () => new HttpResponse(null, { status: 409 })));
    await expect(apiPost("/boom")).rejects.toThrow(/409/);
  });
});
