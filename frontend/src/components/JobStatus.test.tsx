import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { Job } from "../api/types";
import { JobStatus, ProgressBar } from "./JobStatus";

function job(partial: Partial<Job>): Job {
  return {
    id: 1, kind: "analyze", label: "Analisar partida.mp4", state: "running", state_label: "em andamento", recording_id: 1,
    clip_id: null, progress: null, progress_label: null, message: null, error: null, result: null, cancel_requested: false,
    created_at: "2026-01-01T00:00:00+00:00", started_at: null, finished_at: null, ...partial,
  };
}

describe("ProgressBar", () => {
  it("never invents a percentage when progress is unknown", () => {
    render(<ProgressBar value={null} label="Detectando cenas" />);
    expect(screen.getByRole("progressbar")).toHaveClass("progress-indeterminate");
    expect(screen.getByRole("progressbar")).not.toHaveAttribute("aria-valuenow");
    expect(screen.queryByText(/%/)).toBeNull();
    expect(screen.getByText(/sem estimativa de progresso/)).toBeInTheDocument();
  });

  it("shows the real percentage when known", () => {
    render(<ProgressBar value={0.42} label="Renderizando" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "42");
    expect(screen.getByText(/42%/)).toBeInTheDocument();
  });
});

describe("JobStatus", () => {
  it("shows state label and cancel button for a running job", () => {
    render(<JobStatus job={job({ progress: 0.5, progress_label: "Etapa 1/2" })} />);
    expect(screen.getByText("em andamento")).toBeInTheDocument();
    expect(screen.getByText(/50%/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeInTheDocument();
  });

  it("explains queued jobs and hides percentages", () => {
    render(<JobStatus job={job({ state: "queued", state_label: "aguardando" })} />);
    expect(screen.getByText("aguardando")).toBeInTheDocument();
    expect(screen.getByText(/Na fila/)).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows the error of a failed job without cancel", () => {
    render(<JobStatus job={job({ state: "failed", state_label: "com erro", error: "FFmpeg não encontrado." })} />);
    expect(screen.getByText("com erro")).toBeInTheDocument();
    expect(screen.getByText("FFmpeg não encontrado.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull();
  });

  it("marks cancellation in progress", () => {
    render(<JobStatus job={job({ cancel_requested: true })} />);
    expect(screen.getByText("cancelando…")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cancelar" })).toBeNull();
  });
});
