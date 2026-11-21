"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";

export default function AcceptInvitationPage() {
  const [token, setToken] = useState("");
  const [state, setState] = useState<"checking" | "ready" | "complete" | "error">("checking");
  const [message, setMessage] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [saving, setSaving] = useState(false);
  const tokenRef = useRef("");

  useEffect(() => {
    const secret = tokenRef.current || new URLSearchParams(window.location.hash.slice(1)).get("token") || "";
    tokenRef.current = secret;
    window.history.replaceState(null, "", window.location.pathname);
    const controller = new AbortController();
    async function verify() {
      try {
        if (!secret) throw new Error("This invitation link is missing its token.");
        const response = await fetch("/api/invitations/verify", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token: secret }), signal: controller.signal, credentials: "omit",
        });
        if (!response.ok) throw new Error("This invitation is invalid, expired, or no longer available.");
        if (!controller.signal.aborted) {
          setToken(secret);
          setState("ready");
        }
      } catch (reason) {
        if (!controller.signal.aborted) {
          setMessage(reason instanceof Error ? reason.message : "Unable to verify invitation.");
          setState("error");
        }
      }
    }
    void verify();
    return () => controller.abort();
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (password !== confirmation) {
      setMessage("Passwords do not match.");
      return;
    }
    if (!password.trim() || password.length < 12) {
      setMessage("Use at least 12 characters for your password.");
      return;
    }
    setSaving(true);
    try {
      const response = await fetch("/api/invitations/accept", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }), credentials: "omit",
      });
      if (!response.ok) throw new Error("This invitation could not be accepted. Request a new invitation.");
      setToken("");
      tokenRef.current = "";
      setPassword("");
      setConfirmation("");
      setState("complete");
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to accept invitation.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="auth-page">
      <div className="auth-card">
        <div className="brand-icon">T</div>
        <h1>Accept invitation</h1>
        {state === "checking" && <p role="status">Verifying invitation…</p>}
        {message && <div className="auth-alert" role="alert">{message}</div>}
        {state === "ready" && (
          <form onSubmit={submit}>
            <p>Create a password with at least 12 characters.</p>
            <label htmlFor="password">Password</label>
            <input id="password" type="password" autoComplete="new-password" minLength={12}
              maxLength={128} required value={password} onChange={(event) => setPassword(event.target.value)} />
            <label htmlFor="confirmation">Confirm password</label>
            <input id="confirmation" type="password" autoComplete="new-password" minLength={12}
              maxLength={128} required value={confirmation} onChange={(event) => setConfirmation(event.target.value)} />
            <button className="button auth-submit" disabled={saving}>
              {saving ? "Creating account…" : "Create account"}
            </button>
          </form>
        )}
        {state === "complete" && <p role="status">Your account is ready. Sign in to continue.</p>}
        {(state === "complete" || state === "error") && <Link href="/login">Go to sign in</Link>}
      </div>
    </main>
  );
}
