"use client";

/**
 * Sign-in / sign-up gate.
 *
 * Everything behind this needs a session. Rendering the form here rather
 * than redirecting to /login keeps the URL the user asked for, so they land
 * where they intended after signing in.
 */

import { motion } from "motion/react";
import { useState } from "react";
import { AppShell, ThemeToggle } from "@/components/app-shell";
import { useSession } from "@/components/providers";
import { Button, Card, Input, Spinner } from "@/components/ui";
import { ApiError } from "@/lib/api";

function Branding() {
  return (
    <div className="mb-7 text-center">
      <h1 className="text-[40px] font-bold tracking-[-0.04em] text-ink">APEX</h1>
      <p className="mt-1 text-[15px] text-muted">Markets, measured honestly.</p>
    </div>
  );
}

function AuthForm() {
  const { signIn, signUp } = useSession();
  const [mode, setMode] = useState<"in" | "up">("in");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      if (mode === "in") await signIn(username.trim(), password);
      else await signUp(username.trim(), password);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Could not reach the server. Is the API running?",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <Card className="p-6">
      <div className="mb-5 flex gap-1 rounded-full bg-surface-2 p-1">
        {(["in", "up"] as const).map((m) => (
          <button
            key={m}
            type="button"
            onClick={() => {
              setMode(m);
              setError(null);
            }}
            className={`relative flex-1 rounded-full px-4 py-2 text-[14px] font-medium transition-colors ${
              mode === m ? "text-ink" : "text-muted hover:text-ink"
            }`}
          >
            {mode === m && (
              <motion.span
                layoutId="auth-tab"
                className="absolute inset-0 rounded-full bg-surface shadow-card"
                transition={{ duration: 0.28, ease: [0.32, 0.72, 0, 1] }}
              />
            )}
            <span className="relative">
              {m === "in" ? "Sign in" : "Create account"}
            </span>
          </button>
        ))}
      </div>

      <form onSubmit={submit} className="flex flex-col gap-4">
        <Input
          label="Username"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          minLength={3}
        />
        <Input
          label="Password"
          name="password"
          type="password"
          autoComplete={mode === "in" ? "current-password" : "new-password"}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />

        {mode === "up" && (
          <p className="-mt-1 text-[12.5px] text-faint">
            At least 8 characters.
          </p>
        )}

        {error && (
          <motion.p
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            role="alert"
            className="rounded-xl bg-down-soft px-3.5 py-2.5 text-[13.5px] text-down"
          >
            {error}
          </motion.p>
        )}

        <Button type="submit" variant="primary" loading={busy} className="w-full">
          {mode === "in" ? "Sign in" : "Create account"}
        </Button>
      </form>

      <p className="mt-5 text-center text-[12px] leading-relaxed text-faint">
        APEX is an analysis tool. It does not place trades and is not
        financial advice.
      </p>
    </Card>
  );
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading } = useSession();

  if (loading) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-bg">
        <Spinner className="size-6 text-muted" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="flex min-h-dvh flex-col bg-bg px-4 py-6">
        <div className="flex justify-end">
          <ThemeToggle compact />
        </div>
        <div className="flex flex-1 items-center justify-center">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.32, 0.72, 0, 1] }}
            className="w-full max-w-[400px]"
          >
            <Branding />
            <AuthForm />
          </motion.div>
        </div>
      </div>
    );
  }

  return <AppShell>{children}</AppShell>;
}
