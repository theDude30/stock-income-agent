import { describe, expect, it } from "vitest";
import { formatCurrency, formatPercent, formatDate, monthKey } from "../../src/lib/format";

describe("format helpers", () => {
  it("formats currency and handles null", () => {
    expect(formatCurrency(1234.5)).toBe("$1,234.50");
    expect(formatCurrency(null)).toBe("—");
  });
  it("formats a fraction as percent", () => {
    expect(formatPercent(0.0523)).toBe("5.2%");
    expect(formatPercent(null)).toBe("—");
  });
  it("extracts a YYYY-MM month key from an ISO string", () => {
    expect(monthKey("2026-03-14T00:00:00Z")).toBe("2026-03");
  });
  it("formats an ISO date", () => {
    expect(formatDate("2026-03-14")).toMatch(/Mar 14, 2026/);
    expect(formatDate(null)).toBe("—");
  });
});
