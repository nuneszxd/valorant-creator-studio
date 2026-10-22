"""Clip candidates: review (watch, adjust, approve/reject, tag type, mark outcome)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import Field

from ..analysis.moment_types import MOMENT_TYPES
from ..errors import InvalidInput
from ..models import Strict
from ..utils import loads
from .deps import Ctx

router = APIRouter(prefix="/api/candidates", tags=["candidatos"])

STATUS_LABELS = {"pending": "pendente", "approved": "aprovado", "rejected": "rejeitado"}
OUTCOME_LABELS = {"good": "bom", "bad": "ruim"}
MIN_CLIP_S = 3.0
MAX_CLIP_S = 600.0


class CandidatePatch(Strict):
    title: str | None = Field(None, min_length=1, max_length=120)
    start_s: float | None = Field(None, ge=0)
    end_s: float | None = Field(None, ge=0)
    moment_type: str | None = None
    status: Literal["pending", "approved", "rejected"] | None = None
    outcome: Literal["good", "bad"] | None = None
    tags: list[str] | None = Field(None, max_length=10)


class CandidateCreate(Strict):
    recording_id: int
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    title: str = Field("Corte manual", min_length=1, max_length=120)
    moment_type: str = "outro"


def validate_range(recording: dict[str, Any], start: float, end: float) -> None:
    if end - start < MIN_CLIP_S:
        raise InvalidInput(f"O corte precisa ter pelo menos {MIN_CLIP_S:.0f} segundos.")
    if end - start > MAX_CLIP_S:
        raise InvalidInput(f"O corte pode ter no máximo {MAX_CLIP_S / 60:.0f} minutos.")
    duration = recording.get("duration_s")
    if duration and end > duration + 0.5:
        raise InvalidInput(f"O fim do corte passa da duração da gravação ({duration:.0f} s).")


def validate_type(moment_type: str) -> None:
    if moment_type not in MOMENT_TYPES:
        raise InvalidInput(f"Tipo de momento desconhecido. Use: {', '.join(MOMENT_TYPES)}.")


def present(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for name in ("reasons", "tags"):
        if isinstance(out.get(name), str):
            out[name] = loads(out[name])
    out["duration_s"] = round(out["end_s"] - out["start_s"], 2)
    out["status_label"] = STATUS_LABELS.get(out["status"], out["status"])
    out["outcome_label"] = OUTCOME_LABELS.get(out.get("outcome") or "", None)
    out["type_label"] = MOMENT_TYPES.get(out["moment_type"], out["moment_type"])
    out["manual"] = bool(out.get("manual"))
    return out


@router.get("")
def list_candidates(
    c: Ctx,
    recording_id: int | None = None,
    status: str | None = None,
    type: str | None = None,
    outcome: str | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    map: str | None = None,
    agent: str | None = None,
    q: str | None = None,
    sort: Literal["score", "time", "recent"] = "score",
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if recording_id is not None:
        clauses.append("k.recording_id = ?")
        params.append(recording_id)
    for column, value in (("status", status), ("moment_type", type), ("outcome", outcome)):
        if value:
            clauses.append(f"k.{column} = ?")
            params.append(value)
    if min_score is not None:
        clauses.append("k.score >= ?")
        params.append(min_score)
    for column, value in (("map", map), ("agent", agent)):
        if value:
            clauses.append(f"r.{column} = ?")
            params.append(value)
    if q:
        clauses.append("(instr(lower(k.title), lower(?)) > 0 OR instr(lower(COALESCE(k.excerpt, '')), lower(?)) > 0)")
        params.extend([q, q])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    order = {"score": "k.score DESC, k.id", "time": "k.start_s ASC, k.id", "recent": "k.id DESC"}[sort]
    rows = c.db.query(
        "SELECT k.*, r.name AS recording_name, r.map AS recording_map, r.agent AS recording_agent, "
        "(SELECT id FROM clips v WHERE v.candidate_id = k.id ORDER BY v.id DESC LIMIT 1) AS clip_id "
        f"FROM candidates k JOIN recordings r ON r.id = k.recording_id {where} ORDER BY {order} LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    return [present(r) for r in rows]


@router.post("", status_code=201)
def create_candidate(body: CandidateCreate, c: Ctx) -> dict:
    """Add a cut by hand (the automatic detection is a helper, not a requirement)."""
    recording = c.repos.recordings.require(body.recording_id)
    validate_type(body.moment_type)
    validate_range(recording, body.start_s, body.end_s)
    row = c.repos.candidates.insert(
        recording_id=body.recording_id, start_s=body.start_s, end_s=body.end_s, title=body.title,
        moment_type=body.moment_type, score=0, confidence="baixa", reasons=[], excerpt="",
        status="pending", manual=1, tags=[],
    )
    return present(row)


@router.get("/{candidate_id}")
def get_candidate(candidate_id: int, c: Ctx) -> dict:
    row = c.repos.candidates.require(candidate_id)
    recording = c.repos.recordings.require(row["recording_id"])
    clips = c.repos.clips.list("candidate_id = ?", (candidate_id,), order_by="id DESC", limit=1)
    segments = c.repos.segments.in_range(row["recording_id"], row["start_s"] - 5, row["end_s"] + 5)
    return {
        **present(row),
        "recording": {k: recording[k] for k in ("id", "name", "duration_s", "map", "agent", "width", "height")},
        "clip_id": clips[0]["id"] if clips else None,
        "transcript": segments,
    }


@router.patch("/{candidate_id}")
def patch_candidate(candidate_id: int, body: CandidatePatch, c: Ctx) -> dict:
    row = c.repos.candidates.require(candidate_id)
    fields = body.model_dump(exclude_unset=True)
    if "moment_type" in fields and fields["moment_type"] is not None:
        validate_type(fields["moment_type"])
    for required in ("title", "moment_type", "status", "start_s", "end_s", "tags"):
        if required in fields and fields[required] is None:
            raise InvalidInput(f"O campo '{required}' não pode ser vazio.")
    if "start_s" in fields or "end_s" in fields:
        recording = c.repos.recordings.require(row["recording_id"])
        validate_range(recording, fields.get("start_s", row["start_s"]), fields.get("end_s", row["end_s"]))
    return present(c.repos.candidates.update(candidate_id, **fields))


@router.delete("/{candidate_id}")
def delete_candidate(candidate_id: int, c: Ctx) -> dict:
    c.repos.candidates.require(candidate_id)
    c.repos.candidates.delete(candidate_id)
    return {"status": "removido"}
