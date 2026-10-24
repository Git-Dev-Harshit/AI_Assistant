import { FormEvent, useRef, useState } from "react";
import { api, AskResponse } from "../api";
import { ErrorBanner } from "./ErrorBanner";

const MAX_QUESTION = 1000;

type State =
  | { status: "idle" }
  | { status: "loading"; question: string }
  | { status: "success"; question: string; result: AskResponse }
  | { status: "error"; question: string; error: unknown };

export function AskPanel() {
  const [question, setQuestion] = useState("");
  const [state, setState] = useState<State>({ status: "idle" });
  const latestRequest = useRef(0);

  async function ask(text: string) {
    const trimmed = text.trim();
    if (trimmed.length < 3) return;
    const requestId = ++latestRequest.current;
    setState({ status: "loading", question: trimmed });
    try {
      const result = await api.ask(trimmed);
      if (requestId === latestRequest.current) setState({ status: "success", question: trimmed, result });
    } catch (error) {
      if (requestId === latestRequest.current) setState({ status: "error", question: trimmed, error });
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void ask(question);
  }

  const loading = state.status === "loading";
  const tooShort = question.trim().length < 3;

  return (
    <section>
      <form className="card" onSubmit={onSubmit}>
        <label htmlFor="question" className="label">
          Ask a question about the knowledge base
        </label>
        <textarea
          id="question"
          value={question}
          maxLength={MAX_QUESTION}
          rows={3}
          placeholder="e.g. How long do I have to request a refund?"
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              if (!loading && !tooShort) void ask(question);
            }
          }}
          disabled={loading}
        />
        <div className="row">
          <span className="muted small">
            {question.length}/{MAX_QUESTION} · Enter to ask, Shift+Enter for a new line
          </span>
          <button type="submit" disabled={loading || tooShort}>
            {loading ? "Asking..." : "Ask"}
          </button>
        </div>
      </form>

      {state.status === "loading" && (
        <div className="card loading" aria-live="polite">
          <span className="spinner" aria-hidden="true" /> Searching the knowledge base and generating an answer...
        </div>
      )}

      {state.status === "error" && <ErrorBanner error={state.error} onRetry={() => void ask(state.question)} />}

      {state.status === "success" && <Answer question={state.question} result={state.result} />}
    </section>
  );
}

function Answer({ question, result }: { question: string; result: AskResponse }) {
  return (
    <article className="card" aria-live="polite">
      <div className="muted small">Q: {question}</div>
      {result.mode === "demo" && (
        <div className="banner banner-warning">Demo mode: no language model is configured, showing retrieved passages.</div>
      )}
      {!result.grounded && (
        <div className="banner banner-info">No answer was found in the knowledge base. Try rephrasing or add an article.</div>
      )}
      <p className="answer">{result.answer}</p>

      {result.sources.length > 0 && (
        <>
          <h3>Sources</h3>
          <ol className="sources">
            {result.sources.map((source, index) => (
              <li key={source.chunk_id} className={source.cited ? "cited" : undefined}>
                <div className="source-title">
                  [{index + 1}] {source.title}
                  {source.cited && <span className="badge">cited</span>}
                  <span className="muted small"> relevance {(source.score * 100).toFixed(0)}%</span>
                </div>
                <div className="muted small snippet">{source.snippet}</div>
              </li>
            ))}
          </ol>
        </>
      )}
      <div className="muted small">
        {result.model ?? "no model"} · {(result.latency_ms / 1000).toFixed(1)}s
      </div>
    </article>
  );
}
