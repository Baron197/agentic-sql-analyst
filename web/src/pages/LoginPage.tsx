import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { ApiError, api } from "../api/client";
import type { AuthOptions } from "../api/types";
import { useAuth } from "../auth";
import { FictionalNotice, Logo } from "../components/Layout";

export function LoginPage() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [options, setOptions] = useState<AuthOptions | null>(null);

  useEffect(() => {
    api
      .authOptions()
      .then(setOptions)
      .catch(() => setOptions(null));
  }, []);

  if (user) return <Navigate to={from} replace />;

  const finish = async (signIn: () => Promise<Awaited<ReturnType<typeof api.login>>>) => {
    setBusy(true);
    setError(null);
    try {
      setUser(await signIn());
      navigate(from, { replace: true });
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "Could not reach the server. Is the API running?",
      );
    } finally {
      setBusy(false);
    }
  };

  const submit = (e: FormEvent) => {
    e.preventDefault();
    void finish(() => api.login(email, password));
  };

  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-[400px]">
        <div className="mb-6 flex justify-center">
          <Logo />
        </div>
        <div className="card rounded-[var(--radius-card-lg)] p-6">
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="mt-1 text-sm text-ink-mute">
            Ask the database in English or Bahasa Indonesia. Every answer shows its SQL and rows.
          </p>
          <form className="mt-5 space-y-4" onSubmit={submit} noValidate>
            <div>
              <label htmlFor="email" className="label">
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="mt-1.5 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-ink placeholder:text-ink-mute focus:border-accent focus:outline-none"
                placeholder="name@demo"
                required
              />
            </div>
            <div>
              <label htmlFor="password" className="label">
                Password
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="mt-1.5 w-full rounded-[10px] border border-line bg-bg px-3 py-2 text-ink focus:border-accent focus:outline-none"
                required
              />
            </div>
            {error && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="btn-primary w-full"
              disabled={busy || !email || !password}
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
          {options && (
            <div className="mt-6 border-t border-line-faint pt-5">
              <h2 className="label">Demo accounts</h2>
              <ul className="mt-2 space-y-2 text-sm">
                {options.demo_users.map((u) => (
                  <li key={u.key} className="flex items-center justify-between gap-3">
                    <span>
                      <span className="font-mono text-ink-soft">{u.email}</span>
                      <span className="block text-xs text-ink-mute">
                        {u.role === "manager"
                          ? "Sees the Jabodetabek region only"
                          : "Sees all regions"}
                      </span>
                    </span>
                    {options.demo_login_enabled && (
                      <button
                        type="button"
                        className="btn-ghost shrink-0 px-3 py-1.5 text-xs"
                        disabled={busy}
                        onClick={() => void finish(() => api.demoLogin(u.key))}
                      >
                        Try as {u.role}
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <FictionalNotice className="mt-5 text-center" />
      </div>
    </div>
  );
}
