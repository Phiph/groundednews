"use client";
import { useEffect, useState } from "react";

/**
 * Fetch data whenever `key` changes. Previous data stays available while the next
 * request is in flight, so lists don't flash empty when filters change.
 */
export function useApi<T>(key: string, fetcher: () => Promise<T>) {
  const [state, setState] = useState<{ key?: string; data?: T; error?: string }>({});

  useEffect(() => {
    let cancelled = false;
    fetcher().then(
      (data) => !cancelled && setState({ key, data }),
      (e: unknown) =>
        !cancelled &&
        setState((prev) => ({
          ...prev,
          key,
          error: e instanceof Error ? e.message : "Failed to load. Is the backend running?",
        }))
    );
    return () => {
      cancelled = true;
    };
    // `key` encodes everything the fetcher depends on
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { data: state.data, error: state.key === key ? state.error : undefined, loading: state.key !== key };
}
