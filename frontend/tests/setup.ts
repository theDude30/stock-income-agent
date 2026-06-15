import "@testing-library/jest-dom/vitest";

import React from "react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

import { server } from "./msw/server";

// Recharts' ResponsiveContainer measures its parent (0x0 in jsdom) and renders
// nothing. Replace it with a fixed-size div so charts mount in tests.
vi.mock("recharts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("recharts")>();
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) =>
      React.createElement("div", { style: { width: 800, height: 400 } }, children),
  };
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
