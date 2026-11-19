"use client";

let activeCompanyId: number | null = null;

const companyScopedPaths = [
  "/api/employees",
  "/api/employee-imports",
  "/api/job-skills",
  "/api/skill-assessments",
  "/api/tna",
  "/api/courses",
  "/api/course-skills",
  "/api/course-sessions",
  "/api/training-plans",
  "/api/plan-courses",
  "/api/enrollments",
  "/api/enrollment-assessments",
  "/api/session-attendance",
  "/api/session-feedback",
];

export function setActiveCompanyId(companyId: number | null) {
  activeCompanyId = companyId;
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const entry = document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(`${name}=`));
  return entry ? decodeURIComponent(entry.slice(name.length + 1)) : null;
}

function getRequestUrl(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.toString();
  return input.url;
}

export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const url = new URL(getRequestUrl(input), window.location.origin);
  const isCompanyScoped = companyScopedPaths.some(
    (path) => url.pathname === path || url.pathname.startsWith(`${path}/`),
  );
  if (isCompanyScoped && activeCompanyId !== null && !url.searchParams.has("company_id")) {
    url.searchParams.set("company_id", String(activeCompanyId));
  }

  const headers = new Headers(
    input instanceof Request ? input.headers : undefined,
  );
  new Headers(init.headers).forEach((value, key) => headers.set(key, value));
  if (activeCompanyId !== null) {
    headers.set("X-Company-ID", String(activeCompanyId));
  }

  const method = (init.method ?? (input instanceof Request ? input.method : "GET"))
    .toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie("tf_csrf_token");
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }

  const response = await fetch(url.toString(), {
    ...init,
    headers,
    credentials: "same-origin",
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event("auth:expired"));
  }
  return response;
}
