import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchHoldings, fetchLive } from "../api/portfolio";
import HoldingsTable from "../components/HoldingsTable";
import HoldingDrawer from "../components/HoldingDrawer";
import { mergeHoldings } from "../lib/holdings";
import styles from "../styles/components.module.css";

export default function Holdings() {
  const [selected, setSelected] = useState<string | null>(null);
  const holdings = useQuery({ queryKey: ["portfolio", "holdings"], queryFn: fetchHoldings });
  const live = useQuery({
    queryKey: ["portfolio", "live"],
    queryFn: fetchLive,
    refetchInterval: 120_000,
  });

  if (holdings.isLoading) {
    return (
      <div>
        <h2>Holdings</h2>
        <p className={styles.muted}>Loading…</p>
      </div>
    );
  }
  if (holdings.isError) {
    return (
      <div>
        <h2>Holdings</h2>
        <p className={styles.muted}>Failed to load holdings.</p>
      </div>
    );
  }

  const rows = mergeHoldings(holdings.data ?? [], live.data?.positions ?? []);

  return (
    <div>
      <h2>Holdings</h2>
      <HoldingsTable rows={rows} onSelect={setSelected} />
      {selected && <HoldingDrawer ticker={selected} onClose={() => setSelected(null)} />}
    </div>
  );
}
