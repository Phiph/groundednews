"use client";
import useSWR from "swr";

/**
 * Fetch data whenever `key` changes, via SWR: responses are cached and shared by key
 * (e.g. trending tags on the feed and search pages), and refreshed when the tab regains
 * focus. Previous data stays available while the next request is in flight, so lists
 * don't flash empty when filters change.
 */
export function useApi<T>(key: string, fetcher: () => Promise<T>) {
  const { data, error, isLoading } = useSWR<T, unknown>(key, fetcher, { keepPreviousData: true });
  return {
    data,
    error: error ? (error instanceof Error ? error.message : "Failed to load. Is the backend running?") : undefined,
    loading: isLoading,
  };
}
