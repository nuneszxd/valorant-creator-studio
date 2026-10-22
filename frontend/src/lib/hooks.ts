import { useCallback, useEffect, useRef, useState } from "react";
import type { DependencyList } from "react";

import { useToast } from "../components/Toast";
import { errorMessage } from "./format";

export interface AsyncState<T> {
  data: T | null;
  error: unknown;
  loading: boolean;
  reload: () => void;
  setData: (value: T | null) => void;
}

/** Load data when deps change; `reload()` fetches again. Keeps previous data while reloading. */
export function useAsync<T>(loader: () => Promise<T>, deps: DependencyList): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    loaderRef
      .current()
      .then((value) => {
        if (!cancelled) {
          setData(value);
          setError(null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, version]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return { data, error, loading, reload, setData };
}

/** Wrap an async action: tracks `busy`, shows a toast on success/failure. */
export function useAction() {
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  async function run<T>(fn: () => Promise<T>, success?: string): Promise<T | undefined> {
    setBusy(true);
    try {
      const value = await fn();
      if (success) toast(success, "ok");
      return value;
    } catch (err) {
      toast(errorMessage(err), "error");
      return undefined;
    } finally {
      setBusy(false);
    }
  }

  return { run, busy };
}

/** Re-run `callback` on an interval while `enabled`. */
export function useInterval(callback: () => void, ms: number, enabled = true) {
  const saved = useRef(callback);
  saved.current = callback;
  useEffect(() => {
    if (!enabled) return undefined;
    const id = window.setInterval(() => saved.current(), ms);
    return () => window.clearInterval(id);
  }, [ms, enabled]);
}
