"use client";

import { FormEvent, useEffect, useState } from "react";

const COMPANY_ID = 14;

type Employee = {
  id: number;
  employee_id: string;
  full_name: string;
  job_title?: string;
  department?: string;
  employment_status?: string;
};

type Skill = {
  skill_id: number;
  skill_name: string;
  category?: string;
};

type Assessment = {
  assessment_id: number;
  employee_id: number;
  skill_id: number;
  proficiency_level: number;
  assessment_source: string;
  assessment_score: number | null;
  evidence_quality: string;
  assessment_date: string;
  expiry_date: string | null;
  assessor_comments: string | null;
  evidence_status: string;
};

export default function AssessmentsPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const getToday = () => {
    const date = new Date();
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  };

  const [form, setForm] = useState({
    employee_id: "",
    skill_id: "",
    proficiency_level: "1",
    assessment_source: "Manager Assessment",
    assessment_score: "",
    evidence_quality: "Medium",
    assessment_date: getToday(),
    expiry_date: "",
    assessor_comments: "",
  });

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const [employeeResponse, skillResponse, assessmentResponse] =
        await Promise.all([
          fetch(`/api/employees?company_id=${COMPANY_ID}`, {
            cache: "no-store",
          }),
          fetch("/api/skills", { cache: "no-store" }),
          fetch(`/api/skill-assessments?company_id=${COMPANY_ID}`, {
            cache: "no-store",
          }),
        ]);

      if (!employeeResponse.ok || !skillResponse.ok || !assessmentResponse.ok) {
        throw new Error("One or more API requests failed. Check the backend.");
      }

      const employeeData = await employeeResponse.json();
      const skillData = await skillResponse.json();
      const assessmentData = await assessmentResponse.json();

      setEmployees(Array.isArray(employeeData) ? employeeData : []);
      setSkills(Array.isArray(skillData) ? skillData : []);
      setAssessments(Array.isArray(assessmentData) ? assessmentData : []);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to load assessment data."
      );
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!form.employee_id || !form.skill_id) {
      setError("Please select an employee and a skill.");
      return;
    }

    if (
      form.expiry_date &&
      form.expiry_date < form.assessment_date
    ) {
      setError("Expiry date cannot be before the assessment date.");
      return;
    }

    const payload = {
      employee_id: Number(form.employee_id),
      skill_id: Number(form.skill_id),
      proficiency_level: Number(form.proficiency_level),
      assessment_source: form.assessment_source.trim(),
      assessment_score:
        form.assessment_score === ""
          ? null
          : Number(form.assessment_score),
      evidence_quality: form.evidence_quality,
      assessment_date: form.assessment_date,
      expiry_date: form.expiry_date || null,
      assessor_comments: form.assessor_comments.trim() || null,
    };

    setSaving(true);

    try {
      const response = await fetch(
        `/api/skill-assessments?company_id=${COMPANY_ID}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        const responseText = await response.text();
        throw new Error(responseText || "Assessment creation failed.");
      }

      setSuccess("Assessment created successfully. It is pending review.");

      setForm({
        employee_id: "",
        skill_id: "",
        proficiency_level: "1",
        assessment_source: "Manager Assessment",
        assessment_score: "",
        evidence_quality: "Medium",
        assessment_date: getToday(),
        expiry_date: "",
        assessor_comments: "",
      });

      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to create assessment."
      );
    } finally {
      setSaving(false);
    }
  }

  async function reviewAssessment(
    assessmentId: number,
    status: "Approved" | "Rejected"
  ) {
    setError("");
    setSuccess("");

    const confirmed = window.confirm(
      `Are you sure you want to ${status.toLowerCase()} this assessment?`
    );

    if (!confirmed) return;

    try {
      const response = await fetch(
        `/api/skill-assessments/${assessmentId}/review?company_id=${COMPANY_ID}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ evidence_status: status }),
        }
      );

      if (!response.ok) {
        const responseText = await response.text();
        throw new Error(responseText || "Assessment review failed.");
      }

      setSuccess(`Assessment ${status.toLowerCase()} successfully.`);
      await loadData();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Unable to review assessment."
      );
    }
  }

  const pendingCount = assessments.filter(
    (item) => item.evidence_status === "Pending Review"
  ).length;

  const approvedCount = assessments.filter(
    (item) => item.evidence_status === "Approved"
  ).length;

  const rejectedCount = assessments.filter(
    (item) => item.evidence_status === "Rejected"
  ).length;

  const filteredAssessments =
    selectedStatus === "All"
      ? assessments
      : assessments.filter(
          (item) => item.evidence_status === selectedStatus
        );

  function employeeName(employeeId: number) {
    const employee = employees.find((item) => item.id === employeeId);
    return employee
      ? `${employee.full_name} (${employee.employee_id})`
      : `Employee #${employeeId}`;
  }

  function skillName(skillId: number) {
    return (
      skills.find((item) => item.skill_id === skillId)?.skill_name ??
      `Skill #${skillId}`
    );
  }

  if (loading) {
    return (
      <main className="assessment-page">
        <p>Loading assessment management...</p>
      </main>
    );
  }

  return (
    <main className="assessment-page">
      <header className="assessment-header">
        <div>
          <p className="assessment-eyebrow">EMPLOYEE DEVELOPMENT</p>
          <h1>Skill Assessment Management</h1>
          <p>
            Record employee skill assessments and review their supporting
            evidence.
          </p>
        </div>
        <button className="assessment-refresh" onClick={loadData}>
          Refresh data
        </button>
      </header>

      {error && <div className="assessment-alert error">{error}</div>}
      {success && <div className="assessment-alert success">{success}</div>}

      <section className="assessment-stats">
        <div className="assessment-stat">
          <span>Total assessments</span>
          <strong>{assessments.length}</strong>
        </div>
        <div className="assessment-stat">
          <span>Pending review</span>
          <strong>{pendingCount}</strong>
        </div>
        <div className="assessment-stat">
          <span>Approved</span>
          <strong>{approvedCount}</strong>
        </div>
        <div className="assessment-stat">
          <span>Rejected</span>
          <strong>{rejectedCount}</strong>
        </div>
      </section>

      <section className="assessment-panel">
        <div className="assessment-section-heading">
          <div>
            <h2>Create a skill assessment</h2>
            <p>
              New assessments are automatically submitted as Pending Review.
            </p>
          </div>
        </div>

        {employees.length === 0 || skills.length === 0 ? (
          <p className="assessment-empty">
            You need at least one employee and one skill before creating an
            assessment.
          </p>
        ) : (
          <form className="assessment-form" onSubmit={handleSubmit}>
            <label>
              Employee
              <select
                required
                value={form.employee_id}
                onChange={(event) =>
                  setForm({ ...form, employee_id: event.target.value })
                }
              >
                <option value="">Select an employee</option>
                {employees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.full_name} — {employee.employee_id}
                  </option>
                ))}
              </select>
            </label>

            <label>
              Skill
              <select
                required
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
              Proficiency level
              <select
                value={form.proficiency_level}
                onChange={(event) =>
                  setForm({ ...form, proficiency_level: event.target.value })
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
              Assessment source
              <input
                required
                maxLength={50}
                value={form.assessment_source}
                onChange={(event) =>
                  setForm({ ...form, assessment_source: event.target.value })
                }
                placeholder="e.g. Manager Assessment"
              />
            </label>

            <label>
              Assessment score (optional)
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={form.assessment_score}
                onChange={(event) =>
                  setForm({ ...form, assessment_score: event.target.value })
                }
                placeholder="0–100"
              />
            </label>

            <label>
              Evidence quality
              <select
                value={form.evidence_quality}
                onChange={(event) =>
                  setForm({ ...form, evidence_quality: event.target.value })
                }
              >
                <option value="Low">Low</option>
                <option value="Medium">Medium</option>
                <option value="High">High</option>
              </select>
            </label>

            <label>
              Assessment date
              <input
                type="date"
                required
                value={form.assessment_date}
                onChange={(event) =>
                  setForm({ ...form, assessment_date: event.target.value })
                }
              />
            </label>

            <label>
              Expiry date (optional)
              <input
                type="date"
                min={form.assessment_date}
                value={form.expiry_date}
                onChange={(event) =>
                  setForm({ ...form, expiry_date: event.target.value })
                }
              />
            </label>

            <label className="assessment-full-width">
              Assessor comments (optional)
              <textarea
                rows={3}
                value={form.assessor_comments}
                onChange={(event) =>
                  setForm({ ...form, assessor_comments: event.target.value })
                }
                placeholder="Add assessment notes or evidence details..."
              />
            </label>

            <div className="assessment-full-width">
              <button
                className="assessment-submit"
                type="submit"
                disabled={saving}
              >
                {saving ? "Creating..." : "Create assessment"}
              </button>
            </div>
          </form>
        )}

        <p className="assessment-note">
          This form records evidence details and comments. It does not upload
          documents or files.
        </p>
      </section>

      <section className="assessment-panel">
        <div className="assessment-section-heading assessment-record-heading">
          <div>
            <h2>Assessment records</h2>
            <p>Review assessment history and submitted evidence.</p>
          </div>

          <select
            className="assessment-filter"
            value={selectedStatus}
            onChange={(event) => setSelectedStatus(event.target.value)}
            aria-label="Filter assessments by status"
          >
            <option value="All">All statuses</option>
            <option value="Pending Review">Pending Review</option>
            <option value="Approved">Approved</option>
            <option value="Rejected">Rejected</option>
          </select>
        </div>

        {filteredAssessments.length === 0 ? (
          <p className="assessment-empty">
            No assessment records found for this filter.
          </p>
        ) : (
          <div className="assessment-table-wrapper">
            <table className="assessment-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Skill</th>
                  <th>Level</th>
                  <th>Source</th>
                  <th>Evidence</th>
                  <th>Date</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filteredAssessments.map((assessment) => (
                  <tr key={assessment.assessment_id}>
                    <td>{employeeName(assessment.employee_id)}</td>
                    <td>{skillName(assessment.skill_id)}</td>
                    <td>{assessment.proficiency_level}/5</td>
                    <td>{assessment.assessment_source}</td>
                    <td>{assessment.evidence_quality}</td>
                    <td>{assessment.assessment_date}</td>
                    <td>
                      <span
                        className={`assessment-status ${assessment.evidence_status
                          .toLowerCase()
                          .replaceAll(" ", "-")}`}
                      >
                        {assessment.evidence_status}
                      </span>
                    </td>
                    <td>
                      {assessment.evidence_status === "Pending Review" ? (
                        <div className="assessment-actions">
                          <button
                            className="assessment-approve"
                            onClick={() =>
                              reviewAssessment(
                                assessment.assessment_id,
                                "Approved"
                              )
                            }
                          >
                            Approve
                          </button>
                          <button
                            className="assessment-reject"
                            onClick={() =>
                              reviewAssessment(
                                assessment.assessment_id,
                                "Rejected"
                              )
                            }
                          >
                            Reject
                          </button>
                        </div>
                      ) : (
                        <span className="assessment-no-action">—</span>
                      )}
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
