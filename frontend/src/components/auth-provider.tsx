"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname, useRouter } from "next/navigation";
import { setActiveCompanyId } from "../lib/api";

export type Membership = {
  membership_id: number;
  company_id: number;
  employee_id: number | null;
  role: "Training Manager" | "Director" | "Manager" | "Employee";
  is_active: boolean;
};

export type AuthUser = {
  user_id: number;
  full_name: string;
  email: string;
  is_active: boolean;
  memberships: Membership[];
};

type AuthContextValue = {
  user: AuthUser | null;
  activeMembership: Membership | null;
  loading: boolean;
  error: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => Promise<void>;
  selectCompany: (companyId: number) => void;
};

const AuthContext = createContext<AuthContextValue | null>(null);

function responseMessage(body: unknown, fallback: string): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
  }
  return fallback;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [activeMembership, setActiveMembership] = useState<Membership | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const pathname = usePathname();

  const selectCompany = useCallback((companyId: number) => {
    const membership = user?.memberships.find(
      (item) => item.company_id === companyId && item.is_active,
    );
    if (!membership) {
      throw new Error("That company is not an active membership.");
    }
    setActiveMembership(membership);
    setActiveCompanyId(membership.company_id);
    sessionStorage.setItem("active-company-id", String(companyId));
  }, [user]);

  const acceptUser = useCallback((nextUser: AuthUser) => {
    const storedId = Number(sessionStorage.getItem("active-company-id"));
    const selected = nextUser.memberships.find(
      (membership) =>
        membership.is_active && membership.company_id === storedId,
    ) ?? nextUser.memberships.find((membership) => membership.is_active) ?? null;
    setUser(nextUser);
    setActiveMembership(selected);
    setActiveCompanyId(selected?.company_id ?? null);
    if (selected) {
      sessionStorage.setItem("active-company-id", String(selected.company_id));
    }
    setError(null);
  }, []);

  const loadSession = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/auth/me", {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (response.status === 401 || response.status === 403) {
        setUser(null);
        setActiveMembership(null);
        setActiveCompanyId(null);
        return;
      }
      if (!response.ok) {
        throw new Error(`Session lookup failed (${response.status}).`);
      }
      acceptUser(await response.json() as AuthUser);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to verify your session.");
    } finally {
      setLoading(false);
    }
  }, [acceptUser]);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadSession(), 0);
    return () => window.clearTimeout(timer);
  }, [loadSession]);

  useEffect(() => {
    const onExpired = () => {
      setUser(null);
      setActiveMembership(null);
      setActiveCompanyId(null);
      router.replace("/login?expired=1");
    };
    window.addEventListener("auth:expired", onExpired);
    return () => window.removeEventListener("auth:expired", onExpired);
  }, [router]);

  useEffect(() => {
    if (!loading && pathname === "/login" && user) {
      router.replace("/");
    } else if (!loading && pathname !== "/login" && !user) {
      router.replace("/login");
    }
  }, [loading, pathname, router, user]);

  const signIn = useCallback(async (email: string, password: string) => {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ email, password }),
    });
    const body = await response.json().catch(() => null);
    if (!response.ok || !body?.user) {
      throw new Error(responseMessage(body, `Login failed (${response.status}).`));
    }
    acceptUser(body.user as AuthUser);
    router.replace("/");
  }, [acceptUser, router]);

  const signOut = useCallback(async () => {
    const csrf = document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("tf_csrf_token="))
      ?.split("=")[1];
    const response = await fetch("/api/auth/logout", {
      method: "POST",
      headers: csrf ? { "X-CSRF-Token": decodeURIComponent(csrf) } : {},
      credentials: "same-origin",
    });
    if (!response.ok) {
      throw new Error(`Logout failed (${response.status}).`);
    }
    setUser(null);
    setActiveMembership(null);
    setActiveCompanyId(null);
    sessionStorage.removeItem("active-company-id");
    router.replace("/login");
  }, [router]);

  const value = useMemo<AuthContextValue>(() => ({
    user,
    activeMembership,
    loading,
    error,
    signIn,
    signOut,
    selectCompany,
  }), [user, activeMembership, loading, error, signIn, signOut, selectCompany]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider.");
  return context;
}
