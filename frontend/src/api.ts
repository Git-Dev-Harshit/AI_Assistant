// Typed client for the Knowledge Assistant API. All requests go through the Vite proxy
// (`/api/*` -> backend), so the browser never needs the backend's address.

export type Source = {
  document_id: string;
  title: string;
  chunk_id: string;
  chunk_index: number;
  snippet: string;
  score: number;
  cited: boolean;
};

export type AskResponse = {
  question_id: string;
  answer: string;
  sources: Source[];
  grounded: boolean;
  mode: "llm" | "demo" | "no_context";
  model: string | null;
  latency_ms: number;
};

export type DocumentSummary = {
  document_id: string;
  title: string;
  status: string;
  chunk_count: number;
  created_at: string;
};

export type DocumentPage = {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
};

export type DocumentCreated = {
  document_id: string;
  status: string;
  chunk_count: number;
  created_at: string;
};

type ErrorDetail = { field: string; message: string };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly requestId: string | null = null,
    readonly retryAfterSeconds: number | null = null,
    readonly details: unknown = null,
  ) {
    super(message);
  }

  get fieldErrors(): ErrorDetail[] {
    return Array.isArray(this.details) ? (this.details as ErrorDetail[]) : [];
  }
}

const API_BASE = "/api";
const CLIENT_ID_KEY = "knowledge-assistant.client-id";

// One opaque id per browser, used by the backend for per-client rate limiting.
function clientId(): string {
  try {
    let id = localStorage.getItem(CLIENT_ID_KEY);
    if (!id) {
      id = crypto.randomUUID().replace(/-/g, "");
      localStorage.setItem(CLIENT_ID_KEY, id);
    }
    return id;
  } catch {
    return "anonymous-browser";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", "X-Client-Id": clientId(), ...init.headers },
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Could not reach the server. Is the backend running?");
  }

  if (response.status === 204) return undefined as T;

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const error = body?.error;
    const retryAfter = Number(response.headers.get("Retry-After"));
    throw new ApiError(
      response.status,
      error?.code ?? "HTTP_ERROR",
      error?.message ?? `Request failed with status ${response.status}.`,
      error?.request_id ?? response.headers.get("X-Request-ID"),
      Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null,
      error?.details ?? null,
    );
  }
  return body as T;
}

export const api = {
  ask: (question: string) => request<AskResponse>("/ask", { method: "POST", body: JSON.stringify({ question }) }),

  listDocuments: (limit: number, offset: number) =>
    request<DocumentPage>(`/documents?limit=${limit}&offset=${offset}`),

  createDocument: (title: string, content: string) =>
    request<DocumentCreated>("/documents", { method: "POST", body: JSON.stringify({ title, content }) }),

  deleteDocument: (documentId: string) => request<void>(`/documents/${documentId}`, { method: "DELETE" }),
};
