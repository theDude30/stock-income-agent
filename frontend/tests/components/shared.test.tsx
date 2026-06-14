import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

import StatCard from "../../src/components/StatCard";
import StatusBadge from "../../src/components/StatusBadge";

describe("StatCard", () => {
  it("renders label, value, and optional sub-line", () => {
    render(<StatCard label="MTD Income" value="$1,234.50" sub="vs $1,000 last month" />);
    expect(screen.getByText("MTD Income")).toBeInTheDocument();
    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
    expect(screen.getByText(/vs \$1,000 last month/)).toBeInTheDocument();
  });
});

describe("StatusBadge", () => {
  it("renders the status text", () => {
    render(<StatusBadge status="success" />);
    expect(screen.getByText("success")).toBeInTheDocument();
  });
});
