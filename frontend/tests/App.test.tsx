import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "../src/App";

function renderWithClient(ui: React.ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders title and healthy status", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({ status: "ok", database: "ok" }),
    });

    renderWithClient(<App />);

    expect(screen.getByRole("heading", { name: /stock income agent/i })).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText(/api: ok/i)).toBeInTheDocument();
      expect(screen.getByText(/database: ok/i)).toBeInTheDocument();
    });
  });

  it("renders error state when health fetch fails", async () => {
    (fetch as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new Error("boom"));

    renderWithClient(<App />);

    await waitFor(() => {
      expect(screen.getByText(/unreachable/i)).toBeInTheDocument();
    });
  });
});
