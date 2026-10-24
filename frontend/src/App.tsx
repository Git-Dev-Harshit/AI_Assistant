import { useEffect, useState } from "react";
import { AskPanel } from "./components/AskPanel";
import { DocumentsPanel } from "./components/DocumentsPanel";

type Health = {
  status: string;
  version: string;
  compute: { device: string; name: string };
  llm: { provider: string; model: string };
};

type Tab = "ask" | "documents";

export default function App() {
  const [tab, setTab] = useState<Tab>("ask");
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState(false);

  useEffect(() => {
    fetch("/api/health")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: Health) => setHealth(data))
      .catch(() => setHealthError(true));
  }, []);

  return (
    <>
      <header className="header">
        <div className="container header-inner">
          <h1>Knowledge Assistant</h1>
          <div className="status small" title={health?.compute.name}>
            {health && (
              <>
                <span className="dot dot-ok" /> {health.compute.device.toUpperCase()} · {health.llm.model}
                {health.llm.provider === "mock" && " (demo mode)"}
              </>
            )}
            {healthError && (
              <>
                <span className="dot dot-error" /> Backend unreachable
              </>
            )}
          </div>
        </div>
        <nav className="container tabs" role="tablist">
          <button role="tab" aria-selected={tab === "ask"} className={tab === "ask" ? "tab active" : "tab"} onClick={() => setTab("ask")}>
            Ask
          </button>
          <button
            role="tab"
            aria-selected={tab === "documents"}
            className={tab === "documents" ? "tab active" : "tab"}
            onClick={() => setTab("documents")}
          >
            Knowledge base
          </button>
        </nav>
      </header>

      <main className="container">
        {/* Both panels stay mounted so switching tabs keeps the last answer and form state. */}
        <div hidden={tab !== "ask"}>
          <AskPanel />
        </div>
        <div hidden={tab !== "documents"}>
          <DocumentsPanel />
        </div>
      </main>
    </>
  );
}
