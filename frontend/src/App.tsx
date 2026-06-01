import { useQuery } from "@tanstack/react-query";
import { fetchHealth } from "./api/health";

export default function App() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["health"],
    queryFn: fetchHealth,
    refetchInterval: 30_000,
  });

  return (
    <main style={{ fontFamily: "system-ui, sans-serif", padding: "2rem" }}>
      <h1>Stock Income Agent</h1>
      {isLoading && <p>Checking health...</p>}
      {isError && <p>API unreachable.</p>}
      {data && (
        <ul>
          <li>API: {data.status}</li>
          <li>Database: {data.database}</li>
        </ul>
      )}
    </main>
  );
}
