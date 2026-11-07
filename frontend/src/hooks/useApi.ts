import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError, fetchBlob } from "../services/api";

/** Loads data from the API. Stale responses are ignored when the path changes. */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const latest = useRef(path);
  latest.current = path;

  const reload = useCallback(async () => {
    if (!path) {
      setData(null);
      setLoading(false);
      return;
    }
    try {
      const result = await api<T>(path);
      if (latest.current === path) {
        setData(result);
        setError(null);
      }
    } catch (err) {
      if (latest.current === path) setError(err instanceof ApiError ? err.message : "Something went wrong.");
    } finally {
      if (latest.current === path) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    setLoading(path !== null);
    void reload();
  }, [path, reload]);

  return { data, error, loading, reload, setData };
}

/** Protected images need the Authorization header, so they load as blobs. */
export function useAuthedImage(path: string | null): { src: string | null; failed: boolean } {
  const [src, setSrc] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setSrc(null);
    setFailed(false);
    if (!path) return;
    let cancelled = false;
    let url: string | null = null;
    fetchBlob(path)
      .then((blob) => {
        if (cancelled) return;
        url = URL.createObjectURL(blob);
        setSrc(url);
      })
      .catch(() => { if (!cancelled) setFailed(true); });
    return () => {
      cancelled = true;
      if (url) URL.revokeObjectURL(url);
    };
  }, [path]);
  return { src, failed };
}

export function usePolling(callback: () => void, active: boolean, intervalMs = 1500): void {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (!active) return;
    const timer = setInterval(() => saved.current(), intervalMs);
    return () => clearInterval(timer);
  }, [active, intervalMs]);
}
