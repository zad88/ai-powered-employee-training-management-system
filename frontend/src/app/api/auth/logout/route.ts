import { timingSafeEqual } from "node:crypto";
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

function validCsrf(request: NextRequest): boolean {
  const cookie = request.cookies.get(CSRF_COOKIE)?.value;
  const header = request.headers.get("X-CSRF-Token");
  if (!cookie || !header) return false;
  const left = Buffer.from(cookie);
  const right = Buffer.from(header);
  return left.length === right.length && timingSafeEqual(left, right);
}

export async function POST(request: NextRequest) {
  if (!trustedOrigin(request) || !validCsrf(request)) {
    return NextResponse.json({ detail: "Invalid logout request." }, { status: 403 });
  }

  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  if (accessToken) {
    const backend = process.env.BACKEND_URL ?? "http://127.0.0.1:8000";
    let logoutResponse: Response;
    try {
      logoutResponse = await fetch(new URL("/auth/logout", backend), {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store",
      });
    } catch {
      return NextResponse.json(
        { detail: "Logout could not reach the authentication service. Please retry." },
        { status: 502 },
      );
    }

    if (!logoutResponse.ok && logoutResponse.status !== 401) {
      return NextResponse.json(
        { detail: "Logout could not be completed. Please retry." },
        { status: 502 },
      );
    }
  }

  const response = NextResponse.json({ message: "Logged out." });
  const secure = process.env.NODE_ENV === "production";
  response.cookies.set(ACCESS_COOKIE, "", {
    httpOnly: true,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  response.cookies.set(CSRF_COOKIE, "", {
    httpOnly: false,
    secure,
    sameSite: "lax",
    path: "/",
    maxAge: 0,
  });
  return response;
}
