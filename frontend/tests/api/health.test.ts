import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

describe("api/health", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns parsed health response when api returns 200", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", database: "ok" }),
    });

    const { fetchHealth } = await import("../../src/api/health");
    const result = await fetchHealth();
    expect(result).toEqual({ status: "ok", database: "ok" });
  });

  it("throws when api returns non-2xx", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: false,
      status: 503,
      json: async () => ({ status: "degraded", database: "down" }),
    });

    const { fetchHealth } = await import("../../src/api/health");
    await expect(fetchHealth()).rejects.toThrow(/503/);
  });
});
