"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

const COMPANY_ID = 14;

type Skill = {
  skill_id: number;
  skill_name: string;
  category: string | null;
  description: string | null;
};

type Requirement = {
  id: number;
  company_id: number;
  job_title: string;
  skill_id: number;
  required_proficiency: number;
  importance: string;
  approval_status: "Pending" | "Approved" | "Rejected";
  approved_by: number | null;
};

type Employee = {
  id: number;
  full_name: string;
  employee_id: string;
  job_title: string;
  is_active: boolean;
};

type Position = {
  job_title: string;
  employee_count: number;
};

async function apiRequest<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options?.headers || {}),
    },
  });

  const text = await response.text();
  let result: any = null;

  try {
    result = text ? JSON.parse(text) : null;
  } catch {
    result = text;
  }

  if (!response.ok) {
    const detail =
      typeof result === "object" && result !== null
        ? result.detail || result.message
        : result;

    throw new Error(detail || `Request failed (${response.status}).`);
  }

  return result as T;
}

export default function JobRequirementsPage() {
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [positions, setPositions] = useState<Position[]>([]);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [jobFilter, setJobFilter] = useState("All positions");
  const [statusFilter, setStatusFilter] = useState("All statuses");
  const [search, setSearch] = useState("");
  const [approverId, setApproverId] = useState("");

  const [jobTitle, setJobTitle] = useState("");
  const [skillId, setSkillId] = useState("");
  const [proficiency, setProficiency] = useState("3");
  const [importance, setImportance] = useState("Medium");
  const [editingId, setEditingId] = useState<number | null>(null);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError("");

    try {
      const [requirementData, skillData, employeeData, tnaData] =
        await Promise.all([
          apiRequest<Requirement[]>(
            `/api/job-skills?company_id=${COMPANY_ID}`
          ),
          apiRequest<Skill[]>("/api/skills"),
          apiRequest<Employee[]>(
            `/api/employees?company_id=${COMPANY_ID}`
          ),
          apiRequest<any>(`/api/tna?company_id=${COMPANY_ID}`),
        ]);

      setRequirements(requirementData);
      setSkills(skillData);
      setEmployees(employeeData.filter((employee) => employee.is_active));
      setPositions(tnaData.position_analysis || []);

      if (!jobTitle && tnaData.position_analysis?.length) {
        setJobTitle(tnaData.position_analysis[0].job_title);
      }

      if (!skillId && skillData.length) {
        setSkillId(String(skillData[0].skill_id));
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load job requirements."
      );
    } finally {
      setLoading(false);
    }
  }, [jobTitle, skillId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const skillMap = useMemo(
    () => new Map(skills.map((skill) => [skill.skill_id, skill])),
    [skills]
  );

  const jobTitles = useMemo(() => {
    const titles = new Set([
      ...positions.map((position) => position.job_title),
      ...requirements.map((requirement) => requirement.job_title),
    ]);

    return Array.from(titles)
      .filter((title) => title && title.trim().length > 0 && title !== "string")
      .sort((a, b) => a.localeCompare(b));
  }, [positions, requirements]);

  const filteredRequirements = useMemo(() => {
    return requirements.filter((requirement) => {
      const skillName =
        skillMap.get(requirement.skill_id)?.skill_name || "";

      const matchesJob =
        jobFilter === "All positions" ||
        requirement.job_title === jobFilter;

      const matchesStatus =
        statusFilter === "All statuses" ||
        requirement.approval_status === statusFilter;

      const query = search.trim().toLowerCase();
      const matchesSearch =
        !query ||
        requirement.job_title.toLowerCase().includes(query) ||
        skillName.toLowerCase().includes(query);

      return matchesJob && matchesStatus && matchesSearch;
    });
  }, [requirements, skillMap, jobFilter, statusFilter, search]);

  const pendingCount = requirements.filter(
    (item) => item.approval_status === "Pending"
  ).length;

  const approvedCount = requirements.filter(
    (item) => item.approval_status === "Approved"
  ).length;

  const rejectedCount = requirements.filter(
    (item) => item.approval_status === "Rejected"
  ).length;

  function resetForm() {
    setEditingId(null);
    setJobTitle(jobTitles[0] || "");
    setSkillId(skills[0] ? String(skills[0].skill_id) : "");
    setProficiency("3");
    setImportance("Medium");
  }

  function startEditing(requirement: Requirement) {
    setEditingId(requirement.id);
    setJobTitle(requirement.job_title);
    setSkillId(String(requirement.skill_id));
    setProficiency(String(requirement.required_proficiency));
    setImportance(requirement.importance);
    setMessage("");
    setError("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function saveRequirement(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    setMessage("");

    try {
      if (!jobTitle || !skillId) {
        throw new Error("Select a job position and an existing skill.");
      }

      if (editingId !== null) {
        await apiRequest<Requirement>(
          `/api/job-skills/${editingId}?company_id=${COMPANY_ID}`,
          {
            method: "PUT",
            body: JSON.stringify({
              required_proficiency: Number(proficiency),
              importance,
            }),
          }
        );

        setMessage(
          "Requirement updated. It has returned to Pending and needs approval again."
        );
      } else {
        await apiRequest<Requirement>(
          `/api/job-skills?company_id=${COMPANY_ID}`,
          {
            method: "POST",
            body: JSON.stringify({
              job_title: jobTitle,
              skill_id: Number(skillId),
              required_proficiency: Number(proficiency),
              importance,
            }),
          }
        );

        setMessage("Requirement created and submitted for approval.");
      }

      resetForm();
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save the requirement."
      );
    } finally {
      setSaving(false);
    }
  }

  async function updateApproval(
    requirement: Requirement,
    approvalStatus: "Approved" | "Rejected"
  ) {
    setError("");
    setMessage("");

    if (!approverId) {
      setError("Select an active employee to record this approval decision.");
      return;
    }

    try {
      await apiRequest<Requirement>(
        `/api/job-skills/${requirement.id}/approval?company_id=${COMPANY_ID}&approved_by=${approverId}`,
        {
          method: "PUT",
          body: JSON.stringify({ approval_status: approvalStatus }),
        }
      );

      setMessage(
        `Requirement ${approvalStatus.toLowerCase()} successfully.`
      );
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to update approval."
      );
    }
  }

  return (
    <main className="job-skills-page">
      <header className="job-skills-header">
        <div>
          <p className="job-skills-eyebrow">DEFINITION / JOB REQUIREMENTS</p>
          <h1>Job Requirements Management</h1>
          <p>
            Define the skills required for each position and review
            requirements before they are used in Training Needs Analysis.
          </p>
        </div>

        <button
          className="job-skills-refresh"
          type="button"
          onClick={loadData}
          disabled={loading}
        >
          {loading ? "Refreshing..." : "↻ Refresh data"}
        </button>
      </header>

      {error && (
        <div className="job-skills-alert error" role="alert">
          {error}
        </div>
      )}

      {message && (
        <div className="job-skills-alert success" role="status">
          {message}
        </div>
      )}

      <section className="job-skills-stats">
        <div className="job-skills-stat">
          <span>Job positions</span>
          <strong>{jobTitles.length}</strong>
        </div>
        <div className="job-skills-stat">
          <span>Total requirements</span>
          <strong>{requirements.length}</strong>
        </div>
        <div className="job-skills-stat">
          <span>Pending approval</span>
          <strong>{pendingCount}</strong>
        </div>
        <div className="job-skills-stat">
          <span>Approved requirements</span>
          <strong>{approvedCount}</strong>
        </div>
      </section>

      <section className="job-skills-panel">
        <div className="job-skills-section-heading">
          <div>
            <h2>{editingId !== null ? "Edit requirement" : "Add a job requirement"}</h2>
            <p>
              Choose an existing skill and define the proficiency expected
              for this position.
            </p>
          </div>
        </div>

        <form className="job-skills-form" onSubmit={saveRequirement}>
          <label>
            Job position
            <select
              value={jobTitle}
              onChange={(event) => setJobTitle(event.target.value)}
              required
              disabled={editingId !== null}
            >
              <option value="">Select a position</option>
              {jobTitles.map((title) => (
                <option value={title} key={title}>
                  {title}
                </option>
              ))}
            </select>
          </label>

          <label>
            Required skill
            <select
              value={skillId}
              onChange={(event) => setSkillId(event.target.value)}
              required
              disabled={editingId !== null}
            >
              <option value="">Select an existing skill</option>
              {skills.map((skill) => (
                <option value={skill.skill_id} key={skill.skill_id}>
                  {skill.skill_name}
                  {skill.category ? ` — ${skill.category}` : ""}
                </option>
              ))}
            </select>
          </label>

          <label>
            Required proficiency
            <select
              value={proficiency}
              onChange={(event) => setProficiency(event.target.value)}
              required
            >
              <option value="1">1 — Beginner</option>
              <option value="2">2 — Basic</option>
              <option value="3">3 — Intermediate</option>
              <option value="4">4 — Advanced</option>
              <option value="5">5 — Expert</option>
            </select>
          </label>

          <label>
            Importance
            <select
              value={importance}
              onChange={(event) => setImportance(event.target.value)}
              required
            >
              <option value="Low">Low</option>
              <option value="Medium">Medium</option>
              <option value="High">High</option>
              <option value="Critical">Critical</option>
            </select>
          </label>

          <div className="job-skills-form-actions">
            <button
              className="job-skills-submit"
              type="submit"
              disabled={saving || loading || !skills.length || !jobTitles.length}
            >
              {saving
                ? "Saving..."
                : editingId !== null
                  ? "Save changes"
                  : "Add requirement"}
            </button>

            {editingId !== null && (
              <button
                className="job-skills-cancel"
                type="button"
                onClick={resetForm}
                disabled={saving}
              >
                Cancel editing
              </button>
            )}
          </div>
        </form>

        <p className="job-skills-note">
          New requirements are saved as Pending. Editing an existing
          requirement also resets its approval status to Pending.
        </p>

        {!loading && skills.length === 0 && (
          <div className="job-skills-alert error">
            No skills were returned by the Skills API. Add skills in Skills
            Management before creating job requirements.
          </div>
        )}

        {!loading && jobTitles.length === 0 && (
          <div className="job-skills-alert error">
            No job positions were returned by the TNA API. Check the employee
            job-title data before creating requirements.
          </div>
        )}
      </section>

      <section className="job-skills-panel">
        <div className="job-skills-section-heading">
          <div>
            <h2>Requirements and approval</h2>
            <p>
              Review the requirements configured for company {COMPANY_ID}.
            </p>
          </div>
          <span className="job-skills-status pending">
            {pendingCount} pending
          </span>
        </div>

        <div className="job-skills-approver">
          <label>
            Approving employee
            <select
              value={approverId}
              onChange={(event) => setApproverId(event.target.value)}
            >
              <option value="">Select an active employee</option>
              {employees.map((employee) => (
                <option value={employee.id} key={employee.id}>
                  {employee.full_name} — {employee.job_title} (DB ID: {employee.id})
                </option>
              ))}
            </select>
          </label>
          <p>
            The backend records this employee's internal database ID.
            Currently, it validates active status and company membership;
            manager-role authorization is not yet enforced by the API.
          </p>
        </div>

        <div className="job-skills-filters">
          <label>
            Filter by position
            <select
              value={jobFilter}
              onChange={(event) => setJobFilter(event.target.value)}
            >
              <option>All positions</option>
              {jobTitles.map((title) => (
                <option key={title} value={title}>
                  {title}
                </option>
              ))}
            </select>
          </label>

          <label>
            Filter by status
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option>All statuses</option>
              <option>Pending</option>
              <option>Approved</option>
              <option>Rejected</option>
            </select>
          </label>

          <label>
            Search position or skill
            <input
              className="job-skills-search"
              type="search"
              placeholder="Search requirements..."
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>
        </div>

        {loading ? (
          <div className="job-skills-empty">Loading job requirements...</div>
        ) : filteredRequirements.length === 0 ? (
          <div className="job-skills-empty">
            No requirements match the selected filters.
          </div>
        ) : (
          <div className="job-skills-table-wrapper">
            <table className="job-skills-table">
              <thead>
                <tr>
                  <th>Job position</th>
                  <th>Required skill</th>
                  <th>Proficiency</th>
                  <th>Importance</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRequirements.map((requirement) => {
                  const skill = skillMap.get(requirement.skill_id);

                  return (
                    <tr key={requirement.id}>
                      <td>{requirement.job_title}</td>
                      <td>
                        {skill?.skill_name || `Skill #${requirement.skill_id}`}
                      </td>
                      <td>{requirement.required_proficiency} / 5</td>
                      <td>{requirement.importance}</td>
                      <td>
                        <span
                          className={`job-skills-status ${
                            requirement.approval_status.toLowerCase()
                          }`}
                        >
                          {requirement.approval_status}
                        </span>
                      </td>
                      <td>
                        <div className="job-skills-actions">
                          <button
                            className="job-skills-edit"
                            type="button"
                            onClick={() => startEditing(requirement)}
                          >
                            Edit
                          </button>

                          {requirement.approval_status === "Pending" ? (
                            <>
                              <button
                                className="job-skills-approve"
                                type="button"
                                onClick={() =>
                                  updateApproval(requirement, "Approved")
                                }
                                disabled={!approverId}
                                title={
                                  !approverId
                                    ? "Select an approving employee first"
                                    : "Approve requirement"
                                }
                              >
                                Approve
                              </button>
                              <button
                                className="job-skills-reject"
                                type="button"
                                onClick={() =>
                                  updateApproval(requirement, "Rejected")
                                }
                                disabled={!approverId}
                                title={
                                  !approverId
                                    ? "Select an approving employee first"
                                    : "Reject requirement"
                                }
                              >
                                Reject
                              </button>
                            </>
                          ) : (
                            <span className="job-skills-no-action">
                              No review needed
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        <p className="job-skills-note">
          Showing {filteredRequirements.length} of {requirements.length}{" "}
          requirements. Rejected: {rejectedCount}. Only Approved requirements
          are used as confirmed job requirements by the TNA analysis.
        </p>
      </section>
    </main>
  );
}

