"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

type Employee = {
  id: number;
  company_id: number;
  employee_id: string;
  full_name: string;
  email: string;
  job_title: string;
  department: string;
  manager_id: string | null;
  manager_internal_id: number | null;
  employment_status: string;
  working_hours_per_week: string | number | null;
  learning_hours_per_week: string | number | null;
  years_of_experience: string | number | null;
  hire_date: string;
  job_level: string;
  employment_type: string;
  preferred_learning_mode: string | null;
  is_active: boolean;
};

const COMPANY_ID = 14;

function Field({ label, value }: {
  label: string;
  value: string | number | null | undefined;
}) {
  return (
    <div className="profile-field">
      <span>{label}</span>
      <strong>
        {value === null || value === undefined || value === ""
          ? "Not provided"
          : value}
      </strong>
    </div>
  );
}

export default function EmployeeProfilePage() {
  const params = useParams<{ id: string }>();
  const [employee, setEmployee] = useState<Employee | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    async function loadEmployee() {
      try {
        setLoading(true);
        setError("");

        const response = await fetch(
          `/api/employees/${encodeURIComponent(params.id)}?company_id=${COMPANY_ID}`,
          { cache: "no-store" }
        );

        if (!response.ok) {
          if (response.status === 404) {
            throw new Error("Employee not found in this company.");
          }
          throw new Error(`Unable to retrieve employee (${response.status}).`);
        }

        setEmployee(await response.json());
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load employee."
        );
      } finally {
        setLoading(false);
      }
    }

    if (params.id) loadEmployee();
  }, [params.id]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <Link href="/" className="brand">
          <div className="brand-icon">T</div>
          <div>
            <strong>TalentFlow</strong>
            <span>Training Management</span>
          </div>
        </Link>

        <div className="nav-label">WORKSPACE</div>
        <Link href="/" className="nav-item">▦ <span>Overview</span></Link>
        <Link href="/imports" className="nav-item">▤ <span>Employee Imports</span></Link>

        <div className="nav-label nav-spaced">MANAGEMENT</div>
        <Link href="/employees" className="nav-item active">♙ <span>Employees</span></Link>
        <div className="nav-item">◇ <span>Skills</span></div>
        <div className="nav-item">▣ <span>Courses</span></div>
        <div className="nav-item">⌕ <span>Training Needs</span></div>
        <div className="nav-item">▤ <span>Training Plans</span></div>
        <div className="nav-item">▷ <span>Execution</span></div>
        <div className="nav-item">▥ <span>Reports</span></div>

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
          <div className="breadcrumb">
            <Link href="/employees">Employees</Link> / Employee profile
          </div>
          <div className="topbar-right">
            <span className="system-status"><i /> Read-only profile</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content employee-content">
          <Link href="/employees" className="back-link">
            ← Back to employees
          </Link>

          {loading && (
            <div className="employee-message">
              <div className="loading-spinner" />
              Loading employee profile...
            </div>
          )}

          {!loading && error && (
            <div className="employee-error">
              <strong>Could not open employee profile</strong>
              <p>{error}</p>
              <Link href="/employees" className="view-employee">
                Return to directory
              </Link>
            </div>
          )}

          {!loading && !error && employee && (
            <>
              <div className="profile-header">
                <div className="profile-avatar">
                  {employee.full_name.trim().charAt(0).toUpperCase()}
                </div>
                <div className="profile-heading">
                  <div className="eyebrow">EMPLOYEE PROFILE</div>
                  <h1>{employee.full_name}</h1>
                  <p>{employee.job_title} · {employee.department}</p>
                  <div className="profile-tags">
                    <span className="employee-id">{employee.employee_id}</span>
                    <span className="employment-badge">
                      {employee.employment_status}
                    </span>
                  </div>
                </div>
              </div>

              <section className="profile-section">
                <div className="profile-section-heading">
                  <h2>Personal and contact information</h2>
                  <span>GENERAL</span>
                </div>
                <div className="profile-fields">
                  <Field label="Full name" value={employee.full_name} />
                  <Field label="Email address" value={employee.email} />
                  <Field label="Employee ID" value={employee.employee_id} />
                  <Field label="Database record ID" value={employee.id} />
                </div>
              </section>

              <section className="profile-section">
                <div className="profile-section-heading">
                  <h2>Employment information</h2>
                  <span>ORGANIZATION</span>
                </div>
                <div className="profile-fields">
                  <Field label="Job title" value={employee.job_title} />
                  <Field label="Department" value={employee.department} />
                  <Field label="Job level" value={employee.job_level} />
                  <Field label="Employment status" value={employee.employment_status} />
                  <Field label="Employment type" value={employee.employment_type} />
                  <Field label="Hire date" value={employee.hire_date} />
                  <Field label="Manager employee ID" value={employee.manager_id} />
                  <Field label="Manager database ID" value={employee.manager_internal_id} />
                  <Field label="Years of experience" value={employee.years_of_experience} />
                  <Field label="Company ID" value={employee.company_id} />
                  <Field label="Active record" value={employee.is_active ? "Yes" : "No"} />
                </div>
              </section>

              <section className="profile-section">
                <div className="profile-section-heading">
                  <h2>Learning information</h2>
                  <span>DEVELOPMENT</span>
                </div>
                <div className="profile-fields">
                  <Field label="Working hours per week" value={employee.working_hours_per_week} />
                  <Field label="Learning hours per week" value={employee.learning_hours_per_week} />
                  <Field label="Preferred learning mode" value={employee.preferred_learning_mode} />
                </div>
              </section>

              <div className="profile-readonly-note">
                This profile is currently read-only. No employee information has been changed.
              </div>
            </>
          )}
        </div>
      </section>
    </main>
  );
}