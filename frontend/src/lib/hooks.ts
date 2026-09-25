"use client";

import { useCallback, useEffect, useState } from "react";

export type AsyncState<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
};

/**
 * Fetch-on-mount with loading and error states.
 *
 * Every screen needs the same three states, and getting them wrong is how
 * an app ends up showing a spinner forever after a failed request.
 */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fn()
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : "Request failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);
  return { data, error, loading, reload };
}
