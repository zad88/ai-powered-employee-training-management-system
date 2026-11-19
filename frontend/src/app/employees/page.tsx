"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { authenticatedFetch } from "../../lib/api";
import { useAuth } from "../../components/auth-provider";

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

const PAGE_SIZE = 12;

export default function EmployeesPage() {
  const { activeMembership } = useAuth();
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [department, setDepartment] = useState("All");
  const [status, setStatus] = useState("All");
  const [page, setPage] = useState(1);

  useEffect(() => {
    async function loadEmployees() {
      try {
        setLoading(true);
        setError("");

        const response = await authenticatedFetch(
          "/api/employees",
          { cache: "no-store" }
        );

        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || `Request failed (${response.status})`);
        }

        const data: Employee[] = await response.json();
        setEmployees(data);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Unable to load employees."
        );
      } finally {
        setLoading(false);
      }
    }

    loadEmployees();
  }, []);

  const departments = useMemo(
    () => [...new Set(employees.map((e) => e.department).filter(Boolean))].sort(),
    [employees]
  );

  const statuses = useMemo(
    () => [...new Set(employees.map((e) => e.employment_status).filter(Boolean))].sort(),
    [employees]
  );

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase();

    return employees.filter((employee) => {
      const matchesSearch =
        !term ||
        employee.full_name.toLowerCase().includes(term) ||
        employee.employee_id.toLowerCase().includes(term) ||
        employee.email.toLowerCase().includes(term) ||
        employee.job_title.toLowerCase().includes(term);

      const matchesDepartment =
        department === "All" || employee.department === department;

      const matchesStatus =
        status === "All" || employee.employment_status === status;

      return matchesSearch && matchesDepartment && matchesStatus;
    });
  }, [employees, search, department, status]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const visibleEmployees = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const activeCount = employees.filter((e) => e.is_active).length;
  const departmentCount = departments.length;

  function resetFilters() {
    setSearch("");
    setDepartment("All");
    setStatus("All");
    setPage(1);
  }

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
          <div><strong>Training Manager</strong><span>Administrator</span></div>
        </div>
      </aside>

      <section className="main-area">
        <header className="topbar">
          <div className="breadcrumb">Workspace / Employees</div>
          <div className="topbar-right">
            <span className="system-status"><i /> Read-only directory</span>
            <div className="top-avatar">TM</div>
          </div>
        </header>

        <div className="content employee-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">PEOPLE MANAGEMENT</div>
              <h1>Employees</h1>
              <p>View and explore your organization&apos;s employee records.</p>
            </div>
            <span className="workspace-badge">
              Company #{activeMembership?.company_id ?? ""}
            </span>
          </div>

          <section className="employee-stats">
            <div className="employee-stat">
              <span>Total employees</span>
              <strong>{loading ? "—" : employees.length.toLocaleString()}</strong>
              <small>Returned by the employee API</small>
            </div>
            <div className="employee-stat">
              <span>Active employees</span>
              <strong>{loading ? "—" : activeCount.toLocaleString()}</strong>
              <small>Active records</small>
            </div>
            <div className="employee-stat">
              <span>Departments</span>
              <strong>{loading ? "—" : departmentCount}</strong>
              <small>Distinct department names</small>
            </div>
            <div className="employee-stat">
              <span>Search results</span>
              <strong>{loading ? "—" : filtered.length.toLocaleString()}</strong>
              <small>Based on current filters</small>
            </div>
          </section>

          <section className="employee-panel">
            <div className="employee-panel-heading">
              <div>
                <h2>Employee directory</h2>
                <p>Search and filter employee records.</p>
              </div>
              <span className="read-only-label">READ ONLY</span>
            </div>

            <div className="employee-filters">
              <div className="employee-search">
                <span>⌕</span>
                <input
                  value={search}
                  onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                  placeholder="Search name, employee ID, email or job title..."
                />
              </div>

              <select
                value={department}
                onChange={(e) => { setDepartment(e.target.value); setPage(1); }}
                aria-label="Filter by department"
              >
                <option value="All">All departments</option>
                {departments.map((item) => <option key={item}>{item}</option>)}
              </select>

              <select
                value={status}
                onChange={(e) => { setStatus(e.target.value); setPage(1); }}
                aria-label="Filter by employment status"
              >
                <option value="All">All statuses</option>
                {statuses.map((item) => <option key={item}>{item}</option>)}
              </select>

              <button className="clear-filters" onClick={resetFilters}>
                Reset
              </button>
            </div>

            {loading && (
              <div className="employee-message">
                <div className="loading-spinner" />
                Loading employee records...
              </div>
            )}

            {!loading && error && (
              <div className="employee-error">
                <strong>Unable to load employees</strong>
                <p>{error}</p>
                <p>Check that the backend is running and the API is reachable.</p>
              </div>
            )}

            {!loading && !error && (
              <>
                <div className="employee-table-wrap">
                  <table className="employee-table">
                    <thead>
                      <tr>
                        <th>EMPLOYEE</th>
                        <th>EMPLOYEE ID</th>
                        <th>JOB TITLE</th>
                        <th>DEPARTMENT</th>
                        <th>STATUS</th>
                        <th>JOB LEVEL</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleEmployees.map((employee) => (
                        <tr key={employee.id}>
                          <td>
                            <div className="employee-name-cell">
                              <div className="employee-avatar">
                                {employee.full_name.trim().charAt(0).toUpperCase()}
                              </div>
                              <div>
                                <strong>{employee.full_name}</strong>
                                <span>{employee.email}</span>
                              </div>
                            </div>
                          </td>
                          <td className="employee-id">{employee.employee_id}</td>
                          <td>{employee.job_title}</td>
                          <td>{employee.department}</td>
                          <td>
                            <span className={`employment-badge ${employee.employment_status.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
                              {employee.employment_status}
                            </span>
                          </td>
                          <td>{employee.job_level}</td>
                          <td>
                            <Link className="view-employee" href={`/employees/${employee.id}`}>
                              View →
                            </Link>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {visibleEmployees.length === 0 && (
                    <div className="employee-empty">
                      <strong>No employees found</strong>
                      <p>Try changing your search or filters.</p>
                      <button className="clear-filters" onClick={resetFilters}>Clear filters</button>
                    </div>
                  )}
                </div>

                <div className="employee-pagination">
                  <span>
                    Showing {filtered.length === 0 ? 0 : (currentPage - 1) * PAGE_SIZE + 1}
                    {"–"}
                    {Math.min(currentPage * PAGE_SIZE, filtered.length)} of {filtered.length}
                  </span>
                  <div>
                    <button
                      disabled={currentPage <= 1}
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                    >Previous</button>
                    <span>Page {currentPage} of {totalPages}</span>
                    <button
                      disabled={currentPage >= totalPages}
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    >Next</button>
                  </div>
                </div>
              </>
            )}
          </section>
        </div>
      </section>
    </main>
  );
}
