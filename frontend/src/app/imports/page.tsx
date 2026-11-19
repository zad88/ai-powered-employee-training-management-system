"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { authenticatedFetch } from "../../lib/api";
import { useAuth } from "../../components/auth-provider";

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

type StagedImport = {
  batch_id: number;
  company_id: number;
  filename: string;
  status: string;
  source_type: string;
  total_rows: number;
  columns: string[];
  column_mapping: Record<string, string | null>;
  available_fields: string[];
  available_sheets: string[];
  worksheet: string | null;
};

type ImportPreview = {
  batch_id: number;
  rows: Array<{
    row_number: number;
    data: Record<string, unknown>;
    errors: Array<{ field?: string; message: string; type: string }>;
    warnings: Array<{ field?: string; message: string; type: string }>;
    importable: boolean;
  }>;
  errors: Array<{ row_number: number | null; field?: string; message: string; type: string }>;
  warnings: Array<{ row_number?: number; field?: string; message: string; type: string }>;
  missing_mappings: string[];
  summary: {
    total_rows: number;
    importable_rows: number;
    invalid_rows: number;
    total_errors: number;
    total_warnings: number;
    ready_for_confirmation: boolean;
  };
};

type ImportHistoryItem = {
  batch_id: number;
  file_name: string;
  source_type: string;
  uploaded_at: string | null;
  status: string;
  total_rows: number;
  successful_rows: number;
  failed_rows: number;
};

type ImportResult = {
  batch_id: number;
  status: string;
  summary: {
    total_rows: number;
    successful_rows: number;
    failed_rows: number;
    total_errors: number;
    total_warnings: number;
  };
};

type OdooStatus = {
  configured: boolean;
  base_url?: string;
  database?: string;
  username?: string;
  api_key_configured?: boolean;
  missing_configuration?: string;
};

type OdooCompany = {
  id: number;
  name: string;
};

type OdooTestResult = {
  success: boolean;
  server_version: string;
  server_serie: string;
  database: string;
  selected_adapter: string;
  employee_model_access: string;
  employee_count: number;
  available_employee_fields: string[];
};

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export default function Home() {
  const { activeMembership } = useAuth();
  const canManageImports = activeMembership?.role === "Training Manager";
  const canViewImportHistory =
    canManageImports || activeMembership?.role === "Director";
  const [batchId, setBatchId] = useState("");
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
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [availableSheets, setAvailableSheets] = useState<string[]>([]);
  const [selectedSheet, setSelectedSheet] = useState("");
  const [uploading, setUploading] = useState(false);
  const [stagedImport, setStagedImport] = useState<StagedImport | null>(null);
  const [columnMapping, setColumnMapping] = useState<Record<string, string | null>>({});
  const [importPreview, setImportPreview] = useState<ImportPreview | null>(null);
  const [previewingImport, setPreviewingImport] = useState(false);
  const [confirmingImport, setConfirmingImport] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [importHistory, setImportHistory] = useState<ImportHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [previewPage, setPreviewPage] = useState(0);
  const [odooStatus, setOdooStatus] = useState<OdooStatus | null>(null);
  const [odooTest, setOdooTest] = useState<OdooTestResult | null>(null);
  const [odooCompanies, setOdooCompanies] = useState<OdooCompany[]>([]);
  const [odooCompanyId, setOdooCompanyId] = useState("");
  const [includeArchived, setIncludeArchived] = useState(false);
  const [odooEmployeeIds, setOdooEmployeeIds] = useState("");
  const [odooLoading, setOdooLoading] = useState(false);

  const api = useCallback(async <T,>(
    path: string,
    options?: RequestInit
  ): Promise<T> => {
    const headers = new Headers(options?.headers);
    if (!(typeof FormData !== "undefined" && options?.body instanceof FormData)) {
      headers.set("Content-Type", "application/json");
    }
    const response = await authenticatedFetch(path, {
      ...options,
      headers,
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

  const loadImportHistory = useCallback(async () => {
    if (!canViewImportHistory) return;
    setHistoryLoading(true);
    try {
      const response = await api<{ batches: ImportHistoryItem[] }>(
        "/api/employee-imports/history"
      );
      setImportHistory(response.batches);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load import history.");
    } finally {
      setHistoryLoading(false);
    }
  }, [api, canViewImportHistory]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadImportHistory(), 0);
    return () => window.clearTimeout(timer);
  }, [loadImportHistory]);

  const loadOdooStatus = useCallback(async () => {
    if (!canManageImports) return;
    try {
      const status = await api<OdooStatus>("/api/employee-imports/odoo/status");
      setOdooStatus(status);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to read Odoo configuration.");
    }
  }, [api, canManageImports]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadOdooStatus(), 0);
    return () => window.clearTimeout(timer);
  }, [loadOdooStatus]);

  async function testOdooConnection() {
    setOdooLoading(true);
    setError("");
    setSuccess("");
    setOdooTest(null);
    try {
      const response = await api<OdooTestResult>(
        "/api/employee-imports/odoo/test-connection",
        { method: "POST", body: "{}" }
      );
      setOdooTest(response);
      setSuccess(
        `Odoo connected with ${response.selected_adapter} adapter (Odoo ${response.server_serie}).`
      );
      const companyResponse = await api<{ companies: OdooCompany[] }>(
        "/api/employee-imports/odoo/companies"
      );
      setOdooCompanies(companyResponse.companies);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Odoo connection test failed.");
    } finally {
      setOdooLoading(false);
    }
  }

  async function fetchOdooPreview() {
    setOdooLoading(true);
    setError("");
    setSuccess("");
    setImportPreview(null);
    setImportResult(null);
    const employeeIds = odooEmployeeIds
      .split(",")
      .map((value) => Number(value.trim()))
      .filter((value) => Number.isInteger(value) && value > 0);
    try {
      const preview = await api<ImportPreview & StagedImport>(
        "/api/employee-imports/odoo/fetch-preview",
        {
          method: "POST",
          body: JSON.stringify({
            include_archived: includeArchived,
            odoo_company_id: odooCompanyId ? Number(odooCompanyId) : null,
            employee_ids: employeeIds.length > 0 ? employeeIds : null,
            column_mapping: null,
          }),
        }
      );
      setStagedImport({
        batch_id: preview.batch_id,
        company_id: preview.company_id,
        filename: preview.filename,
        status: preview.status,
        source_type: preview.source_type,
        total_rows: preview.summary.total_rows,
        columns: preview.columns,
        column_mapping: preview.column_mapping,
        available_fields: preview.available_fields,
        available_sheets: preview.available_sheets,
        worksheet: preview.worksheet,
      });
      setColumnMapping(preview.column_mapping);
      setBatchId(String(preview.batch_id));
      setImportPreview(preview);
      setSuccess(
        `Fetched ${preview.total_rows} Odoo employee records. Preview does not create employees.`
      );
      await loadImportHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not fetch Odoo employees.");
    } finally {
      setOdooLoading(false);
    }
  }

  async function stageImport() {
    if (!selectedFile) {
      setError("Choose a CSV, Excel, or JSON file first.");
      return;
    }

    setUploading(true);
    setError("");
    setSuccess("");
    setImportPreview(null);
    setImportResult(null);

    const form = new FormData();
    form.append("file", selectedFile);
    if (selectedSheet) form.append("sheet_name", selectedSheet);

    try {
      const response = await authenticatedFetch(
        "/api/employee-imports/upload",
        { method: "POST", body: form }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        const detail = data.detail;
        if (
          typeof detail === "object" &&
          detail !== null &&
          "code" in detail &&
          detail.code === "worksheet_selection_required" &&
          "available_sheets" in detail &&
          Array.isArray(detail.available_sheets)
        ) {
          setAvailableSheets(detail.available_sheets.filter(
            (sheet: unknown): sheet is string => typeof sheet === "string"
          ));
          setError("Select the worksheet that contains the employee records.");
          return;
        }
        throw new Error(
          typeof detail === "string"
            ? detail
            : detail
              ? JSON.stringify(detail)
              : `Upload failed (${response.status})`
        );
      }

      const staged = data as StagedImport;
      setStagedImport(staged);
      setColumnMapping(staged.column_mapping);
      setBatchId(String(staged.batch_id));
      setAvailableSheets(staged.available_sheets);
      setSelectedSheet(staged.worksheet ?? "");
      setSuccess(`Uploaded ${staged.filename}. Review the mapping and preview before importing.`);
      await loadImportHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to upload the file.");
    } finally {
      setUploading(false);
    }
  }

  async function previewStagedImport() {
    if (!stagedImport) return;
    setPreviewingImport(true);
    setError("");
    setSuccess("");
    setImportResult(null);
    setPreviewPage(0);
    try {
      const preview = await api<ImportPreview>(
        `/api/employee-imports/${stagedImport.batch_id}/preview`,
        {
          method: "POST",
          body: JSON.stringify({ column_mapping: columnMapping }),
        }
      );
      setImportPreview(preview);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to preview this import.");
    } finally {
      setPreviewingImport(false);
    }
  }

  async function confirmStagedImport() {
    if (!stagedImport || !importPreview?.summary.ready_for_confirmation) return;
    if (!window.confirm(
      `Import ${importPreview.summary.importable_rows} valid employee records? ${importPreview.summary.invalid_rows} invalid records will remain unimported and be recorded for review.`
    )) return;

    setConfirmingImport(true);
    setError("");
    setSuccess("");
    try {
      const response = await api<ImportResult>(
        `/api/employee-imports/${stagedImport.batch_id}/confirm`,
        {
          method: "POST",
          body: JSON.stringify({ confirmed: true }),
        }
      );
      setImportResult(response);
      setSuccess(`Import finished with status: ${response.status}.`);
      await loadImportHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to confirm this import.");
    } finally {
      setConfirmingImport(false);
    }
  }

  const loadData = useCallback(async () => {
    if (!batchId) {
      setLoading(false);
      setError("");
      return;
    }
    const batch = Number(batchId);

    if (!Number.isInteger(batch) || batch <= 0) {
      setError("Enter a valid import batch ID.");
      return;
    }

    setLoading(true);
    setError("");
    setSuccess("");
    setResult(null);

    try {
      const [previewData, issuesData] = await Promise.all([
        api<PreviewResponse>(
          `/api/employee-imports/${batch}/preview-corrections`
        ),
        api<IssuesResponse>(
          `/api/employee-imports/${batch}/issues?status=Open`
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
  }, [api, batchId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
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
        `/api/employee-imports/${batchId}/issues/${item.issue_id}`,
        {
          method: "PATCH",
          body: JSON.stringify({
            corrected_value: value,
            resolution_note:
              notes[item.issue_id]?.trim() ||
              "Manually reviewed by the authenticated user.",
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
        `/api/employee-imports/${batchId}/reprocess`,
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

          {!canManageImports && (
            <div className="alert">
              Import corrections and reprocessing are available to Training Managers.
            </div>
          )}

          {error && <div className="alert error">{error}</div>}
          {success && <div className="alert success">{success}</div>}

          <section className="review-section">
            <div className="section-heading">
              <div>
                <h2>Upload employee records</h2>
                <p>Stage CSV, Excel (.xlsx/.xls), or a JSON array of flat employee objects. Records are not saved until you confirm.</p>
              </div>
              {canViewImportHistory && (
                <button
                  className="button secondary"
                  onClick={() => void loadImportHistory()}
                  disabled={historyLoading}
                >
                  {historyLoading ? "Refreshing..." : "Refresh history"}
                </button>
              )}
            </div>

            {canManageImports && (
              <section className="review-section">
                <div className="section-heading">
                  <div>
                    <h2>Import from Odoo</h2>
                    <p>Uses the server-side Odoo environment configuration. API keys are never displayed or stored here.</p>
                  </div>
                  <button
                    className="button secondary"
                    onClick={() => void testOdooConnection()}
                    disabled={odooLoading}
                  >
                    {odooLoading ? "Testing..." : "Test Odoo connection"}
                  </button>
                </div>

                {odooStatus && (
                  <div className={odooStatus.configured ? "notice" : "alert error"}>
                    {odooStatus.configured ? (
                      <>
                        <strong>Configured database:</strong>{" "}
                        {odooStatus.database} at {odooStatus.base_url}
                      </>
                    ) : (
                      odooStatus.missing_configuration
                    )}
                  </div>
                )}

                {odooTest && (
                  <div className="notice">
                    <strong>
                      Odoo {odooTest.server_serie} · {odooTest.selected_adapter}
                    </strong>
                    <p>
                      Employee model access: {odooTest.employee_model_access} ·
                      {" "}{odooTest.employee_count} matching records available.
                    </p>
                  </div>
                )}

                <div className="selection-panel">
                  <div className="field">
                    <label htmlFor="odoo-company">Odoo company</label>
                    <select
                      id="odoo-company"
                      value={odooCompanyId}
                      onChange={(event) => setOdooCompanyId(event.target.value)}
                    >
                      <option value="">All visible companies</option>
                      {odooCompanies.map((company) => (
                        <option key={company.id} value={String(company.id)}>
                          {company.name} (ID {company.id})
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="field">
                    <label htmlFor="odoo-employee-ids">Employee record IDs (optional)</label>
                    <input
                      id="odoo-employee-ids"
                      value={odooEmployeeIds}
                      onChange={(event) => setOdooEmployeeIds(event.target.value)}
                      placeholder="Examples: 12, 15, 21"
                    />
                  </div>
                  <label className="field">
                    <span>Archived employees</span>
                    <select
                      value={includeArchived ? "include" : "active"}
                      onChange={(event) =>
                        setIncludeArchived(event.target.value === "include")
                      }
                    >
                      <option value="active">Active employees only</option>
                      <option value="include">Include archived employees</option>
                    </select>
                  </label>
                  <button
                    className="button primary"
                    onClick={() => void fetchOdooPreview()}
                    disabled={odooLoading}
                  >
                    {odooLoading ? "Fetching..." : "Fetch employees and preview"}
                  </button>
                </div>
              </section>
            )}

            {canManageImports ? (
              <>
                <div className="selection-panel">
                  <div className="field">
                    <label htmlFor="employee-import-file">Employee data file</label>
                    <input
                      id="employee-import-file"
                      type="file"
                      accept=".csv,.xlsx,.xls,.json"
                      onChange={(event) => {
                        setSelectedFile(event.target.files?.[0] ?? null);
                        setAvailableSheets([]);
                        setSelectedSheet("");
                        setStagedImport(null);
                        setImportPreview(null);
                        setImportResult(null);
                        setError("");
                      }}
                    />
                  </div>
                  <button
                    className="button primary"
                    onClick={() => void stageImport()}
                    disabled={uploading || !selectedFile}
                  >
                    {uploading ? "Uploading..." : "Upload and inspect"}
                  </button>
                </div>

                {availableSheets.length > 0 && (
                  <div className="selection-panel">
                    <div className="field">
                      <label htmlFor="employee-import-sheet">Worksheet</label>
                      <select
                        id="employee-import-sheet"
                        value={selectedSheet}
                        onChange={(event) => setSelectedSheet(event.target.value)}
                      >
                        <option value="">Select a worksheet</option>
                        {availableSheets.map((sheet) => (
                          <option key={sheet} value={sheet}>{sheet}</option>
                        ))}
                      </select>
                    </div>
                  </div>
                )}

                {stagedImport && (
                  <div className="notice">
                    <div className="notice-icon">i</div>
                    <div>
                      <strong>{stagedImport.filename} · {stagedImport.source_type.toUpperCase()}</strong>
                      <p>
                        {stagedImport.total_rows} rows staged
                        {stagedImport.worksheet ? ` from worksheet “${stagedImport.worksheet}”` : ""}.
                        Nothing has been written to employee records yet.
                      </p>
                    </div>
                  </div>
                )}

                {stagedImport && (
                  <section className="review-section">
                    <div className="section-heading">
                      <div>
                        <h2>Map source fields</h2>
                        <p>Unmapped columns are ignored. Company ownership always comes from your active membership.</p>
                      </div>
                    </div>
                    <div className="filter-bar">
                      {stagedImport.columns.map((column) => (
                        <label className="field" key={column}>
                          <span>{column}</span>
                          <select
                            value={columnMapping[column] ?? ""}
                            onChange={(event) => setColumnMapping((current) => ({
                              ...current,
                              [column]: event.target.value || null,
                            }))}
                          >
                            <option value="">Do not import</option>
                            {stagedImport.available_fields.map((field) => (
                              <option key={field} value={field}>{field.replaceAll("_", " ")}</option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                    <button
                      className="button primary"
                      onClick={() => void previewStagedImport()}
                      disabled={previewingImport}
                    >
                      {previewingImport ? "Validating..." : "Validate and preview"}
                    </button>
                  </section>
                )}

                {importPreview && (
                  <section className="review-section">
                    <div className="section-heading">
                      <div>
                        <h2>Validation preview</h2>
                        <p>Only valid rows will be imported; invalid rows and warnings are retained in the batch history.</p>
                      </div>
                      <span className="count-pill">
                        {importPreview.summary.importable_rows} valid · {importPreview.summary.invalid_rows} invalid
                      </span>
                    </div>

                    <section className="stats-grid">
                      <div className="stat-card"><span>Total rows</span><strong>{importPreview.summary.total_rows}</strong></div>
                      <div className="stat-card"><span>Importable</span><strong>{importPreview.summary.importable_rows}</strong></div>
                      <div className="stat-card"><span>Invalid</span><strong>{importPreview.summary.invalid_rows}</strong></div>
                      <div className="stat-card"><span>Warnings</span><strong>{importPreview.summary.total_warnings}</strong></div>
                    </section>

                    {importPreview.missing_mappings.length > 0 && (
                      <div className="alert error">
                        Required fields not mapped: {importPreview.missing_mappings.join(", ")}.
                      </div>
                    )}
                    {importPreview.errors.filter((item) => item.row_number === null).map((item, index) => (
                      <div className="alert error" key={`${item.type}-${index}`}>{item.message}</div>
                    ))}

                    <div className="issue-list">
                      {importPreview.rows
                        .slice(previewPage * 15, (previewPage + 1) * 15)
                        .map((row) => (
                          <article className="issue-card" key={row.row_number}>
                            <div className="issue-header">
                              <div className="issue-title">
                                <span className={row.importable ? "issue-symbol" : "issue-symbol duplicate"}>
                                  {row.importable ? "✓" : "!"}
                                </span>
                                <div>
                                  <strong>Source row {row.row_number}</strong>
                                  <span>{String(row.data.full_name ?? row.data.employee_id ?? "Employee record")}</span>
                                </div>
                              </div>
                              <span className={row.importable ? "review-status saved" : "review-status"}>
                                {row.importable ? "Ready to import" : "Needs correction"}
                              </span>
                            </div>
                            <p>
                              {Object.entries(row.data)
                                .map(([field, value]) => (
                                  `${field.replaceAll("_", " ")}: ${String(value ?? "—")}`
                                ))
                                .join(" · ")}
                            </p>
                            {(row.errors.length > 0 || row.warnings.length > 0) && (
                              <ul>
                                {row.errors.map((item, index) => (
                                  <li key={`error-${index}`}>Error · {item.field ?? "record"}: {item.message}</li>
                                ))}
                                {row.warnings.map((item, index) => (
                                  <li key={`warning-${index}`}>Warning · {item.field ?? "record"}: {item.message}</li>
                                ))}
                              </ul>
                            )}
                          </article>
                        ))}
                    </div>

                    <div className="filter-bar">
                      <button
                        className="button secondary"
                        onClick={() => setPreviewPage((page) => Math.max(0, page - 1))}
                        disabled={previewPage === 0}
                      >
                        Previous
                      </button>
                      <span>
                        Page {previewPage + 1} of {Math.max(1, Math.ceil(importPreview.rows.length / 15))}
                      </span>
                      <button
                        className="button secondary"
                        onClick={() => setPreviewPage((page) => Math.min(
                          Math.ceil(importPreview.rows.length / 15) - 1,
                          page + 1
                        ))}
                        disabled={(previewPage + 1) * 15 >= importPreview.rows.length}
                      >
                        Next
                      </button>
                      <button
                        className="button primary"
                        onClick={() => void confirmStagedImport()}
                        disabled={
                          confirmingImport ||
                          !importPreview.summary.ready_for_confirmation ||
                          importPreview.summary.importable_rows === 0
                        }
                      >
                        {confirmingImport ? "Importing..." : "Confirm and import valid rows"}
                      </button>
                    </div>
                  </section>
                )}

                {importResult && (
                  <section className="result-panel">
                    <h2>Import results · {importResult.status}</h2>
                    <div className="result-grid">
                      <div><strong>{importResult.summary.total_rows}</strong><span>Total rows</span></div>
                      <div><strong>{importResult.summary.successful_rows}</strong><span>Imported</span></div>
                      <div><strong>{importResult.summary.failed_rows}</strong><span>Failed</span></div>
                      <div><strong>{importResult.summary.total_errors}</strong><span>Errors</span></div>
                    </div>
                  </section>
                )}
              </>
            ) : (
              <div className="alert">
                Only Training Managers can upload or confirm employee imports.
              </div>
            )}

            {canViewImportHistory && (
              <section className="review-section">
                <div className="section-heading">
                  <div>
                    <h2>Recent import history</h2>
                    <p>Company-scoped import batches and their recorded outcomes.</p>
                  </div>
                </div>
                {historyLoading && <div className="empty-state">Loading import history...</div>}
                {!historyLoading && importHistory.length === 0 && (
                  <div className="empty-state">No employee import batches yet.</div>
                )}
                {!historyLoading && importHistory.map((item) => (
                  <article className="issue-card" key={item.batch_id}>
                    <div className="issue-header">
                      <div className="issue-title">
                        <span className="issue-symbol">▤</span>
                        <div>
                          <strong>{item.file_name ?? `Batch ${item.batch_id}`}</strong>
                          <span>Batch #{item.batch_id} · {item.source_type.toUpperCase()} · {item.uploaded_at ?? "Time unavailable"}</span>
                        </div>
                      </div>
                      <span className="review-status">{item.status}</span>
                    </div>
                    <p>{item.total_rows} rows · {item.successful_rows} imported · {item.failed_rows} failed</p>
                  </article>
                ))}
              </section>
            )}
          </section>

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
                      {canManageImports && <button
                        className="button small primary"
                        disabled={savingId === item.issue_id || !value.trim()}
                        onClick={() => void saveCorrection(item)}
                      >
                        {savingId === item.issue_id ? "Saving..." : "Save correction"}
                      </button>}
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
            {canManageImports && <button
              className="button primary reprocess-button"
              onClick={() => void reprocessBatch()}
              disabled={reprocessing || loading || issues.length === 0}
            >
              {reprocessing ? "Reprocessing..." : "↻ Reprocess batch"}
            </button>}
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
