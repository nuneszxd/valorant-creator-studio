import { api } from "../api/client";
import type { Job } from "../api/types";
import { useAction } from "../lib/hooks";
import { fmtDate } from "../lib/format";
import { useJobs } from "./JobsContext";
import { Badge, Button } from "./ui";
import type { Tone } from "./ui";

const TONES: Record<string, Tone> = {
  queued: "neutral",
  running: "info",
  succeeded: "ok",
  failed: "danger",
  cancelled: "warn",
};

/**
 * Progress bar. `value === null` means the task has no real progress information:
 * it is drawn as an indeterminate bar and no percentage is shown (nothing is simulated).
 */
export function ProgressBar({ value, label }: { value: number | null; label?: string | null }) {
  const determinate = value !== null && value !== undefined;
  const percent = determinate ? Math.round(Math.min(Math.max(value, 0), 1) * 100) : null;
  return (
    <div className="progress-wrap">
      <div
        className={`progress ${determinate ? "" : "progress-indeterminate"}`}
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent ?? undefined}
        aria-label={label ?? "Progresso"}
      >
        <div className="progress-bar" style={determinate ? { width: `${percent}%` } : undefined} />
      </div>
      <div className="progress-text small muted">
        {label}
        {determinate ? ` — ${percent}%` : label ? " — sem estimativa de progresso" : "Sem estimativa de progresso"}
      </div>
    </div>
  );
}

export function JobStatus({ job, compact = false }: { job: Job; compact?: boolean }) {
  const { refresh } = useJobs();
  const { run, busy } = useAction();
  const active = job.state === "queued" || job.state === "running";

  async function cancel() {
    await run(() => api.post(`/api/jobs/${job.id}/cancel`), "Cancelamento solicitado.");
    void refresh();
  }

  return (
    <div className={`job ${compact ? "job-compact" : ""}`}>
      <div className="job-head">
        <strong className="job-label">{job.label}</strong>
        <Badge tone={TONES[job.state] ?? "neutral"}>
          {job.cancel_requested && active ? "cancelando…" : job.state_label}
        </Badge>
      </div>
      {job.state === "running" && <ProgressBar value={job.progress} label={job.progress_label} />}
      {job.state === "queued" && <div className="muted small">Na fila: começa quando a tarefa anterior terminar.</div>}
      {job.message && <div className="small muted">{job.message}</div>}
      {job.state === "failed" && job.error && <div className="notice notice-danger small">{job.error}</div>}
      {job.state === "cancelled" && <div className="muted small">Cancelada pelo usuário.</div>}
      {!compact && job.finished_at && <div className="muted small">Finalizada em {fmtDate(job.finished_at)}</div>}
      {active && !job.cancel_requested && (
        <Button variant="ghost" onClick={cancel} busy={busy}>
          Cancelar
        </Button>
      )}
    </div>
  );
}
