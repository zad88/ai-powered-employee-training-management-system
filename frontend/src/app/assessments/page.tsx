"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { authenticatedFetch } from "../../lib/api";
import { useAuth } from "../../components/auth-provider";

const ASSESSMENT_SOURCES = [
  "Manager Assessment",
  "Technical Test",
  "Practical Demonstration",
  "Self-Assessment",
  "Project or Work Sample",
  "Certificate",
  "Peer Assessment",
  "External Assessment",
];

const PROFICIENCY_LEVELS = [
  { value: 1, label: "Beginner", description: "Basic awareness; needs guidance." },
  { value: 2, label: "Basic", description: "Can perform simple tasks with support." },
  { value: 3, label: "Intermediate", description: "Works independently on routine tasks." },
  { value: 4, label: "Advanced", description: "Handles complex tasks and supports others." },
  { value: 5, label: "Expert", description: "Demonstrates mastery and can lead or mentor." },
];

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
  evidence_title: string | null;
  evidence_description: string | null;
  assessment_date: string;
  expiry_date: string | null;
  assessor_comments: string | null;
  evidence_status: string;
};

const today = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
};

const emptyForm = () => ({
  employee_id: "",
  employee_search: "",
  skill_id: "",
  proficiency_level: "1",
  assessment_source: "Manager Assessment",
  assessment_score: "",
  evidence_quality: "Medium",
  evidence_title: "",
  evidence_description: "",
  assessment_date: today(),
  expiry_date: "",
  assessor_comments: "",
});

export default function AssessmentsPage() {
  const { activeMembership } = useAuth();
  const canCreate = activeMembership?.role === "Training Manager" ||
    activeMembership?.role === "Manager" ||
    activeMembership?.role === "Employee";
  const canReview = activeMembership?.role === "Training Manager" ||
    activeMembership?.role === "Director" ||
    activeMembership?.role === "Manager";
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [selectedStatus, setSelectedStatus] = useState("All");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  async function loadData() {
    setLoading(true);
    setError("");

    try {
      const [employeeResponse, skillResponse, assessmentResponse] =
        await Promise.all([
          authenticatedFetch("/api/employees", { cache: "no-store" }),
          authenticatedFetch("/api/skills", { cache: "no-store" }),
          authenticatedFetch("/api/skill-assessments", { cache: "no-store" }),
        ]);

      if (!employeeResponse.ok || !skillResponse.ok || !assessmentResponse.ok) {
        throw new Error("One or more API requests failed. Check the backend.");
      }

      const [employeeData, skillData, assessmentData] = await Promise.all([
        employeeResponse.json(),
        skillResponse.json(),
        assessmentResponse.json(),
      ]);

      setEmployees(Array.isArray(employeeData) ? employeeData : []);
      setSkills(Array.isArray(skillData) ? skillData : []);
      setAssessments(Array.isArray(assessmentData) ? assessmentData : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load assessment data.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadData(), 0);
    return () => window.clearTimeout(timer);
  }, []);

  const selectedEmployee = employees.find(
    (employee) => String(employee.id) === form.employee_id
  );

  const selectedSkill = skills.find(
    (skill) => String(skill.skill_id) === form.skill_id
  );

  const filteredEmployees = useMemo(() => {
    const term = form.employee_search.trim().toLowerCase();
    if (!term) return employees.slice(0, 30);

    return employees.filter((employee) =>
      [
        employee.full_name,
        employee.employee_id,
        employee.job_title ?? "",
        employee.department ?? "",
      ].some((value) => value.toLowerCase().includes(term))
    ).slice(0, 50);
  }, [employees, form.employee_search]);

  const selectedLevel = PROFICIENCY_LEVELS.find(
    (level) => String(level.value) === form.proficiency_level
  );

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSuccess("");

    if (!form.employee_id || !form.skill_id) {
      setError("Please select an employee and a skill.");
      return;
    }

    if (form.evidence_title.trim().length < 2) {
      setError("Please enter an evidence title.");
      return;
    }

    if (form.expiry_date && form.expiry_date < form.assessment_date) {
      setError("Expiry date cannot be before the assessment date.");
      return;
    }

    const payload = {
      employee_id: Number(form.employee_id),
      skill_id: Number(form.skill_id),
      proficiency_level: Number(form.proficiency_level),
      assessment_source: form.assessment_source,
      assessment_score: form.assessment_score === "" ? null : Number(form.assessment_score),
      evidence_quality: form.evidence_quality,
      evidence_title: form.evidence_title.trim(),
      evidence_description: form.evidence_description.trim() || null,
      assessment_date: form.assessment_date,
      expiry_date: form.expiry_date || null,
      assessor_comments: form.assessor_comments.trim() || null,
    };

    setSaving(true);

    try {
      const response = await authenticatedFetch(
        "/api/skill-assessments",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        }
      );

      if (!response.ok) {
        const body = await response.text();
        throw new Error(body || "Assessment creation failed.");
      }

      setSuccess("Assessment created successfully and submitted for review.");
      setForm(emptyForm());
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to create assessment.");
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

    if (!window.confirm(`Are you sure you want to ${status.toLowerCase()} this assessment?`)) {
      return;
    }

    try {
      const response = await authenticatedFetch(
        `/api/skill-assessments/${assessmentId}/review`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ evidence_status: status }),
        }
      );

      if (!response.ok) {
        throw new Error(await response.text() || "Assessment review failed.");
      }

      setSuccess(`Assessment ${status.toLowerCase()} successfully.`);
      await loadData();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to review assessment.");
    }
  }

  const pendingCount = assessments.filter((item) => item.evidence_status === "Pending Review").length;
  const approvedCount = assessments.filter((item) => item.evidence_status === "Approved").length;
  const rejectedCount = assessments.filter((item) => item.evidence_status === "Rejected").length;

  const filteredAssessments = selectedStatus === "All"
    ? assessments
    : assessments.filter((item) => item.evidence_status === selectedStatus);

  function employeeName(employeeId: number) {
    const employee = employees.find((item) => item.id === employeeId);
    return employee ? `${employee.full_name} (${employee.employee_id})` : `Employee #${employeeId}`;
  }

  function skillName(skillId: number) {
    return skills.find((item) => item.skill_id === skillId)?.skill_name ?? `Skill #${skillId}`;
  }

  if (loading) {
    return <main className="assessment-page"><p>Loading assessment management...</p></main>;
  }

  return (
    <main className="assessment-page">
      <header className="assessment-header">
        <div>
          <p className="assessment-eyebrow">EMPLOYEE DEVELOPMENT</p>
          <h1>Skill Assessment Management</h1>
          <p>Record employee skills, document supporting evidence, and manage review status.</p>
        </div>
        <button type="button" className="assessment-refresh" onClick={loadData}>Refresh data</button>
      </header>

      {error && <div className="assessment-alert error">{error}</div>}
      {success && <div className="assessment-alert success">{success}</div>}

      <section className="assessment-stats">
        <div className="assessment-stat"><span>Total assessments</span><strong>{assessments.length}</strong></div>
        <div className="assessment-stat"><span>Pending review</span><strong>{pendingCount}</strong></div>
        <div className="assessment-stat"><span>Approved</span><strong>{approvedCount}</strong></div>
        <div className="assessment-stat"><span>Rejected</span><strong>{rejectedCount}</strong></div>
      </section>

      {canCreate && <section className="assessment-panel">
        <div className="assessment-section-heading">
          <div>
            <h2>Create a skill assessment</h2>
            <p>Complete the assessment and its supporting evidence. New submissions require review.</p>
          </div>
        </div>

        {employees.length === 0 || skills.length === 0 ? (
          <p className="assessment-empty">You need at least one employee and one skill before creating an assessment.</p>
        ) : (
          <form className="assessment-form" onSubmit={handleSubmit}>
            <div className="assessment-full-width">
              <h3>1. Employee information</h3>
            </div>

            <label className="assessment-full-width">
              Search employees
              <input
                type="search"
                value={form.employee_search}
                placeholder="Search by name, employee ID, job title, or department"
                onChange={(event) => setForm({
                  ...form,
                  employee_search: event.target.value,
                  employee_id: "",
                })}
              />
            </label>

            <label className="assessment-full-width">
              Select employee
              <select
                required
                value={form.employee_id}
                onChange={(event) => setForm({ ...form, employee_id: event.target.value })}
              >
                <option value="">Select an employee</option>
                {filteredEmployees.map((employee) => (
                  <option key={employee.id} value={employee.id}>
                    {employee.full_name} — {employee.employee_id}
                  </option>
                ))}
              </select>
              <small>{filteredEmployees.length} matching employees shown (maximum 50).</small>
            </label>

            {selectedEmployee && (
              <div className="assessment-full-width assessment-note">
                <strong>{selectedEmployee.full_name}</strong>
                <p>Employee ID: {selectedEmployee.employee_id}</p>
                <p>Job title: {selectedEmployee.job_title || "Not available"}</p>
                <p>Department: {selectedEmployee.department || "Not available"}</p>
              </div>
            )}

            <div className="assessment-full-width">
              <h3>2. Skill assessment</h3>
            </div>

            <label>
              Skill
              <select
                required
                value={form.skill_id}
                onChange={(event) => setForm({ ...form, skill_id: event.target.value })}
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
                onChange={(event) => setForm({ ...form, proficiency_level: event.target.value })}
              >
                {PROFICIENCY_LEVELS.map((level) => (
                  <option key={level.value} value={level.value}>
                    {level.value} — {level.label}
                  </option>
                ))}
              </select>
            </label>

            {selectedSkill && (
              <div className="assessment-full-width assessment-note">
                <strong>{selectedSkill.skill_name}</strong>
                <p>Category: {selectedSkill.category || "Not specified"}</p>
              </div>
            )}

            {selectedLevel && (
              <div className="assessment-full-width assessment-note">
                <strong>Level {selectedLevel.value}: {selectedLevel.label}</strong>
                <p>{selectedLevel.description}</p>
              </div>
            )}

            <div className="assessment-full-width">
              <h3>3. Assessment method and results</h3>
            </div>

            <label>
              Assessment method
              <select
                required
                value={form.assessment_source}
                onChange={(event) => setForm({ ...form, assessment_source: event.target.value })}
              >
                {ASSESSMENT_SOURCES.map((source) => (
                  <option key={source} value={source}>{source}</option>
                ))}
              </select>
            </label>

            <label>
              Assessment score (optional)
              <input
                type="number"
                min="0"
                max="100"
                step="0.01"
                value={form.assessment_score}
                onChange={(event) => setForm({ ...form, assessment_score: event.target.value })}
                placeholder="0–100"
              />
            </label>

            <label>
              Evidence quality
              <select
                value={form.evidence_quality}
                onChange={(event) => setForm({ ...form, evidence_quality: event.target.value })}
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
                onChange={(event) => setForm({ ...form, assessment_date: event.target.value })}
              />
            </label>

            <label>
              Expiry date (optional)
              <input
                type="date"
                min={form.assessment_date}
                value={form.expiry_date}
                onChange={(event) => setForm({ ...form, expiry_date: event.target.value })}
              />
            </label>

            <div className="assessment-full-width">
              <h3>4. Supporting evidence</h3>
            </div>

            <label className="assessment-full-width">
              Evidence title
              <input
                required
                minLength={2}
                maxLength={200}
                value={form.evidence_title}
                onChange={(event) => setForm({ ...form, evidence_title: event.target.value })}
                placeholder="e.g. Python Technical Assessment"
              />
            </label>

            <label className="assessment-full-width">
              Evidence description
              <textarea
                rows={4}
                maxLength={5000}
                value={form.evidence_description}
                onChange={(event) => setForm({ ...form, evidence_description: event.target.value })}
                placeholder="Describe the evidence, what was assessed, and what it demonstrates."
              />
            </label>

            <label className="assessment-full-width">
              Assessor comments (optional)
              <textarea
                rows={3}
                maxLength={5000}
                value={form.assessor_comments}
                onChange={(event) => setForm({ ...form, assessor_comments: event.target.value })}
                placeholder="Add observations or additional notes."
              />
            </label>

            <div className="assessment-full-width">
              <button className="assessment-submit" type="submit" disabled={saving}>
                {saving ? "Submitting..." : "Submit assessment for review"}
              </button>
            </div>
          </form>
        )}

        <p className="assessment-note">
          Evidence is recorded as text. This version does not upload documents or files.
          An assessment does not become verified proficiency until it is approved.
        </p>
      </section>}

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
          <p className="assessment-empty">No assessment records found for this filter.</p>
        ) : (
          <div className="assessment-table-wrapper">
            <table className="assessment-table">
              <thead>
                <tr>
                  <th>Employee</th>
                  <th>Skill</th>
                  <th>Level</th>
                  <th>Method</th>
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
                    <td>
                      <strong>{assessment.evidence_title || "Legacy record"}</strong>
                      {assessment.evidence_description && <p>{assessment.evidence_description}</p>}
                      <small>Quality: {assessment.evidence_quality}</small>
                    </td>
                    <td>{assessment.assessment_date}</td>
                    <td>
                      <span className={`assessment-status ${assessment.evidence_status.toLowerCase().replaceAll(" ", "-")}`}>
                        {assessment.evidence_status}
                      </span>
                    </td>
                    <td>
                      {canReview && assessment.evidence_status === "Pending Review" ? (
                        <div className="assessment-actions">
                          <button
                            type="button"
                            className="assessment-approve"
                            onClick={() => reviewAssessment(assessment.assessment_id, "Approved")}
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            className="assessment-reject"
                            onClick={() => reviewAssessment(assessment.assessment_id, "Rejected")}
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
