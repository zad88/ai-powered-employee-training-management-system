"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "./auth-provider";
import { useState } from "react";

type NavItem = { href: string; label: string };

const navigation: Record<string, NavItem[]> = {
  "Training Manager": [
    { href: "/", label: "Overview" },
    { href: "/imports", label: "Employee Imports" },
    { href: "/employees", label: "Employees" },
    { href: "/skills", label: "Skills Catalogue" },
    { href: "/assessments", label: "Assessments" },
    { href: "/job-requirements", label: "Job Requirements" },
    { href: "/tna", label: "Training Needs" },
  ],
  Director: [
    { href: "/", label: "Overview" },
    { href: "/employees", label: "Employees" },
    { href: "/skills", label: "Skills Catalogue" },
    { href: "/assessments", label: "Assessments & Approvals" },
    { href: "/job-requirements", label: "Job Approvals" },
    { href: "/tna", label: "Training Needs" },
  ],
  Manager: [
    { href: "/", label: "Overview" },
    { href: "/employees", label: "Direct Reports" },
    { href: "/employee-skills", label: "Team Skills" },
    { href: "/assessments", label: "Assessments" },
    { href: "/tna", label: "Team Training Needs" },
  ],
  Employee: [
    { href: "/", label: "Overview" },
    { href: "/employees", label: "My Profile" },
    { href: "/employee-skills", label: "My Skills" },
    { href: "/assessments", label: "My Assessments" },
  ],
};

export function WorkspaceSidebar() {
  const pathname = usePathname();
  const { user, activeMembership, selectCompany, signOut } = useAuth();
  const [logoutError, setLogoutError] = useState("");
  const role = activeMembership?.role ?? "Employee";
  const items = navigation[role] ?? [];
  const activePath = pathname.startsWith("/employees/")
    ? "/employees"
    : pathname;

  return (
    <aside className="sidebar">
      <Link href="/" className="brand">
        <div className="brand-icon">T</div>
        <div><strong>TalentFlow</strong><span>Training Management</span></div>
      </Link>
      <div className="nav-label">WORKSPACE</div>
      {items.map((item: NavItem) => (
        <Link
          href={item.href}
          className={`nav-item${activePath === item.href ? " active" : ""}`}
          key={item.href}
        >
          <span>{item.label}</span>
        </Link>
      ))}
      {user && user.memberships.filter((membership) => membership.is_active).length > 1 && (
        <label className="company-switcher">
          Company
          <select
            value={activeMembership?.company_id ?? ""}
            onChange={(event) => selectCompany(Number(event.target.value))}
          >
            {user.memberships.filter((membership) => membership.is_active).map((membership) => (
              <option key={membership.membership_id} value={membership.company_id}>
                Company {membership.company_id}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="sidebar-bottom">
        <div className="user-avatar">
          {user?.full_name.split(/\s+/).slice(0, 2).map((name) => name[0]).join("")}
        </div>
        <div className="sidebar-user">
          <strong>{user?.full_name}</strong>
          <span>{role}</span>
        </div>
        <button
          className="logout-button"
          onClick={() => {
            setLogoutError("");
            void signOut().catch((reason: unknown) => {
              setLogoutError(reason instanceof Error ? reason.message : "Unable to log out.");
            });
          }}
        >
          Log out
        </button>
      </div>
      {logoutError && <p className="logout-error" role="alert">{logoutError}</p>}
    </aside>
  );
}
