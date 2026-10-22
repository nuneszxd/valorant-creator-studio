import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api/client";
import type { JobsSummary } from "../api/types";

interface JobsValue {
  summary: JobsSummary | null;
  /** Increments every time a job that was active has finished: pages reload their data on change. */
  tick: number;
  refresh: () => Promise<void>;
}

const JobsContext = createContext<JobsValue>({ summary: null, tick: 0, refresh: async () => undefined });

export function useJobs(): JobsValue {
  return useContext(JobsContext);
}

export function JobsProvider({ children }: { children: ReactNode }) {
  const [summary, setSummary] = useState<JobsSummary | null>(null);
  const [tick, setTick] = useState(0);
  const previous = useRef<Set<number>>(new Set());

  const refresh = useCallback(async () => {
    try {
      const next = await api.get<JobsSummary>("/api/jobs/summary");
      const ids = new Set(next.active.map((job) => job.id));
      let finished = false;
      previous.current.forEach((id) => {
        if (!ids.has(id)) finished = true;
      });
      previous.current = ids;
      setSummary(next);
      if (finished) setTick((t) => t + 1);
    } catch {
      // The API may be restarting; the next poll will retry.
    }
  }, []);

  const activeCount = summary ? summary.active.length : 0;

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), activeCount > 0 ? 1500 : 5000);
    return () => window.clearInterval(id);
  }, [refresh, activeCount]);

  const value = useMemo(() => ({ summary, tick, refresh }), [summary, tick, refresh]);
  return <JobsContext.Provider value={value}>{children}</JobsContext.Provider>;
}
