"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

const COMPANY_ID = 14;

type Employee = {
  id: number;
  employee_id: string;
  full_name: string;
  email: string | null;
  job_title: string | null;
  department: string | null;
  employment_status: string | null;
  is_active: boolean;
};

type Skill = {
  skill_id: number;
  skill_name: string;
  category: string | null;
};

type Assessment = {
  assessment_id: number;
  company_id: number;
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

type JobRequirement = {
  id: number;
  company_id: number;
  job_title: string;
  skill_id: number;
  required_proficiency: number;
  importance: string;
  approval_status: string;
};

function formatDate(value: string | null) {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString();
}

function isCurrentAssessment(assessment: Assessment) {
  if (assessment.evidence_status !== "Approved") return false;
  if (!assessment.expiry_date) return true;

  const expiry = new Date(assessment.expiry_date);
  if (Number.isNaN(expiry.getTime())) return false;

  const today = new Date();
  today.setHours(0, 0, 0, 0);
  expiry.setHours(0, 0, 0, 0);

  return expiry >= today;
}

export default function EmployeeSkillsPage() {
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [requirements, setRequirements] = useState<JobRequirement[]>([]);
  const [selectedEmployeeId, setSelectedEmployeeId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadData() {
      try {
        const endpoints = [
          `/api/employees?company_id=${COMPANY_ID}`,
          "/api/skills",
          `/api/skill-assessments?company_id=${COMPANY_ID}`,
          `/api/job-skills?company_id=${COMPANY_ID}`,
        ];

        const responses = await Promise.all(
          endpoints.map((url) => fetch(url, { cache: "no-store" }))
        );

        const failed = responses.find((response) => !response.ok);
        if (failed) {
          throw new Error(`API request failed (${failed.status}).`);
        }

        const [employeeData, skillData, assessmentData, requirementData] =
          await Promise.all(responses.map((response) => response.json()));

        setEmployees(Array.isArray(employeeData) ? employeeData : []);
        setSkills(Array.isArray(skillData) ? skillData : []);
        setAssessments(Array.isArray(assessmentData) ? assessmentData : []);
        setRequirements(Array.isArray(requirementData) ? requirementData : []);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load employee skills."
        );
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  useEffect(() => {
    if (!selectedEmployeeId && employees.length > 0) {
      setSelectedEmployeeId(String(employees[0].id));
    }
  }, [employees, selectedEmployeeId]);

  const selectedEmployee = employees.find(
    (employee) => String(employee.id) === selectedEmployeeId
  );

  const employeeAssessments = useMemo(() => {
    if (!selectedEmployee) return [];

    return assessments
      .filter((item) => item.employee_id === selectedEmployee.id)
      .sort(
        (a, b) =>
          new Date(b.assessment_date).getTime() -
          new Date(a.assessment_date).getTime()
      );
  }, [assessments, selectedEmployee]);

  const employeeRequirements = useMemo(() => {
    if (!selectedEmployee?.job_title) return [];

    return requirements.filter(
      (item) =>
        item.job_title.trim().toLowerCase() ===
        selectedEmployee.job_title!.trim().toLowerCase()
    );
  }, [requirements, selectedEmployee]);

  const skillMap = useMemo(
    () => new Map(skills.map((skill) => [skill.skill_id, skill])),
    [skills]
  );

  const currentAssessments = useMemo(() => {
    const latest = new Map<number, Assessment>();

    for (const assessment of employeeAssessments) {
      if (!isCurrentAssessment(assessment)) continue;

      const existing = latest.get(assessment.skill_id);
      if (
        !existing ||
        new Date(assessment.assessment_date).getTime() >
          new Date(existing.assessment_date).getTime()
      ) {
        latest.set(assessment.skill_id, assessment);
      }
    }

    return latest;
  }, [employeeAssessments]);

  const approvedRequirements = employeeRequirements.filter(
    (item) => item.approval_status === "Approved"
  );

  const gapCount = approvedRequirements.filter((requirement) => {
    const assessment = currentAssessments.get(requirement.skill_id);
    return (
      assessment &&
      assessment.proficiency_level < requirement.required_proficiency
    );
  }).length;

  const assessmentNeededCount = approvedRequirements.filter(
    (requirement) => !currentAssessments.has(requirement.skill_id)
  ).length;

  const pendingRequirements = employeeRequirements.filter(
    (item) => item.approval_status === "Pending"
  ).length;

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <div className="brand-icon">T</div>
          <div><strong>TalentFlow</strong><span>Training Management</span></div>
        </Link>

        <div className="nav-label">WORKSPACE</div>
        <Link href="/" className="nav-item">▦ <span>Overview</span></Link>
        <Link href="/imports" className="nav-item">▤ <span>Employee Imports</span></Link>

        <div className="nav-label nav-spaced">MANAGEMENT</div>
        <Link href="/employees" className="nav-item">♙ <span>Employees</span></Link>
        <Link href="/skills" className="nav-item">◇ <span>Skills</span></Link>
        <Link href="/employee-skills" className="nav-item active">▣ <span>Employee Skills</span></Link>
        <div className="nav-item">▣ <span>Courses</span></div>
        <div className="nav-item">⌕ <span>Training Needs</span></div>
        <div className="nav-item">▤ <span>Training Plans</span></div>
        <div className="nav-item">▷ <span>Execution</span></div>
        <div className="nav-item">▥ <span>Reports</span></div>

        <div className="sidebar-bottom">
          <div className="user-avatar">TM</div>
          <div><strong>Training Manager</strong><span>Administrator</span></div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace / Employee Skills</div>
          <div className="topbar-right">
            <span className="system-status"><i /> Read-only records</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content employee-skills-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">TALENT MANAGEMENT</div>
              <h1>Employee Skills &amp; Proficiency</h1>
              <p>
                Review employee competencies, assessment evidence and
                approved role requirements.
              </p>
            </div>
            <span className="workspace-badge">Company {COMPANY_ID}</span>
          </div>

          {loading && <div className="skills-message">Loading employee skill data...</div>}
          {error && <div className="employee-skills-error">{error}</div>}

          {!loading && !error && (
            <>
              <section className="employee-skills-stats">
                <div className="employee-skills-stat">
                  <span>Employees</span>
                  <strong>{employees.length}</strong>
                  <small>Company employees</small>
                </div>
                <div className="employee-skills-stat">
                  <span>Skill assessments</span>
                  <strong>{assessments.length}</strong>
                  <small>Recorded assessment entries</small>
                </div>
                <div className="employee-skills-stat">
                  <span>Approved requirements</span>
                  <strong>{approvedRequirements.length}</strong>
                  <small>For the selected employee's role</small>
                </div>
                <div className="employee-skills-stat">
                  <span>Identified skill gaps</span>
                  <strong>{gapCount}</strong>
                  <small>Based on valid approved records</small>
                </div>
              </section>

              <section className="employee-skills-panel">
                <div className="employee-skills-panel-heading">
                  <div>
                    <h2>Select employee</h2>
                    <p>Choose an employee to review their skills and assessments.</p>
                  </div>
                </div>

                {employees.length === 0 ? (
                  <div className="employee-skills-empty">
                    <strong>No employees found</strong>
                    <p>There are no employee records for this company.</p>
                  </div>
                ) : (
                  <>
                    <select
                      className="employee-skills-select"
                      value={selectedEmployeeId}
                      onChange={(event) => setSelectedEmployeeId(event.target.value)}
                    >
                      {employees.map((employee) => (
                        <option key={employee.id} value={employee.id}>
                          {employee.full_name} — {employee.employee_id}
                        </option>
                      ))}
                    </select>

                    {selectedEmployee && (
                      <div className="employee-skills-profile">
                        <div className="employee-skills-avatar">
                          {selectedEmployee.full_name
                            .split(" ")
                            .map((part) => part[0])
                            .slice(0, 2)
                            .join("")
                            .toUpperCase()}
                        </div>
                        <div className="employee-skills-identity">
                          <h3>{selectedEmployee.full_name}</h3>
                          <p>{selectedEmployee.job_title || "No job title"} · {selectedEmployee.department || "No department"}</p>
                          <span>Employee ID: {selectedEmployee.employee_id}</span>
                        </div>
                        <span className="employee-skills-status">
                          {selectedEmployee.employment_status || "Status unavailable"}
                        </span>
                      </div>
                    )}
                  </>
                )}
              </section>

              {selectedEmployee && (
                <>
                  <section className="employee-skills-panel">
                    <div className="employee-skills-panel-heading">
                      <div>
                        <h2>Role skill requirements</h2>
                        <p>
                          Required proficiency levels for {selectedEmployee.job_title || "this employee's role"}.
                        </p>
                      </div>
                      <span className="employee-skills-count">
                        {employeeRequirements.length} requirements
                      </span>
                    </div>

                    {employeeRequirements.length === 0 ? (
                      <div className="employee-skills-empty">
                        <strong>No role requirements found</strong>
                        <p>No requirements currently match this employee's job title.</p>
                      </div>
                    ) : (
                      <div className="employee-skills-table-wrap">
                        <table className="employee-skills-table">
                          <thead>
                            <tr>
                              <th>Skill</th>
                              <th>Required level</th>
                              <th>Importance</th>
                              <th>Approval</th>
                            </tr>
                          </thead>
                          <tbody>
                            {employeeRequirements.map((requirement) => (
                              <tr key={requirement.id}>
                                <td>
                                  <strong>
                                    {skillMap.get(requirement.skill_id)?.skill_name ||
                                      `Skill #${requirement.skill_id}`}
                                  </strong>
                                  <small>
                                    {skillMap.get(requirement.skill_id)?.category || "Uncategorised"}
                                  </small>
                                </td>
                                <td>{requirement.required_proficiency} / 5</td>
                                <td>{requirement.importance}</td>
                                <td>
                                  <span className={
                                    requirement.approval_status === "Approved"
                                      ? "employee-skills-badge approved"
                                      : requirement.approval_status === "Rejected"
                                      ? "employee-skills-badge rejected"
                                      : "employee-skills-badge pending"
                                  }>
                                    {requirement.approval_status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {pendingRequirements > 0 && (
                      <p className="employee-skills-note">
                        {pendingRequirements} requirement(s) are pending approval
                        and are excluded from official skill-gap calculations.
                      </p>
                    )}
                  </section>

                  <section className="employee-skills-panel">
                    <div className="employee-skills-panel-heading">
                      <div>
                        <h2>Current confirmed proficiency</h2>
                        <p>
                          Only the latest approved, non-expired assessment per skill is counted.
                        </p>
                      </div>
                    </div>

                    {currentAssessments.size === 0 ? (
                      <div className="employee-skills-empty">
                        <strong>No confirmed proficiency records</strong>
                        <p>
                          This employee has no approved, current skill assessments.
                          Proficiency cannot be inferred from job title or role requirements.
                        </p>
                      </div>
                    ) : (
                      <div className="employee-skills-table-wrap">
                        <table className="employee-skills-table">
                          <thead>
                            <tr>
                              <th>Skill</th>
                              <th>Proficiency</th>
                              <th>Assessment date</th>
                              <th>Source</th>
                            </tr>
                          </thead>
                          <tbody>
                            {[...currentAssessments.entries()].map(([skillId, item]) => (
                              <tr key={skillId}>
                                <td>{skillMap.get(skillId)?.skill_name || `Skill #${skillId}`}</td>
                                <td>
                                  <strong>{item.proficiency_level} / 5</strong>
                                  <span className="employee-skills-level">
                                    <i style={{ width: `${item.proficiency_level * 20}%` }} />
                                  </span>
                                </td>
                                <td>{formatDate(item.assessment_date)}</td>
                                <td>{item.assessment_source}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>

                  <section className="employee-skills-panel">
                    <div className="employee-skills-panel-heading">
                      <div>
                        <h2>Skill gap overview</h2>
                        <p>
                          Comparisons require an approved role requirement and a valid approved assessment.
                        </p>
                      </div>
                    </div>

                    {approvedRequirements.length === 0 ? (
                      <div className="employee-skills-empty">
                        <strong>No approved requirements to compare</strong>
                        <p>Role requirements must be approved before official gaps can be calculated.</p>
                      </div>
                    ) : (
                      <div className="employee-skills-gap-summary">
                        <div>
                          <strong>{gapCount}</strong>
                          <span>Confirmed gaps</span>
                        </div>
                        <div>
                          <strong>{assessmentNeededCount}</strong>
                          <span>Assessments needed</span>
                        </div>
                      </div>
                    )}

                    {approvedRequirements.length > 0 && (
                      <div className="employee-skills-table-wrap">
                        <table className="employee-skills-table">
                          <thead>
                            <tr>
                              <th>Skill</th>
                              <th>Required</th>
                              <th>Confirmed</th>
                              <th>Result</th>
                            </tr>
                          </thead>
                          <tbody>
                            {approvedRequirements.map((requirement) => {
                              const assessment = currentAssessments.get(requirement.skill_id);
                              const hasGap = assessment &&
                                assessment.proficiency_level < requirement.required_proficiency;

                              return (
                                <tr key={requirement.id}>
                                  <td>{skillMap.get(requirement.skill_id)?.skill_name || `Skill #${requirement.skill_id}`}</td>
                                  <td>{requirement.required_proficiency} / 5</td>
                                  <td>{assessment ? `${assessment.proficiency_level} / 5` : "Not assessed"}</td>
                                  <td>
                                    <span className={
                                      !assessment
                                        ? "employee-skills-badge pending"
                                        : hasGap
                                        ? "employee-skills-badge rejected"
                                        : "employee-skills-badge approved"
                                    }>
                                      {!assessment ? "Assessment needed" : hasGap ? "Gap identified" : "Requirement met"}
                                    </span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>

                  <section className="employee-skills-panel">
                    <div className="employee-skills-panel-heading">
                      <div>
                        <h2>Assessment history</h2>
                        <p>All recorded assessments, including pending and rejected reviews.</p>
                      </div>
                      <span className="employee-skills-count">
                        {employeeAssessments.length} records
                      </span>
                    </div>

                    {employeeAssessments.length === 0 ? (
                      <div className="employee-skills-empty">
                        <strong>No assessments recorded</strong>
                        <p>Assessment history will appear here when records are created.</p>
                      </div>
                    ) : (
                      <div className="employee-skills-table-wrap">
                        <table className="employee-skills-table">
                          <thead>
                            <tr>
                              <th>Skill</th>
                              <th>Level</th>
                              <th>Date</th>
                              <th>Evidence quality</th>
                              <th>Review status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {employeeAssessments.map((item) => (
                              <tr key={item.assessment_id}>
                                <td>
                                  {skillMap.get(item.skill_id)?.skill_name ||
                                    `Skill #${item.skill_id}`}
                                </td>
                                <td>{item.proficiency_level} / 5</td>
                                <td>{formatDate(item.assessment_date)}</td>
                                <td>{item.evidence_quality}</td>
                                <td>
                                  <span className={
                                    item.evidence_status === "Approved"
                                      ? "employee-skills-badge approved"
                                      : item.evidence_status === "Rejected"
                                      ? "employee-skills-badge rejected"
                                      : "employee-skills-badge pending"
                                  }>
                                    {item.evidence_status}
                                  </span>
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </section>
                </>
              )}
            </>
          )}
        </div>
      </section>
    </main>
  );
}
