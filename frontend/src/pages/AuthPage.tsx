import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Button, ErrorNote } from "../components/ui";
import { useSession } from "../hooks/useSession";
import { ApiError, post } from "../services/api";
import type { TokenResponse } from "../types";

export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const { user, signIn } = useSession();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [fullName, setFullName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isRegister = mode === "register";

  if (user) return <Navigate to={(location.state as { from?: string } | null)?.from ?? "/"} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = isRegister ? { email, full_name: fullName, password } : { email, password };
      signIn(await post<TokenResponse>(isRegister ? "/auth/register" : "/auth/login", body));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-full items-center justify-center bg-ink-950 p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2">
          <ShieldCheck className="h-6 w-6 text-accent" />
          <span className="text-lg font-semibold">VisionGuard <span className="text-accent">AI</span></span>
        </div>
        <form onSubmit={submit} className="card space-y-4 p-6">
          <div>
            <h1 className="text-base">{isRegister ? "Create your account" : "Sign in"}</h1>
            <p className="mt-0.5 text-xs text-text-3">AI-assisted visual inspection. Your images stay private to your account.</p>
          </div>
          {error && <ErrorNote message={error} />}
          {isRegister && (
            <div>
              <label className="label" htmlFor="full-name">Full name</label>
              <input id="full-name" className="field" required maxLength={120} autoComplete="name" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>
          )}
          <div>
            <label className="label" htmlFor="email">E-mail</label>
            <input id="email" className="field" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} />
          </div>
          <div>
            <label className="label" htmlFor="password">Password</label>
            <input id="password" className="field" type="password" required minLength={isRegister ? 10 : 1} maxLength={128}
              autoComplete={isRegister ? "new-password" : "current-password"} value={password} onChange={(e) => setPassword(e.target.value)} />
            {isRegister && <p className="mt-1 text-xs text-text-3">At least 10 characters.</p>}
          </div>
          <Button type="submit" variant="primary" className="w-full" busy={busy}>{isRegister ? "Create account" : "Sign in"}</Button>
          <p className="text-center text-xs text-text-3">
            {isRegister ? "Already registered? " : "New to VisionGuard AI? "}
            <Link className="text-accent hover:underline" to={isRegister ? "/login" : "/register"}>{isRegister ? "Sign in" : "Create an account"}</Link>
          </p>
        </form>
        <p className="mt-4 text-center text-xs text-text-3">Findings require human verification. Not certified for safety-critical, medical, structural or regulatory inspections.</p>
      </div>
    </div>
  );
}
