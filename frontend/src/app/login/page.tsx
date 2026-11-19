"use client";

import { FormEvent, Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "../../components/auth-provider";

export default function LoginPage() {
  return (
    <Suspense fallback={<main className="auth-loading">Loading sign in…</main>}>
      <LoginForm />
    </Suspense>
  );
}

function LoginForm() {
  const { signIn, loading, error } = useAuth();
  const searchParams = useSearchParams();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setSubmitting(true);
    try {
      await signIn(email, password);
    } catch (reason) {
      setMessage(reason instanceof Error ? reason.message : "Unable to sign in.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <div className="brand-icon">T</div>
        <p className="eyebrow">TALENTFLOW</p>
        <h1>Sign in</h1>
        <p>Use your company account to access training management.</p>
        {searchParams.get("expired") && (
          <div className="auth-alert">Your session expired. Please sign in again.</div>
        )}
        {(message || error) && (
          <div className="auth-alert" role="alert">{message || error}</div>
        )}
        {loading && <p className="auth-status">Verifying existing session…</p>}
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          autoComplete="username"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        <button className="button auth-submit" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
