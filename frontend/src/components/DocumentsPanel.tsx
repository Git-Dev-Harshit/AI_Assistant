import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError, DocumentPage } from "../api";
import { ErrorBanner } from "./ErrorBanner";

const PAGE_SIZE = 10;
const MAX_TITLE = 200;
const MAX_CONTENT = 100_000;

export function DocumentsPanel() {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<DocumentPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<unknown>(null);

  const load = useCallback(async (nextOffset: number) => {
    setLoading(true);
    setError(null);
    try {
      setPage(await api.listDocuments(PAGE_SIZE, nextOffset));
      setOffset(nextOffset);
    } catch (err) {
      setError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(0);
  }, [load]);

  async function remove(documentId: string, title: string) {
    if (!window.confirm(`Delete "${title}"? Its chunks will be removed from search.`)) return;
    try {
      await api.deleteDocument(documentId);
      const lastOnPage = page?.items.length === 1 && offset > 0;
      await load(lastOnPage ? offset - PAGE_SIZE : offset);
    } catch (err) {
      setError(err);
    }
  }

  const total = page?.total ?? 0;
  const pageNumber = Math.floor(offset / PAGE_SIZE) + 1;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <section>
      <AddDocumentForm onCreated={() => void load(0)} />

      <div className="card">
        <div className="row">
          <h2>Knowledge base ({total} {total === 1 ? "article" : "articles"})</h2>
          <button type="button" className="button-secondary" onClick={() => void load(offset)} disabled={loading}>
            Refresh
          </button>
        </div>

        {error !== null && <ErrorBanner error={error} onRetry={() => void load(offset)} />}
        {loading && !page && <div className="loading"><span className="spinner" /> Loading...</div>}
        {page && page.items.length === 0 && <p className="muted">No articles yet. Add one above to get started.</p>}

        {page && page.items.length > 0 && (
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Chunks</th>
                <th>Added</th>
                <th aria-label="Actions" />
              </tr>
            </thead>
            <tbody>
              {page.items.map((doc) => (
                <tr key={doc.document_id}>
                  <td>{doc.title}</td>
                  <td>{doc.chunk_count}</td>
                  <td>{new Date(doc.created_at).toLocaleString()}</td>
                  <td>
                    <button type="button" className="button-link" onClick={() => void remove(doc.document_id, doc.title)}>
                      Delete
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {total > PAGE_SIZE && (
          <div className="row pagination">
            <button type="button" className="button-secondary" disabled={offset === 0 || loading} onClick={() => void load(offset - PAGE_SIZE)}>
              Previous
            </button>
            <span className="muted">
              Page {pageNumber} of {pageCount}
            </span>
            <button
              type="button"
              className="button-secondary"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => void load(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        )}
      </div>
    </section>
  );
}

function AddDocumentForm({ onCreated }: { onCreated: () => void }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.createDocument(title.trim(), content.trim());
      setNotice(`Indexed "${title.trim()}" as ${created.chunk_count} chunk${created.chunk_count === 1 ? "" : "s"}.`);
      setTitle("");
      setContent("");
      onCreated();
    } catch (err) {
      setError(err);
    } finally {
      setSaving(false);
    }
  }

  const fieldErrors = error instanceof ApiError ? error.fieldErrors : [];
  const fieldError = (field: string) => fieldErrors.find((e) => e.field === field)?.message;
  const invalid = !title.trim() || !content.trim();

  return (
    <form className="card" onSubmit={onSubmit}>
      <h2>Add an article</h2>
      <label htmlFor="title" className="label">Title</label>
      <input id="title" value={title} maxLength={MAX_TITLE} onChange={(e) => setTitle(e.target.value)} disabled={saving} />
      {fieldError("title") && <div className="field-error">{fieldError("title")}</div>}

      <label htmlFor="content" className="label">Content</label>
      <textarea
        id="content"
        value={content}
        rows={8}
        maxLength={MAX_CONTENT}
        onChange={(e) => setContent(e.target.value)}
        disabled={saving}
        placeholder="Paste a policy, FAQ or troubleshooting note. Blank lines separate paragraphs."
      />
      {fieldError("content") && <div className="field-error">{fieldError("content")}</div>}

      <div className="row">
        <span className="muted small">{content.length.toLocaleString()}/{MAX_CONTENT.toLocaleString()} characters</span>
        <button type="submit" disabled={saving || invalid}>
          {saving ? "Indexing..." : "Add article"}
        </button>
      </div>
      {notice && <div className="banner banner-success">{notice}</div>}
      {error !== null && fieldErrors.length === 0 && <ErrorBanner error={error} />}
    </form>
  );
}
