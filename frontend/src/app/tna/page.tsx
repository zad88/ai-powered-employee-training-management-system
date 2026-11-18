"use client";

import { useCallback, useEffect, useState } from "react";

const COMPANY_ID = 14;

type TNAData = {
  company_id: number;
  analysis_date: string;
  summary: {
    active_employees: number;
    positions_analysed: number;
    confirmed_skill_gaps: number;
    assessments_needed: number;
  };
  position_analysis: any[];
  department_analysis: any[];
};

type AIInsights = {
  overall_summary: string;
  key_findings: { finding: string; evidence: string }[];
  data_limitations: string[];
  recommended_actions: {
    action: string;
    reason: string;
    priority: "High" | "Medium" | "Low";
  }[];
  suggested_skills_for_review: {
    job_title: string;
    skill_name: string;
    reason: string;
    status: string;
  }[];
};

export default function TNADashboard() {
  const [data, setData] = useState<TNAData | null>(null);
  const [insights, setInsights] = useState<AIInsights | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [error, setError] = useState("");
  const [aiError, setAiError] = useState("");
  const [lastUpdated, setLastUpdated] = useState("");

  const loadAnalysis = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`/api/tna?company_id=${COMPANY_ID}`);

      if (!response.ok) {
        throw new Error(`Unable to load TNA data (${response.status}).`);
      }

      const result = await response.json();
      setData(result);
      setLastUpdated(new Date().toLocaleString());
    } catch (err) {
      setError(err instanceof Error ? err.message : "An unexpected error occurred.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAnalysis();
  }, [loadAnalysis]);

  async function runAIAnalysis() {
    setAiLoading(true);
    setAiError("");
    setInsights(null);

    try {
      const response = await fetch(
        `/api/tna/ai-analysis?company_id=${COMPANY_ID}`,
        { method: "POST" }
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || `AI analysis failed (${response.status}).`);
      }

      if (result.status !== "insights_generated" || !result.ai_insights) {
        throw new Error(result.error || "AI analysis could not generate insights.");
      }

      setInsights(result.ai_insights);
    } catch (err) {
      setAiError(
        err instanceof Error ? err.message : "AI analysis is currently unavailable."
      );
    } finally {
      setAiLoading(false);
    }
  }

  const positions = data?.position_analysis ?? [];
  const departments = data?.department_analysis ?? [];
  const summary = data?.summary;

  const approvedRequirements = positions.reduce(
    (total, position) => total + (position.approved_requirement_count ?? 0), 0
  );
  const pendingRequirements = positions.reduce(
    (total, position) => total + (position.pending_requirement_count ?? 0), 0
  );
  const positionsWithoutRequirements = positions.filter(
    (position) => position.approved_requirement_count === 0
  ).length;

  const hasCoverage = approvedRequirements > 0;

  return (
    <main className="tna-page">
      <header className="tna-header">
        <div>
          <div className="tna-eyebrow">TRAINING MANAGEMENT</div>
          <h1>Training Needs Analysis</h1>
          <p>
            Understand workforce skill gaps, review training requirements,
            and identify areas that need attention.
          </p>
        </div>
        <button className="tna-refresh" onClick={loadAnalysis} disabled={loading}>
          {loading ? "Refreshing..." : "? Refresh data"}
        </button>
      </header>

      {error && (
        <div className="tna-alert tna-alert-error">
          <strong>Unable to load analysis</strong>
          <span>{error}</span>
          <button onClick={loadAnalysis}>Try again</button>
        </div>
      )}

      {loading && !data && (
        <div className="tna-loading">Loading training needs analysis...</div>
      )}

      {data && summary && (
        <>
          <section className="tna-stats">
            <article className="tna-stat">
              <span>Active employees</span>
              <strong>{summary.active_employees.toLocaleString()}</strong>
              <small>Employees included in this analysis</small>
            </article>
            <article className="tna-stat">
              <span>Positions analysed</span>
              <strong>{summary.positions_analysed.toLocaleString()}</strong>
              <small>Distinct job positions</small>
            </article>
            <article className="tna-stat">
              <span>Confirmed skill gaps</span>
              <strong>{summary.confirmed_skill_gaps.toLocaleString()}</strong>
              <small>Based on approved requirements and valid assessments</small>
            </article>
            <article className="tna-stat">
              <span>Assessments needed</span>
              <strong>{summary.assessments_needed.toLocaleString()}</strong>
              <small>Approved requirements without valid assessments</small>
            </article>
          </section>

          <section className={`tna-coverage ${hasCoverage ? "" : "tna-coverage-warning"}`}>
            <div className="tna-coverage-icon">{hasCoverage ? "i" : "!"}</div>
            <div>
              <strong>
                {hasCoverage
                  ? "Training data coverage"
                  : "Training needs cannot yet be fully determined"}
              </strong>
              <p>
                {approvedRequirements} approved skill requirements and{" "}
                {pendingRequirements} pending requirements are configured.
                {positionsWithoutRequirements} of {positions.length} positions
                currently have no approved requirements.
                {hasCoverage
                  ? " Confirmed gaps are calculated only against approved requirements."
                  : " Zero confirmed gaps does not mean employees have no skill gaps. Configure and approve job skill requirements to enable meaningful gap analysis."}
              </p>
            </div>
          </section>

          <section className="tna-section">
            <div className="tna-section-heading">
              <div>
                <h2>Training needs by position</h2>
                <p>Review requirement coverage across job positions.</p>
              </div>
              <span className="tna-count">{positions.length} positions</span>
            </div>

            <div className="tna-table-wrap">
              <table className="tna-table">
                <thead>
                  <tr>
                    <th>Job position</th>
                    <th>Employees</th>
                    <th>Approved</th>
                    <th>Pending</th>
                    <th>Rejected</th>
                    <th>Coverage</th>
                  </tr>
                </thead>
                <tbody>
                  {positions.map((position, index) => (
                    <tr key={`${position.job_title}-${index}`}>
                      <td className="tna-position-name">{position.job_title}</td>
                      <td>{position.employee_count}</td>
                      <td>{position.approved_requirement_count}</td>
                      <td>{position.pending_requirement_count}</td>
                      <td>{position.rejected_requirement_count}</td>
                      <td>
                        {position.approved_requirement_count > 0 ? (
                          <span className="tna-status tna-status-good">Configured</span>
                        ) : (
                          <span className="tna-status tna-status-warning">Not configured</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {positions.length === 0 && (
                    <tr><td colSpan={6}>No position data is available.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>

          <section className="tna-section">
            <div className="tna-section-heading">
              <div>
                <h2>Department analysis</h2>
                <p>Workforce coverage and identified skill gaps by department.</p>
              </div>
              <span className="tna-count">{departments.length} departments</span>
            </div>

            <div className="tna-department-grid">
              {departments.map((department, index) => (
                <article className="tna-department-card" key={`${department.department}-${index}`}>
                  <h3>{department.department}</h3>
                  <div className="tna-department-metrics">
                    <div>
                      <strong>{department.employee_count}</strong>
                      <span>Employees</span>
                    </div>
                    <div>
                      <strong>{department.confirmed_skill_gaps}</strong>
                      <span>Confirmed gaps</span>
                    </div>
                    <div>
                      <strong>{department.assessments_needed}</strong>
                      <span>Assessments needed</span>
                    </div>
                  </div>
                  <div className="tna-common-gaps">
                    <strong>Common skill gaps</strong>
                    {department.common_skill_gaps?.length ? (
                      department.common_skill_gaps.slice(0, 4).map((gap: any) => (
                        <div className="tna-gap-row" key={gap.skill_name}>
                          <span>{gap.skill_name}</span>
                          <span>{gap.employee_count} employees</span>
                        </div>
                      ))
                    ) : (
                      <p>No confirmed skill gaps recorded.</p>
                    )}
                  </div>
                </article>
              ))}
              {departments.length === 0 && (
                <p>No department data is available.</p>
              )}
            </div>
          </section>

          <section className="tna-ai-section">
            <div className="tna-ai-header">
              <div>
                <div className="tna-eyebrow">AI-POWERED ANALYSIS</div>
                <h2>AI findings and recommendations</h2>
                <p>
                  Generate insights from aggregated training data.
                  AI suggestions remain subject to human review.
                </p>
              </div>
              <button
                className="tna-ai-button"
                onClick={runAIAnalysis}
                disabled={aiLoading}
              >
                {aiLoading ? "Analysing..." : "? Run AI analysis"}
              </button>
            </div>

            {aiError && (
              <div className="tna-alert tna-alert-error">
                <strong>AI analysis unavailable</strong>
                <span>{aiError}</span>
                <small>
                  Your rule-based TNA results above are still available.
                  Check your AI service configuration or try again later.
                </small>
              </div>
            )}

            {aiLoading && (
              <div className="tna-ai-empty">Generating AI findings...</div>
            )}

            {!insights && !aiLoading && !aiError && (
              <div className="tna-ai-empty">
                <span className="tna-ai-sparkle">?</span>
                <strong>No AI analysis generated yet</strong>
                <p>Run the analysis to view findings and recommended actions.</p>
              </div>
            )}

            {insights && (
              <div className="tna-insights">
                <article className="tna-insight-card tna-summary-card">
                  <h3>Overall summary</h3>
                  <p>{insights.overall_summary}</p>
                </article>

                <div className="tna-insight-grid">
                  <article className="tna-insight-card">
                    <h3>Key findings</h3>
                    {insights.key_findings.map((item, index) => (
                      <div className="tna-finding" key={index}>
                        <strong>{item.finding}</strong>
                        <p>{item.evidence}</p>
                      </div>
                    ))}
                    {!insights.key_findings.length && <p>No key findings returned.</p>}
                  </article>

                  <article className="tna-insight-card">
                    <h3>Recommended actions</h3>
                    {insights.recommended_actions.map((item, index) => (
                      <div className="tna-action" key={index}>
                        <div className="tna-action-title">
                          <strong>{item.action}</strong>
                          <span className={`tna-priority tna-priority-${item.priority.toLowerCase()}`}>
                            {item.priority}
                          </span>
                        </div>
                        <p>{item.reason}</p>
                      </div>
                    ))}
                    {!insights.recommended_actions.length && <p>No actions returned.</p>}
                  </article>
                </div>

                <article className="tna-insight-card">
                  <h3>Data limitations</h3>
                  {insights.data_limitations.length ? (
                    <ul className="tna-limitations">
                      {insights.data_limitations.map((item, index) => (
                        <li key={index}>{item}</li>
                      ))}
                    </ul>
                  ) : (
                    <p>No limitations were reported.</p>
                  )}
                </article>

                <article className="tna-insight-card">
                  <div className="tna-section-heading">
                    <div>
                      <h3>Suggested skills awaiting review</h3>
                      <p>AI-proposed skills are not official requirements until reviewed.</p>
                    </div>
                    <span className="tna-count">
                      {insights.suggested_skills_for_review.length} suggestions
                    </span>
                  </div>

                  {insights.suggested_skills_for_review.length ? (
                    <div className="tna-table-wrap">
                      <table className="tna-table">
                        <thead>
                          <tr>
                            <th>Job position</th>
                            <th>Suggested skill</th>
                            <th>Reason</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {insights.suggested_skills_for_review.map((item, index) => (
                            <tr key={`${item.job_title}-${item.skill_name}-${index}`}>
                              <td>{item.job_title}</td>
                              <td className="tna-position-name">{item.skill_name}</td>
                              <td>{item.reason}</td>
                              <td>
                                <span className="tna-status tna-status-warning">
                                  Requires approval
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p>No suggested skills were returned by the AI analysis.</p>
                  )}
                  <p className="tna-review-note">
                    These suggestions are displayed for review only. They are not
                    automatically saved or approved as job requirements.
                  </p>
                </article>
              </div>
            )}
          </section>

          <footer className="tna-footer">
            <span>Company ID: {data.company_id}</span>
            <span>Analysis date: {String(data.analysis_date).slice(0, 10)}</span>
            {lastUpdated && <span>Last refreshed: {lastUpdated}</span>}
          </footer>
        </>
      )}
    </main>
  );
}


