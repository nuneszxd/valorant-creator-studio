"""Job (task) endpoints: list, inspect, cancel."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from ..errors import InvalidInput
from ..jobs.manager import FINISHED_STATES, STATE_LABELS
from .deps import Ctx

router = APIRouter(prefix="/api/jobs", tags=["tarefas"])


def present(job: dict[str, Any]) -> dict[str, Any]:
    out = dict(job)
    out["state_label"] = STATE_LABELS.get(out["state"], out["state"])
    out["cancel_requested"] = bool(out.get("cancel_requested"))
    return out


@router.get("")
def list_jobs(
    c: Ctx,
    state: str | None = None,
    kind: str | None = None,
    recording_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if state:
        states = [s.strip() for s in state.split(",") if s.strip()]
        if any(s not in STATE_LABELS for s in states):
            raise InvalidInput(f"Estado inválido. Use: {', '.join(STATE_LABELS)}.")
        clauses.append("state IN (" + ", ".join("?" for _ in states) + ")")
        params.extend(states)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if recording_id is not None:
        clauses.append("recording_id = ?")
        params.append(recording_id)
    rows = c.repos.jobs.list(" AND ".join(clauses), params, order_by="id DESC", limit=limit)
    return [present(r) for r in rows]


@router.get("/summary")
def summary(c: Ctx) -> dict:
    counts = {state: c.repos.jobs.count("state = ?", (state,)) for state in STATE_LABELS}
    active = c.repos.jobs.list("state IN ('queued', 'running')", order_by="id ASC", limit=20)
    return {"counts": counts, "active": [present(j) for j in active], "labels": STATE_LABELS}


@router.post("/clear-finished")
def clear_finished(c: Ctx) -> dict:
    """Remove finished jobs from the history (does not touch any media file)."""
    placeholders = ", ".join("?" for _ in FINISHED_STATES)
    c.db.execute(f"DELETE FROM jobs WHERE state IN ({placeholders})", FINISHED_STATES)
    return {"status": "ok"}


@router.get("/{job_id}")
def get_job(job_id: int, c: Ctx) -> dict:
    return present(c.repos.jobs.require(job_id))


@router.post("/{job_id}/cancel")
def cancel_job(job_id: int, c: Ctx) -> dict:
    return present(c.jobs.cancel(job_id))
