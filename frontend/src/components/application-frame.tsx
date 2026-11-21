"use client";

import { usePathname } from "next/navigation";
import { useAuth } from "./auth-provider";
import { WorkspaceSidebar } from "./workspace-sidebar";

export function ApplicationFrame({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, loading, error } = useAuth();

  if (pathname === "/login" || pathname === "/accept-invitation") return children;
  if (loading) {
    return <main className="auth-loading">Checking your session…</main>;
  }
  if (!user) {
    return <main className="auth-loading">{error ?? "Redirecting to sign in…"}</main>;
  }
  return (
    <div className="workspace-frame">
      <WorkspaceSidebar />
      <div className="workspace-content">{children}</div>
    </div>
  );
}
