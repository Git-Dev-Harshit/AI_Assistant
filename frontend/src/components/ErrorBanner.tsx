import { useEffect, useState } from "react";
import { ApiError } from "../api";

type Props = { error: unknown; onRetry?: () => void };

const FRIENDLY: Record<string, string> = {
  RATE_LIMITED: "You're asking questions faster than the limit allows.",
  LLM_MODEL_NOT_READY: "The language model is still loading. This can take a few minutes on first start.",
  LLM_TIMEOUT: "The answer took too long to generate. Try a shorter question or retry.",
  LLM_BUSY: "The assistant is busy answering other questions.",
  NETWORK_ERROR: "Could not reach the server. Check that the backend is running.",
};

export function ErrorBanner({ error, onRetry }: Props) {
  const apiError = error instanceof ApiError ? error : null;
  const retryAfter = apiError?.retryAfterSeconds ?? null;
  const secondsLeft = useCountdown(retryAfter);

  const message = (apiError && FRIENDLY[apiError.code]) ?? apiError?.message ?? "Something went wrong.";
  const canRetry = onRetry && (secondsLeft === null || secondsLeft === 0);

  return (
    <div className="banner banner-error" role="alert">
      <div>
        <strong>{message}</strong>
        {apiError && apiError.message !== message && <div className="muted">{apiError.message}</div>}
        {secondsLeft !== null && secondsLeft > 0 && <div>You can retry in {secondsLeft}s.</div>}
        {apiError?.requestId && <div className="muted small">Reference: {apiError.requestId}</div>}
      </div>
      {onRetry && (
        <button type="button" className="button-secondary" onClick={onRetry} disabled={!canRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

function useCountdown(seconds: number | null): number | null {
  const [left, setLeft] = useState(seconds);

  useEffect(() => {
    setLeft(seconds);
    if (seconds === null) return;
    const timer = setInterval(() => setLeft((s) => (s && s > 0 ? s - 1 : 0)), 1000);
    return () => clearInterval(timer);
  }, [seconds]);

  return left;
}
