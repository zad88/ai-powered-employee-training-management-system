import { randomBytes } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";

const ACCESS_COOKIE = "tf_access_token";
const CSRF_COOKIE = "tf_csrf_token";

function trustedOrigin(request: NextRequest): boolean {
  const origin = request.headers.get("origin");
  const configuredOrigin = process.env.FRONTEND_ORIGIN;
  const expectedOrigin =
    configuredOrigin ??
    (process.env.NODE_ENV === "production" ? null : request.nextUrl.origin);
  return Boolean(origin && expectedOrigin && origin === expectedOrigin);
}

export async function POST(request: NextRequest) {
  if (!trustedOrigin(request)) {
    return NextResponse.json({ detail: "Request origin is not allowed." }, { status: 403 });
  }

  const body: unknown = await request.json().catch(() => null);
  if (
    typeof body !== "object" ||
    body === null ||
    !("email" in body) ||
    !("password" in body) ||
    typeof body.email !== "string" ||
    typeof body.password !== "string"
  ) {
    return NextResponse.json({ detail: "Email and password are required." }, { status: 422 });
  }

  const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
  const form = new URLSearchParams({
    username: body.email,
    password: body.password,
  });
  const loginResponse = await fetch(new URL("/auth/login", backend), {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form,
    cache: "no-store",
  });
  const loginBody: unknown = await loginResponse.json().catch(() => null);
  if (
    !loginResponse.ok ||
    typeof loginBody !== "object" ||
    loginBody === null ||
    !("access_token" in loginBody) ||
    typeof loginBody.access_token !== "string"
  ) {
    const detail =
      typeof loginBody === "object" && loginBody !== null && "detail" in loginBody
        ? loginBody.detail
        : "Login failed.";
    return NextResponse.json({ detail }, { status: loginResponse.status || 502 });
  }

  const accessToken = loginBody.access_token;
  const profileResponse = await fetch(new URL("/auth/me", backend), {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  });
  if (!profileResponse.ok) {
    return NextResponse.json(
      { detail: `Profile lookup failed (${profileResponse.status}).` },
      { status: 502 },
    );
  }

  const response = NextResponse.json({ user: await profileResponse.json() });
  const secure = process.env.NODE_ENV === "production";
  response.cookies.set(ACCESS_COOKIE, accessToken, {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60,
  });
  response.cookies.set(CSRF_COOKIE, randomBytes(32).toString("hex"), {
    httpOnly: false,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60,
  });
  return response;
}
