"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

type PreviewItem = {
  issue_id: number;
  row_number: number;
  original_value: string | null;
  proposed_value: string | null;
  action: string;
  confidence: number;
  method: string;
  reason: string;
  existing_human_correction?: unknown;
};

type Issue = {
  id: number;
  row_number: number;
  field_name: string;
  issue_type: string;
  message: string;
  raw_value: string | null;
  corrected_value: string | null;
  status: string;
  resolution_note: string | null;
};

type PreviewResponse = {
  batch_id: number;
  company_id: number;
  mode: string;
  source_modified: boolean;
  database_modified: boolean;
  total_open_email_issues: number;
  automatic_corrections: number;
  human_review_required: number;
  items: PreviewItem[];
};

type IssuesResponse = {
  batch_id: number;
  company_id: number;
  batch_status: string;
  total_issues: number;
  issues: Issue[];
};

type ReprocessResponse = {
  message: string;
  batch_id: number;
  company_id?: number;
  status?: string;
  summary?: {
    affected_rows: number;
    newly_imported_rows: number;
    total_imported_rows: number;
    remaining_failed_rows: number;
    remaining_open_issues: number;
    resolved_issues: number;
  };
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Home() {
  const [companyId, setCompanyId] = useState("14");
  const [batchId, setBatchId] = useState("3");
  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [edits, setEdits] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [filter, setFilter] = useState("all");
  const [loading, setLoading] = useState(false);
  const [savingId, setSavingId] = useState<number | null>(null);
  const [reprocessing, setReprocessing] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [result, setResult] = useState<ReprocessResponse | null>(null);

  const api = useCallback(async <T,>(
    path: string,
    options?: RequestInit
  ): Promise<T> => {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    });

    const data = await response.json().catch(() => ({}));

    if (!response.ok) {
      throw new Error(
        data.detail
          ? typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail)
          : `Request failed (${response.status})`
      );
    }

    return data as T;
  }, []);

  const loadData = useCallback(async () => {
    const company = Number(companyId);
    const batch = Number(batchId);

    if (!Number.isInteger(company) || company <= 0 ||
        !Number.isInteger(batch) || batch <= 0) {
      setError("Enter valid company and batch IDs.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setResult(null);

    try {
      const query = `company_id=${company}`;
      const [previewData, issuesData] = await Promise.all([
        api<PreviewResponse>(
          `/api/employee-imports/${batch}/preview-corrections?${query}`
        ),
        api<IssuesResponse>(
          `/api/employee-imports/${batch}/issues?${query}&status=Open`
        ),
      ]);

      setPreview(previewData);
      setIssues(issuesData.issues);

      const nextEdits: Record<number, string> = {};
      const nextNotes: Record<number, string> = {};

      for (const item of previewData.items) {
        const issue = issuesData.issues.find(
          (entry) => entry.id === item.issue_id
        );

        nextEdits[item.issue_id] =
          issue?.corrected_value ?? item.proposed_value ?? "";

        nextNotes[item.issue_id] = issue?.resolution_note ?? "";
      }

      setEdits(nextEdits);
      setNotes(nextNotes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load data.");
    } finally {
      setLoading(false);
    }
  }, [api, batchId, companyId]);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const issueMap = useMemo(
    () => new Map(issues.map((issue) => [issue.id, issue])),
    [issues]
  );

  const filteredItems = useMemo(() => {
    if (!preview) return [];

    if (filter === "duplicates") {
      return preview.items.filter((item) => item.method === "duplicate_email");
    }

    if (filter === "suggestions") {
      return preview.items.filter(
        (item) => item.method === "internal_whitespace_suggestion"
      );
    }

    return preview.items;
  }, [preview, filter]);

  async function saveCorrection(item: PreviewItem) {
    const value = (edits[item.issue_id] ?? "").trim();

    if (!value || !EMAIL_PATTERN.test(value)) {
      setError(`Enter a valid email address for row ${item.row_number}.`);
      return;
    }

    setSavingId(item.issue_id);
    setError("");
    setSuccess("");

    try {
      await api(
        `/api/employee-imports/${batchId}/issues/${item.issue_id}?company_id=${companyId}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            corrected_value: value,
            resolution_note:
              notes[item.issue_id]?.trim() ||
              "Manually reviewed and approved by Training Manager.",
          }),
        }
      );

      setSuccess(`Correction saved for row ${item.row_number}.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save correction.");
    } finally {
      setSavingId(null);
    }
  }

  async function reprocessBatch() {
    if (!preview || issues.length === 0) {
      setError("There are no open issues to reprocess.");
      return;
    }

    const unsaved = preview.items.filter((item) => {
      const issue = issueMap.get(item.issue_id);
      return !issue?.corrected_value;
    });

    if (unsaved.length > 0) {
      setError(
        `${unsaved.length} issues still need a verified correction. Save their corrections before reprocessing.`
      );
      return;
    }

    const confirmed = window.confirm(
      "Reprocess the affected rows using the saved corrections? This will update the database."
    );

    if (!confirmed) return;

    setReprocessing(true);
    setError("");
    setSuccess("");
    setResult(null);

    try {
      const response = await api<ReprocessResponse>(
        `/api/employee-imports/${batchId}/reprocess?company_id=${companyId}`,
        { method: "POST" }
      );

      setResult(response);
      setSuccess(response.message);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reprocessing failed.");
    } finally {
      setReprocessing(false);
    }
  }

  const duplicates =
    preview?.items.filter((item) => item.method === "duplicate_email").length ?? 0;

  const suggestions =
    preview?.items.filter(
      (item) => item.method === "internal_whitespace_suggestion"
    ).length ?? 0;

  const savedCount = preview?.items.filter(
    (item) => issueMap.get(item.issue_id)?.corrected_value
  ).length ?? 0;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-icon">T</div>
          <div>
            <strong>TalentFlow</strong>
            <span>Training Management</span>
          </div>
        </div>

        <div className="nav-label">WORKSPACE</div>
        <div className="nav-item">◫ <span>Overview</span></div>
        <div className="nav-item active">▤ <span>Employee Imports</span></div>
        <div className="nav-item">♙ <span>Employees</span></div>
        <div className="nav-item">◇ <span>Skills</span></div>
        <div className="nav-item">▣ <span>Courses</span></div>
        <div className="nav-item">▥ <span>Training Plans</span></div>
        <div className="nav-item">▧ <span>Reports</span></div>

        <div className="sidebar-bottom">
          <div className="user-avatar">TM</div>
          <div>
            <strong>Training Manager</strong>
            <span>Administrator</span>
          </div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace / Employee Imports / Corrections</div>
          <div className="topbar-right">
            <span className="system-status"><i /> System connected</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">DATA MANAGEMENT</div>
              <h1>Email correction review</h1>
              <p>Review, verify and resolve employee import issues.</p>
            </div>
            <button className="button secondary" onClick={() => void loadData()} disabled={loading}>
              ↻ Refresh data
            </button>
          </div>

          <section className="selection-panel">
            <div className="field">
              <label>Company ID</label>
              <input
                type="number"
                min="1"
                value={companyId}
                onChange={(e) => setCompanyId(e.target.value)}
              />
            </div>
            <div className="field">
              <label>Import batch ID</label>
              <input
                type="number"
                min="1"
                value={batchId}
                onChange={(e) => setBatchId(e.target.value)}
              />
            </div>
            <button className="button primary" onClick={() => void loadData()} disabled={loading}>
              {loading ? "Loading..." : "Load batch"}
            </button>
            <div className="batch-label">
              <span className="status-dot" />
              {preview?.mode ?? "Awaiting batch"}
            </div>
          </section>

          {error && <div className="alert error">{error}</div>}
          {success && <div className="alert success">{success}</div>}

          <section className="stats-grid">
            <div className="stat-card">
              <div className="stat-top"><span>Total open issues</span><span className="stat-icon">!</span></div>
              <strong>{preview?.total_open_email_issues ?? "—"}</strong>
              <small>Awaiting review</small>
            </div>
            <div className="stat-card">
              <div className="stat-top"><span>Email suggestions</span><span className="stat-icon purple">✧</span></div>
              <strong>{suggestions}</strong>
              <small>Internal whitespace detected</small>
            </div>
            <div className="stat-card">
              <div className="stat-top"><span>Duplicate emails</span><span className="stat-icon orange">↔</span></div>
              <strong>{duplicates}</strong>
              <small>Require manual verification</small>
            </div>
            <div className="stat-card">
              <div className="stat-top"><span>Corrections saved</span><span className="stat-icon green">✓</span></div>
              <strong>{savedCount}</strong>
              <small>Ready for reprocessing</small>
            </div>
          </section>

          <section className="notice">
            <div className="notice-icon">i</div>
            <div>
              <strong>Human verification required</strong>
              <p>Suggested addresses are not automatically approved. Confirm each employee email before saving a correction.</p>
            </div>
          </section>

          <section className="review-section">
            <div className="section-heading">
              <div>
                <h2>Issues requiring review</h2>
                <p>Inspect each original value and save a verified correction.</p>
              </div>
              <span className="count-pill">{filteredItems.length} issues</span>
            </div>

            <div className="filter-bar">
              <button className={filter === "all" ? "filter active-filter" : "filter"} onClick={() => setFilter("all")}>All issues</button>
              <button className={filter === "suggestions" ? "filter active-filter" : "filter"} onClick={() => setFilter("suggestions")}>Email suggestions</button>
              <button className={filter === "duplicates" ? "filter active-filter" : "filter"} onClick={() => setFilter("duplicates")}>Duplicates</button>
            </div>

            {loading && <div className="empty-state">Loading import issues...</div>}

            {!loading && filteredItems.length === 0 && (
              <div className="empty-state">
                {preview ? "No issues in this category." : "Load a batch to see its issues."}
              </div>
            )}

            <div className="issue-list">
              {filteredItems.map((item) => {
                const issue = issueMap.get(item.issue_id);
                const isDuplicate = item.method === "duplicate_email";
                const value = edits[item.issue_id] ?? "";

                return (
                  <article className="issue-card" key={item.issue_id}>
                    <div className="issue-header">
                      <div className="issue-title">
                        <span className={isDuplicate ? "issue-symbol duplicate" : "issue-symbol"}>{isDuplicate ? "↔" : "@"}</span>
                        <div>
                          <strong>{isDuplicate ? "Duplicate email address" : "Invalid email format"}</strong>
                          <span>Issue #{item.issue_id} · Source row {item.row_number}</span>
                        </div>
                      </div>
                      <span className={issue?.corrected_value ? "review-status saved" : "review-status"}>
                        {issue?.corrected_value ? "Correction saved" : "Needs review"}
                      </span>
                    </div>

                    <div className="email-comparison">
                      <div className="email-box">
                        <label>Original email</label>
                        <div className="original-value">{item.original_value ?? "Missing value"}</div>
                      </div>
                      <div className="arrow">→</div>
                      <div className="email-box">
                        <label>Suggested email</label>
                        <div className="suggested-value">{item.proposed_value ?? "No automatic suggestion"}</div>
                      </div>
                    </div>

                    <div className="correction-fields">
                      <div className="field correction-input">
                        <label>Verified email address</label>
                        <input
                          type="email"
                          value={value}
                          placeholder="Enter the verified employee email"
                          onChange={(e) => setEdits((old) => ({ ...old, [item.issue_id]: e.target.value }))}
                        />
                      </div>
                      <div className="field note-input">
                        <label>Review note (optional)</label>
                        <input
                          type="text"
                          value={notes[item.issue_id] ?? ""}
                          placeholder="Reason for this correction"
                          onChange={(e) => setNotes((old) => ({ ...old, [item.issue_id]: e.target.value }))}
                        />
                      </div>
                    </div>

                    <div className="issue-footer">
                      <span className="issue-reason">{item.reason}</span>
                      <button
                        className="button small primary"
                        disabled={savingId === item.issue_id || !value.trim()}
                        onClick={() => void saveCorrection(item)}
                      >
                        {savingId === item.issue_id ? "Saving..." : "Save correction"}
                      </button>
                    </div>
                  </article>
                );
              })}
            </div>
          </section>

          <section className="reprocess-panel">
            <div>
              <div className="eyebrow">FINAL STEP</div>
              <h2>Reprocess corrected rows</h2>
              <p>Only affected rows are revalidated. Existing imported employees and the original CSV remain untouched.</p>
            </div>
            <button
              className="button primary reprocess-button"
              onClick={() => void reprocessBatch()}
              disabled={reprocessing || loading || issues.length === 0}
            >
              {reprocessing ? "Reprocessing..." : "↻ Reprocess batch"}
            </button>
          </section>

          {result?.summary && (
            <section className="result-panel">
              <h2>Reprocessing results</h2>
              <div className="result-grid">
                <div><strong>{result.summary.affected_rows}</strong><span>Affected rows</span></div>
                <div><strong>{result.summary.newly_imported_rows}</strong><span>Newly imported</span></div>
                <div><strong>{result.summary.resolved_issues}</strong><span>Resolved issues</span></div>
                <div><strong>{result.summary.remaining_open_issues}</strong><span>Remaining issues</span></div>
              </div>
            </section>
          )}

          <footer className="page-footer">
            Employee Training Management System <span>·</span> Data correction module
          </footer>
        </div>
      </section>
    </main>
  );
}
