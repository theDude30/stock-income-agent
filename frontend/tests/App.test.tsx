import { describe, expect, it, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";

import App from "../src/App";
import { renderWithProviders } from "./test-utils";
import { server } from "./msw/server";
import { emptyHandlers } from "./msw/handlers";

describe("App routing", () => {
  beforeEach(() => server.use(...emptyHandlers));

  it("redirects '/' to the Income tab", () => {
    renderWithProviders(<App />, { route: "/" });
    expect(screen.getByRole("heading", { name: /income overview/i })).toBeInTheDocument();
  });

  it("navigates to Holdings when its tab is clicked", () => {
    renderWithProviders(<App />, { route: "/income" });
    fireEvent.click(screen.getByRole("link", { name: /holdings/i }));
    expect(screen.getByRole("heading", { name: /holdings/i, level: 2 })).toBeInTheDocument();
  });
});
