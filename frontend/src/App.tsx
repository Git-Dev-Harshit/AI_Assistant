import { useEffect, useState } from "react";

type Health = { status: string; version: string; compute: { device: string; name: string } };

export default function App() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
      .then(setHealth)
      .catch((err: Error) => setError(err.message));
  }, []);

  return (
    <main className="container">
      <h1>Knowledge Assistant</h1>
      {health && (
        <p>
          Backend v{health.version} is {health.status} ({health.compute.device}: {health.compute.name})
        </p>
      )}
      {error && <p className="error">Backend unreachable: {error}</p>}
    </main>
  );
}
