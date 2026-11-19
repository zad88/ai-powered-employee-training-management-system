"use client";

import { useEffect, useState, FormEvent } from "react";
import { authenticatedFetch } from "../../lib/api";
import { useAuth } from "../../components/auth-provider";

type Employee = {
  id: number;
  employee_id: string;
  full_name: string;
  job_title?: string;
  is_active: boolean;
};

type Skill = {
  skill_id: number;
  skill_name: string;
  category?: string;
};

type Requirement = {
  id: number;
  company_id: number;
  job_title: string;
  skill_id: number;
  required_proficiency: number;
  importance: string;
  approval_status: string;
  approved_by: number | null;
};

export default function JobSkillsPage() {
  const { activeMembership } = useAuth();
  const canEdit = activeMembership?.role === "Training Manager";
  const canApprove = canEdit || activeMembership?.role === "Director";
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [jobFilter, setJobFilter] = useState("All");
  const [editingId, setEditingId] = useState<number | null>(null);

  const [form, setForm] = useState({
    job_title: "",
    skill_id: "",
    required_proficiency: "3",
    importance: "Medium",
  });

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const [requirementsResponse, employeesResponse, skillsResponse] =
        await Promise.all([
          authenticatedFetch("/api/job-skills", {
            cache: "no-store",
          }),
          authenticatedFetch("/api/employees", {
            cache: "no-store",
          }),
          authenticatedFetch("/api/skills", { cache: "no-store" }),
        ]);

      if (
        !requirementsResponse.ok ||
        !employeesResponse.ok ||
        !skillsResponse.ok
      ) {
        throw new Error("Unable to load one or more API resources.");
      }

      const [requirementsData, employeesData, skillsData] = await Promise.all([
        requirementsResponse.json(),
        employeesResponse.json(),
        skillsResponse.json(),
      ]);

      setRequirements(Array.isArray(requirementsData) ? requirementsData : []);
      setEmployees(
        Array.isArray(employeesData)
          ? employeesData.filter((employee: Employee) => employee.is_active)
          : []
      );
      setSkills(Array.isArray(skillsData) ? skillsData : []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load job requirements."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  function resetForm() {
    setForm({
      job_title: "",
      skill_id: "",
      required_proficiency: "3",
      importance: "Medium",
    });
    setEditingId(null);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (form.job_title.trim().length < 2) {
      setError("Job title must contain at least 2 characters.");
      return;
    }

    if (!form.skill_id && editingId === null) {
      setError("Please select a skill.");
      return;
    }

    setSaving(true);

    try {
      const isEditing = editingId !== null;
      const url = isEditing
        ? `/api/job-skills/${editingId}`
        : "/api/job-skills";

      const payload = isEditing
        ? {
            required_proficiency: Number(form.required_proficiency),
            importance: form.importance,
          }
        : {
            job_title: form.job_title.trim(),
            skill_id: Number(form.skill_id),
            required_proficiency: Number(form.required_proficiency),
            importance: form.importance,
          };

      const response = await authenticatedFetch(url, {
        method: isEditing ? "PUT" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await response.text());
      }

      setSuccess(
        isEditing
          ? "Requirement updated. It has returned to Pending approval."
          : "Requirement created successfully. It is Pending approval."
      );

      resetForm();
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to save requirement."
      );
    } finally {
      setSaving(false);
    }
  }

  function startEditing(item: Requirement) {
    setEditingId(item.id);
    setForm({
      job_title: item.job_title,
      skill_id: String(item.skill_id),
      required_proficiency: String(item.required_proficiency),
      importance: item.importance,
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function reviewRequirement(
    item: Requirement,
    approvalStatus: "Approved" | "Rejected"
  ) {
    setError("");
    setSuccess("");

    if (
      !window.confirm(
        `Are you sure you want to ${approvalStatus.toLowerCase()} this requirement?`
      )
    ) {
      return;
    }

    try {
      const response = await authenticatedFetch(
        `/api/job-skills/${item.id}/approval`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approval_status: approvalStatus }),
        }
      );

      if (!response.ok) {
        throw new Error(await response.text());
      }

      setSuccess(`Requirement ${approvalStatus.toLowerCase()} successfully.`);
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to review requirement."
      );
    }
  }

  function getSkillName(skillId: number) {
    return (
      skills.find((skill) => skill.skill_id === skillId)?.skill_name ??
      `Skill #${skillId}`
    );
  }

  function getApproverName(id: number | null) {
    if (!id) return "Not approved";
    const employee = employees.find((item) => item.id === id);
    return employee ? employee.full_name : `Employee #${id}`;
  }

  const pendingCount = requirements.filter(
    (item) => item.approval_status === "Pending"
  ).length;

  const approvedCount = requirements.filter(
    (item) => item.approval_status === "Approved"
  ).length;

  const rejectedCount = requirements.filter(
    (item) => item.approval_status === "Rejected"
  ).length;

  const jobTitles = Array.from(
    new Set(requirements.map((item) => item.job_title))
  ).sort();

  const filteredRequirements = requirements.filter((item) => {
    const matchesStatus =
      statusFilter === "All" || item.approval_status === statusFilter;
    const matchesJob = jobFilter === "All" || item.job_title === jobFilter;
    return matchesStatus && matchesJob;
  });

  if (loading) {
    return (
      <main className="job-skills-page">
        <p>Loading job skill requirements...</p>
      </main>
    );
  }

  return (
    <main className="job-skills-page">
      <header className="job-skills-header">
        <div>
          <p className="job-skills-eyebrow">EMPLOYEE DEVELOPMENT</p>
          <h1>Job Skill Requirements</h1>
          <p>
            Define the skills and proficiency levels expected for each job
            title.
          </p>
        </div>
        <button className="job-skills-refresh" onClick={loadData}>
          Refresh data
        </button>
      </header>

      {error && <div className="job-skills-alert error">{error}</div>}
      {success && <div className="job-skills-alert success">{success}</div>}

      <section className="job-skills-stats">
        <div className="job-skills-stat">
          <span>Total requirements</span>
          <strong>{requirements.length}</strong>
        </div>
        <div className="job-skills-stat">
          <span>Pending approval</span>
          <strong>{pendingCount}</strong>
        </div>
        <div className="job-skills-stat">
          <span>Approved</span>
          <strong>{approvedCount}</strong>
        </div>
        <div className="job-skills-stat">
          <span>Rejected</span>
          <strong>{rejectedCount}</strong>
        </div>
      </section>

      {canEdit && <section className="job-skills-panel">
        <div className="job-skills-section-heading">
          <div>
            <h2>{editingId ? "Edit requirement" : "Add job requirement"}</h2>
            <p>
              {editingId
                ? "Changes will require approval again."
                : "New requirements are automatically submitted as Pending."}
            </p>
          </div>
        </div>

        {skills.length === 0 ? (
          <p className="job-skills-empty">
            No skills are available in the shared Skills catalogue.
          </p>
        ) : (
          <form className="job-skills-form" onSubmit={handleSubmit}>
            <label>
              Job title
              {editingId ? (
                <input value={form.job_title} disabled />
              ) : (
                <>
                  <input
                    required
                    minLength={2}
                    maxLength={150}
                    list="job-title-options"
                    value={form.job_title}
                    onChange={(event) =>
                      setForm({ ...form, job_title: event.target.value })
                    }
                    placeholder="e.g. AI Engineer"
                  />
                  <datalist id="job-title-options">
                    {Array.from(
                      new Set(
                        employees
                          .map((employee) => employee.job_title)
                          .filter(Boolean)
                      )
                    ).map((title) => (
                      <option key={title} value={title} />
                    ))}
                  </datalist>
                </>
              )}
            </label>

            <label>
              Skill
              <select
                required
                disabled={editingId !== null}
                value={form.skill_id}
                onChange={(event) =>
                  setForm({ ...form, skill_id: event.target.value })
                }
              >
                <option value="">Select a skill</option>
                {skills.map((skill) => (
                  <option key={skill.skill_id} value={skill.skill_id}>
                    {skill.skill_name}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Required proficiency
              <select
                value={form.required_proficiency}
                onChange={(event) =>
                  setForm({
                    ...form,
                    required_proficiency: event.target.value,
                  })
                }
              >
                {[1, 2, 3, 4, 5].map((level) => (
                  <option key={level} value={level}>
                    {level} / 5
                  </option>
                ))}
              </select>
            </label>

            <label>
              Importance
              <select
                value={form.importance}
                onChange={(event) =>
                  setForm({ ...form, importance: event.target.value })
                }
              >
                <option value="Critical">Critical</option>
                <option value="High">High</option>
                <option value="Medium">Medium</option>
                <option value="Low">Low</option>
              </select>
            </label>

            <div className="job-skills-form-actions">
              <button
                className="job-skills-submit"
                type="submit"
                disabled={saving}
              >
                {saving
                  ? "Saving..."
                  : editingId
                    ? "Save changes"
                    : "Add requirement"}
              </button>

              {editingId !== null && (
                <button
                  className="job-skills-cancel"
                  type="button"
                  onClick={resetForm}
                >
                  Cancel editing
                </button>
              )}
            </div>
          </form>
        )}
      </section>}

      <section className="job-skills-panel">
        <div className="job-skills-section-heading">
          <div>
            <h2>Requirement records</h2>
            <p>Manage job requirements and their approval status.</p>
          </div>
        </div>

        <div className="job-skills-filters">
          <label>
            Job title
            <select
              value={jobFilter}
              onChange={(event) => setJobFilter(event.target.value)}
            >
              <option value="All">All job titles</option>
              {jobTitles.map((title) => (
                <option key={title} value={title}>
                  {title}
                </option>
              ))}
            </select>
          </label>

          <label>
            Approval status
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
            >
              <option value="All">All statuses</option>
              <option value="Pending">Pending</option>
              <option value="Approved">Approved</option>
              <option value="Rejected">Rejected</option>
            </select>
          </label>
        </div>

        {filteredRequirements.length === 0 ? (
          <p className="job-skills-empty">
            No requirements match the selected filters.
          </p>
        ) : (
          <div className="job-skills-table-wrapper">
            <table className="job-skills-table">
              <thead>
                <tr>
                  <th>Job title</th>
                  <th>Skill</th>
                  <th>Required level</th>
                  <th>Importance</th>
                  <th>Status</th>
                  <th>Approved by</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredRequirements.map((item) => (
                  <tr key={item.id}>
                    <td>{item.job_title}</td>
                    <td>{getSkillName(item.skill_id)}</td>
                    <td>{item.required_proficiency} / 5</td>
                    <td>{item.importance}</td>
                    <td>
                      <span
                        className={`job-skills-status ${item.approval_status.toLowerCase()}`}
                      >
                        {item.approval_status}
                      </span>
                    </td>
                    <td>{getApproverName(item.approved_by)}</td>
                    <td>
                      <div className="job-skills-actions">
                        {canEdit && <button
                          className="job-skills-edit"
                          onClick={() => startEditing(item)}
                        >
                          Edit
                        </button>}
                        {canApprove && item.approval_status === "Pending" && (
                          <>
                            <button
                              className="job-skills-approve"
                              onClick={() =>
                                reviewRequirement(item, "Approved")
                              }
                            >
                              Approve
                            </button>
                            <button
                              className="job-skills-reject"
                              onClick={() =>
                                reviewRequirement(item, "Rejected")
                              }
                            >
                              Reject
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
