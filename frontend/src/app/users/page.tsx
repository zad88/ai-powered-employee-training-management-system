"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { useAuth } from "../../components/auth-provider";
import { authenticatedFetch } from "../../lib/api";

type Role = "Training Manager" | "Director" | "Manager" | "Employee";
type CompanyUser = {
  id: number; full_name: string; email: string; role: Role; is_active: boolean;
  employee_id: number | null; department: string | null; manager_id: number | null;
  manager_name: string | null; created_at: string;
};
type Employee = {
  id: number; full_name: string; department: string; linked_user_id: number | null;
  role: Role | null; manager_id: number | null;
};
type Invitation = {
  id: number; full_name: string; email: string; role: Role; employee_id: number | null;
  department: string | null; manager_id: number | null; status: string; created_at: string; expires_at: string;
};
type FormData = {
  full_name: string; email: string; role: Role; employee_id: string;
  department: string; manager_id: string; is_active: boolean;
};

const roles: Role[] = ["Training Manager", "Director", "Manager", "Employee"];
const emptyForm = (): FormData => ({
  full_name: "", email: "", role: "Employee", employee_id: "", department: "",
  manager_id: "", is_active: true,
});

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await authenticatedFetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
    cache: "no-store",
  });
  const result: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = result && typeof result === "object" && "detail" in result
      ? result.detail : null;
    throw new Error(typeof detail === "string" ? detail : `Request failed (${response.status}).`);
  }
  return result as T;
}

function displayDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : date.toLocaleDateString();
}

export default function UserManagementPage() {
  const { activeMembership, user: currentUser } = useAuth();
  const canManage = activeMembership?.role === "Training Manager";
  const [users, setUsers] = useState<CompanyUser[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [search, setSearch] = useState("");
  const [roleFilter, setRoleFilter] = useState("All");
  const [departmentFilter, setDepartmentFilter] = useState("All");
  const [accountFilter, setAccountFilter] = useState("All");
  const [invitationFilter, setInvitationFilter] = useState("All");
  const [mode, setMode] = useState<"invite" | "edit" | null>(null);
  const [selected, setSelected] = useState<CompanyUser | null>(null);
  const [form, setForm] = useState<FormData>(emptyForm);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextUsers, nextInvitations, nextEmployees] = await Promise.all([
        request<CompanyUser[]>("/api/user-management/users"),
        request<Invitation[]>("/api/user-management/invitations"),
        request<Employee[]>("/api/user-management/employees"),
      ]);
      setUsers(nextUsers);
      setInvitations(nextInvitations);
      setEmployees(nextEmployees);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load users.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!canManage) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [canManage, load]);

  const departments = useMemo(() => Array.from(new Set([
    ...users.map((item) => item.department),
    ...invitations.map((item) => item.department),
    ...employees.map((item) => item.department),
  ].filter((value): value is string => Boolean(value)))).sort(), [users, invitations, employees]);
  const searchTerm = search.trim().toLowerCase();
  const invitationStatus = (email: string) => invitations.find(
    (item) => item.email.toLowerCase() === email.toLowerCase() && item.status === "Accepted"
  )?.status ?? "None";
  const matches = (name: string, email: string, role: string, department: string | null,
                   account: string, invitation: string) =>
    (!searchTerm || `${name} ${email}`.toLowerCase().includes(searchTerm)) &&
    (roleFilter === "All" || roleFilter === role) &&
    (departmentFilter === "All" || departmentFilter === department) &&
    (accountFilter === "All" || accountFilter === account) &&
    (invitationFilter === "All" || invitationFilter === invitation);
  const filteredUsers = users.filter((item) => matches(
    item.full_name, item.email, item.role, item.department,
    item.is_active ? "Active" : "Deactivated", invitationStatus(item.email),
  ));
  const filteredInvitations = invitations.filter((item) => matches(
    item.full_name, item.email, item.role, item.department, "Invited", item.status,
  ));
  const availableEmployees = employees.filter(
    (employee) => employee.linked_user_id === null || employee.linked_user_id === selected?.id
  );
  const managers = employees.filter((employee) =>
    employee.id !== Number(form.employee_id) &&
    (employee.role === "Manager" || employee.role === "Training Manager" || employee.role === "Director")
  );

  function chooseEmployee(id: string) {
    const employee = employees.find((item) => item.id === Number(id));
    setForm((current) => ({
      ...current, employee_id: id,
      department: employee?.department ?? "",
      manager_id: employee?.manager_id ? String(employee.manager_id) : "",
    }));
  }

  function editUser(item: CompanyUser) {
    setSelected(item);
    setForm({
      full_name: item.full_name, email: item.email, role: item.role,
      employee_id: item.employee_id === null ? "" : String(item.employee_id),
      department: item.department ?? "", manager_id: item.manager_id === null ? "" : String(item.manager_id),
      is_active: item.is_active,
    });
    setMode("edit");
    setError("");
    setMessage("");
  }

  function inviteUser() {
    setSelected(null);
    setForm(emptyForm());
    setMode("invite");
    setError("");
    setMessage("");
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setMessage("");
    const employeeId = form.employee_id ? Number(form.employee_id) : null;
    const managerId = form.manager_id ? Number(form.manager_id) : null;
    const payload: Record<string, unknown> = {};
    if (mode === "invite") {
      Object.assign(payload, {
        full_name: form.full_name, email: form.email, role: form.role, employee_id: employeeId,
        department: employeeId === null ? null : form.department,
        manager_id: employeeId === null ? null : managerId,
      });
    } else if (selected) {
      if (form.full_name !== selected.full_name) payload.full_name = form.full_name;
      if (form.email !== selected.email) payload.email = form.email;
      if (form.role !== selected.role) payload.role = form.role;
      if (form.is_active !== selected.is_active) payload.is_active = form.is_active;
      if (employeeId !== selected.employee_id) payload.employee_id = employeeId;
      const reference = employeeId === selected.employee_id ? selected : employees.find((item) => item.id === employeeId);
      if (employeeId !== null && form.department !== (reference?.department ?? "")) payload.department = form.department;
      if (employeeId !== null && managerId !== (reference?.manager_id ?? null)) payload.manager_id = managerId;
      if (!Object.keys(payload).length) {
        setMessage("No changes to save.");
        return;
      }
      if (("role" in payload || "is_active" in payload || "employee_id" in payload || "manager_id" in payload) &&
          !window.confirm("Apply these account or reporting changes?")) return;
    }
    setBusy(true);
    try {
      if (mode === "invite") {
        await request("/api/user-management/invitations", { method: "POST", body: JSON.stringify(payload) });
        setMessage("Invitation submitted to the mail server; delivery is not guaranteed.");
      } else if (selected) {
        await request(`/api/user-management/users/${selected.id}`, { method: "PATCH", body: JSON.stringify(payload) });
        setMessage("User updated.");
      }
      setMode(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save.");
    } finally {
      setBusy(false);
    }
  }

  async function invitationAction(item: Invitation, action: "resend" | "revoke") {
    if (!window.confirm(`${action === "resend" ? "Resend" : "Revoke"} this invitation?`)) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await request(`/api/user-management/invitations/${item.id}/${action}`, { method: "POST" });
      setMessage(action === "resend" ? "Invitation submitted to the mail server." : "Invitation revoked.");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to update invitation.");
    } finally {
      setBusy(false);
    }
  }

  if (!canManage) return <main className="content"><h1>Access denied</h1><p>Only Training Managers can manage users.</p></main>;
  return (
    <main className="content users-page">
      <header className="page-heading">
        <div><h1>User Management</h1><p>Manage your company accounts and invitations.</p></div>
        <button className="button" onClick={inviteUser}>Invite user</button>
      </header>
      {error && <div className="auth-alert" role="alert">{error}</div>}
      {message && <div role="status">{message}</div>}
      {loading && <p role="status">Loading users…</p>}
      <section className="users-stats" aria-label="User statistics">
        <div><strong>{users.length}</strong><span>Company users</span></div>
        <div><strong>{users.filter((item) => item.is_active).length}</strong><span>Active</span></div>
        <div><strong>{invitations.filter((item) => item.status === "Pending").length}</strong><span>Pending invitations</span></div>
        <div><strong>{users.filter((item) => !item.is_active).length}</strong><span>Deactivated</span></div>
      </section>
      <section className="users-filters" aria-label="User filters">
        <label>Search<input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name or email" /></label>
        <label>Role<select value={roleFilter} onChange={(event) => setRoleFilter(event.target.value)}>
          <option>All</option>{roles.map((role) => <option key={role}>{role}</option>)}
        </select></label>
        <label>Department<select value={departmentFilter} onChange={(event) => setDepartmentFilter(event.target.value)}>
          <option>All</option>{departments.map((department) => <option key={department}>{department}</option>)}
        </select></label>
        <label>Account status<select value={accountFilter} onChange={(event) => setAccountFilter(event.target.value)}>
          <option>All</option><option>Active</option><option>Deactivated</option><option>Invited</option>
        </select></label>
        <label>Invitation status<select value={invitationFilter} onChange={(event) => setInvitationFilter(event.target.value)}>
          <option>All</option><option>None</option><option>Pending</option><option>Expired</option><option>Accepted</option><option>Revoked</option>
        </select></label>
      </section>
      {mode && (
        <section className="users-editor" aria-labelledby="user-form-heading">
          <h2 id="user-form-heading">{mode === "invite" ? "Invite user" : "User details"}</h2>
          <p>Employee links are optional. No employee record is created by an invitation.</p>
          <form onSubmit={submit} className="users-form">
            <label>Full name<input required maxLength={150} value={form.full_name}
              onChange={(event) => setForm({ ...form, full_name: event.target.value })} /></label>
            <label>Email<input type="email" required maxLength={255} value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })} /></label>
            <label>Role<select value={form.role} disabled={selected?.id === currentUser?.user_id}
              onChange={(event) => setForm({ ...form, role: event.target.value as Role })}>
              {roles.map((role) => <option key={role}>{role}</option>)}
            </select></label>
            <label>Linked employee<select value={form.employee_id} onChange={(event) => chooseEmployee(event.target.value)}>
              <option value="">Not linked</option>
              {availableEmployees.map((employee) => <option key={employee.id} value={employee.id}>{employee.full_name}</option>)}
            </select></label>
            {form.employee_id && <>
              <label>Department<input required maxLength={100} value={form.department}
                onChange={(event) => setForm({ ...form, department: event.target.value })} /></label>
              <label>Reporting manager<select value={form.manager_id}
                onChange={(event) => setForm({ ...form, manager_id: event.target.value })}>
                <option value="">None</option>
                {managers.map((manager) => <option key={manager.id} value={manager.id}>{manager.full_name}</option>)}
              </select></label>
            </>}
            {mode === "edit" && <label>Account status<select value={form.is_active ? "Active" : "Deactivated"}
              disabled={selected?.id === currentUser?.user_id}
              onChange={(event) => setForm({ ...form, is_active: event.target.value === "Active" })}>
              <option>Active</option><option>Deactivated</option>
            </select></label>}
            <div className="users-actions">
              <button className="button" disabled={busy}>{busy ? "Saving…" : mode === "invite" ? "Send invitation" : "Save changes"}</button>
              <button type="button" onClick={() => setMode(null)} disabled={busy}>Cancel</button>
            </div>
          </form>
        </section>
      )}
      <section>
        <h2>Company users</h2>
        <div className="users-table-wrap"><table className="users-table">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Department</th><th>Manager</th>
            <th>Account</th><th>Invitation</th><th>Added</th><th>Actions</th></tr></thead>
          <tbody>{filteredUsers.map((item) => <tr key={item.id}>
            <td>{item.full_name}</td><td>{item.email}</td><td>{item.role}</td><td>{item.department ?? "—"}</td>
            <td>{item.manager_name ?? "—"}</td><td>{item.is_active ? "Active" : "Deactivated"}</td>
            <td>{invitationStatus(item.email)}</td><td>{displayDate(item.created_at)}</td>
            <td><button onClick={() => editUser(item)}>View / edit</button></td>
          </tr>)}</tbody>
        </table></div>
        {!loading && !filteredUsers.length && <p>No users match these filters.</p>}
      </section>
      <section>
        <h2>Invitations</h2>
        <div className="users-table-wrap"><table className="users-table">
          <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Department</th><th>Manager</th><th>Status</th><th>Added</th><th>Actions</th></tr></thead>
          <tbody>{filteredInvitations.map((item) => <tr key={item.id}>
            <td>{item.full_name}</td><td>{item.email}</td><td>{item.role}</td><td>{item.department ?? "—"}</td>
            <td>{employees.find((employee) => employee.id === item.manager_id)?.full_name ?? "—"}</td>
            <td>{item.status}</td><td>{displayDate(item.created_at)}</td>
            <td>{(item.status === "Pending" || item.status === "Expired") && <>
              <button disabled={busy} onClick={() => void invitationAction(item, "resend")}>Resend</button>{" "}
              <button disabled={busy} onClick={() => void invitationAction(item, "revoke")}>Revoke</button>
            </>}</td>
          </tr>)}</tbody>
        </table></div>
        {!loading && !filteredInvitations.length && <p>No invitations match these filters.</p>}
      </section>
    </main>
  );
}
