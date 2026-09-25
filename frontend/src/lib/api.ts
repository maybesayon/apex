/**
 * Typed API client.
 *
 * Types in `api-types.ts` are generated from the FastAPI OpenAPI schema
 * (`npm run gen:api`), so renaming a field on the backend becomes a compile
 * error here rather than `undefined` at runtime.
 *
 * Requests go to the SAME ORIGIN via the /api rewrite in next.config.ts.
 * That is deliberate: the session cookies are httpOnly and SameSite=Lax, and
 * Lax cookies are not sent on cross-origin requests. Proxying keeps the
 * browser seeing one origin, so the stricter cookie policy keeps working and
 * no CORS credentials dance is needed.
 */

import type { components } from "./api-types";

type S = components["schemas"];

export type Session = S["SessionResponse"];
export type User = S["UserResponse"];
export type Quote = S["Quote"];
export type SearchResult = S["SearchResult"];
export type Bar = S["Bar"];
export type HistoryResponse = S["HistoryResponse"];
export type Profile = S["Profile"];
export type Rating = S["Rating"];
export type PortfolioResponse = S["PortfolioResponse"];
export type PositionValued = S["PositionValued"];
export type WatchlistItem = S["WatchlistItem"];
export type JournalEntry = S["JournalEntry"];
export type JournalStats = S["JournalStats"];
export type JobResponse = S["JobResponse"];
export type Settings = S["Settings"];

export const API_BASE = "/api";
const CSRF_COOKIE = "apex_csrf";
const CSRF_HEADER = "X-CSRF-Token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
  /** The session expired and a refresh should be attempted. */
  get isExpired() {
    return this.status === 401 && this.code === "token_expired";
  }
  get isUnauthorized() {
    return this.status === 401;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const hit = document.cookie
    .split("; ")
    .find((row) => row.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.split("=").slice(1).join("=")) : null;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Internal: prevents an infinite refresh loop. */
  _retried?: boolean;
};

async function request<T>(path: string, opts: RequestOptions = {}): Promise<T> {
  const method = opts.method ?? "GET";
  const headers: Record<string, string> = {};

  if (opts.body !== undefined) headers["Content-Type"] = "application/json";

  // The CSRF cookie is readable by design; echoing it in a header is what
  // proves the request did not come from another origin.
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = readCookie(CSRF_COOKIE);
    if (csrf) headers[CSRF_HEADER] = csrf;
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method,
    headers,
    credentials: "include",
    body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
    signal: opts.signal,
  });

  if (res.status === 204) return undefined as T;

  if (!res.ok) {
    const code = res.headers.get("X-Auth-Error") ?? undefined;

    // A merely expired access token is recoverable: rotate it once and
    // replay. Anything else is a real failure.
    if (res.status === 401 && code === "token_expired" && !opts._retried) {
      const refreshed = await fetch(`${API_BASE}/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (refreshed.ok) {
        return request<T>(path, { ...opts, _retried: true });
      }
    }

    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
      else if (Array.isArray(body?.detail) && body.detail[0]?.msg)
        detail = body.detail[0].msg;
    } catch {
      /* non-JSON error body; keep the generic message */
    }
    throw new ApiError(res.status, detail, code);
  }

  return (await res.json()) as T;
}

export const api = {
  // Auth
  register: (username: string, password: string, email?: string) =>
    request<Session>("/auth/register", {
      method: "POST",
      body: { username, password, email: email || null },
    }),
  login: (username: string, password: string) =>
    request<Session>("/auth/login", {
      method: "POST",
      body: { username, password },
    }),
  logout: () => request<void>("/auth/logout", { method: "POST" }),
  me: () => request<User>("/auth/me"),

  // Market
  search: (q: string, limit = 12) =>
    request<SearchResult[]>(
      `/search?q=${encodeURIComponent(q)}&limit=${limit}`,
    ),
  quotes: (symbols: string[]) =>
    request<Quote[]>(`/quotes?symbols=${encodeURIComponent(symbols.join(","))}`),
  quote: (symbol: string) => request<Quote>(`/stocks/${symbol}/quote`),
  history: (symbol: string, period = "1y") =>
    request<HistoryResponse>(`/stocks/${symbol}/history?period=${period}`),
  profile: (symbol: string) => request<Profile>(`/stocks/${symbol}/profile`),
  rating: (symbol: string) => request<Rating | null>(`/stocks/${symbol}/rating`),

  // Analysis — loosely typed because the shape is owned by the Python
  // engine and pinned by contract tests, not by this file.
  analysis: (symbol: string, period = "1y") =>
    request<Record<string, unknown>>(
      `/stocks/${symbol}/analysis?period=${period}`,
    ),
  opportunity: (symbol: string) =>
    request<Record<string, unknown>>(`/stocks/${symbol}/opportunity`),
  forecast: (symbol: string) =>
    request<Record<string, unknown>>(`/stocks/${symbol}/forecast`),
  backtest: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>("/backtest", { method: "POST", body }),

  // User data
  portfolio: () => request<PortfolioResponse>("/portfolio"),
  savePosition: (symbol: string, shares: number, avg_cost: number) =>
    request<void>("/portfolio/positions", {
      method: "PUT",
      body: { symbol, shares, avg_cost },
    }),
  deletePosition: (symbol: string) =>
    request<void>(`/portfolio/positions/${symbol}`, { method: "DELETE" }),

  watchlist: () => request<WatchlistItem[]>("/watchlist"),
  addToWatchlist: (symbol: string) =>
    request<void>("/watchlist", { method: "POST", body: { symbol } }),
  removeFromWatchlist: (symbol: string) =>
    request<void>(`/watchlist/${symbol}`, { method: "DELETE" }),

  journal: () => request<JournalEntry[]>("/journal"),
  journalStats: () => request<JournalStats>("/journal/stats"),

  settings: () => request<Settings>("/settings"),
  saveSettings: (theme: "light" | "dark") =>
    request<Settings>("/settings", { method: "PUT", body: { theme } }),

  // Jobs
  startScan: (scope: "universe" | "broad", min_score = 55) =>
    request<JobResponse>("/jobs/scan", {
      method: "POST",
      body: { scope, min_score },
    }),
  job: (id: string) => request<JobResponse>(`/jobs/${id}`),
  jobs: () => request<JobResponse[]>("/jobs"),
  cancelJob: (id: string) =>
    request<JobResponse>(`/jobs/${id}`, { method: "DELETE" }),
};
