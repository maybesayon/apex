"use client";

/**
 * Theme and session providers.
 *
 * Theme resolution order: the user's saved server-side preference, then
 * localStorage, then the OS setting. The blocking script in layout.tsx
 * applies the localStorage/OS answer before first paint; this provider
 * reconciles it with the server once the session loads.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";
import { ApiError, api, type User } from "@/lib/api";

export type Theme = "light" | "dark";

// ── Theme ─────────────────────────────────────────────────────────────────────

type ThemeCtx = { theme: Theme; setTheme: (t: Theme) => void; toggle: () => void };
const ThemeContext = createContext<ThemeCtx | null>(null);

export const THEME_STORAGE_KEY = "apex-theme";

function applyTheme(theme: Theme) {
  const root = document.documentElement;
  // Enable colour transitions only for the duration of the switch, so the
  // change cross-fades without making every later interaction feel laggy.
  root.classList.add("theme-transition");
  root.setAttribute("data-theme", theme);
  root.style.colorScheme = theme;
  window.setTimeout(() => root.classList.remove("theme-transition"), 360);
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");

  useEffect(() => {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY) as Theme | null;
    const initial =
      stored ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light");
    setThemeState(initial);
    document.documentElement.setAttribute("data-theme", initial);
    document.documentElement.style.colorScheme = initial;
  }, []);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    applyTheme(next);
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* private browsing; the in-memory value still works for this session */
    }
    // Persist server-side too, so the choice follows the account to another
    // device. A failure here is not worth interrupting the user for.
    void api.saveSettings(next).catch(() => {});
  }, []);

  const toggle = useCallback(
    () => setTheme(theme === "dark" ? "light" : "dark"),
    [theme, setTheme],
  );

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggle }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme must be used inside ThemeProvider");
  return ctx;
}

// ── Session ───────────────────────────────────────────────────────────────────

type SessionCtx = {
  user: User | null;
  loading: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signUp: (username: string, password: string, email?: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<SessionCtx | null>(null);

export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // On mount, ask the server who we are. The cookie is httpOnly, so this is
  // the only way to know — the client cannot read the session itself.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch (err) {
        if (err instanceof ApiError && !err.isUnauthorized) {
          console.error("Session check failed", err);
        }
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const adopt = useCallback(async () => {
    const me = await api.me();
    setUser(me);
    // Pull the saved theme so a returning user sees their own choice.
    try {
      const s = await api.settings();
      const next = s.theme as Theme;
      document.documentElement.setAttribute("data-theme", next);
      document.documentElement.style.colorScheme = next;
      window.localStorage.setItem(THEME_STORAGE_KEY, next);
    } catch {
      /* theme is a preference, not a blocker */
    }
  }, []);

  const signIn = useCallback(
    async (username: string, password: string) => {
      await api.login(username, password);
      await adopt();
    },
    [adopt],
  );

  const signUp = useCallback(
    async (username: string, password: string, email?: string) => {
      await api.register(username, password, email);
      await adopt();
    },
    [adopt],
  );

  const signOut = useCallback(async () => {
    try {
      await api.logout();
    } finally {
      setUser(null);
    }
  }, []);

  return (
    <SessionContext.Provider value={{ user, loading, signIn, signUp, signOut }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession() {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside SessionProvider");
  return ctx;
}
