"""Clips: editor state (cut, layout, subtitles), rendering, preview, and copy suggestions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field, model_validator

from ..analysis.moment_types import MOMENT_TYPES
from ..copywriting.generator import CopyInput, generate_copy, short_quote
from ..errors import Conflict, InvalidInput, NotFound
from ..media.render import plan_for_clip, render_clip, transcribe_clip
from ..media.subtitles import cues_from_segments
from ..media.transcribe import transcription_available
from ..models import RenderConfig, Strict, SubtitleStyle
from ..settings_store import validate_model
from ..streaming import range_file_response
from ..utils import deep_merge
from .candidates import validate_range, validate_type
from .deps import Ctx
from .jobs import present as jobs_present

router = APIRouter(prefix="/api/clips", tags=["cortes"])

STATUS_LABELS = {"draft": "rascunho", "rendering": "renderizando", "ready": "pronto"}


class CueWord(Strict):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(max_length=60)


class Cue(Strict):
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    text: str = Field(min_length=1, max_length=300)
    words: list[CueWord] | None = Field(None, max_length=80)

    @model_validator(mode="after")
    def _ordered(self) -> "Cue":
        if self.end <= self.start:
            raise ValueError("Cada legenda precisa terminar depois de começar.")
        return self


class ClipCreate(Strict):
    candidate_id: int | None = None
    recording_id: int | None = None
    start_s: float | None = Field(None, ge=0)
    end_s: float | None = Field(None, ge=0)
    title: str | None = Field(None, min_length=1, max_length=120)
    moment_type: str | None = None


class ClipPatch(Strict):
    title: str | None = Field(None, min_length=1, max_length=120)
    start_s: float | None = Field(None, ge=0)
    end_s: float | None = Field(None, ge=0)
    moment_type: str | None = None
    map: str | None = Field(None, max_length=40)
    agent: str | None = Field(None, max_length=40)
    facts: dict[str, Any] | None = None
    render_config: dict[str, Any] | None = None
    subtitle_style: dict[str, Any] | None = None
    subtitles: list[Cue] | None = Field(None, max_length=600)


class RenderBody(Strict):
    mode: Literal["final", "preview"] = "final"


class TranscribeBody(Strict):
    allow_model_download: bool = False


def present(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label"] = STATUS_LABELS.get(out["status"], out["status"])
    out["duration_s"] = round(out["end_s"] - out["start_s"], 2)
    out["type_label"] = MOMENT_TYPES.get(out["moment_type"], out["moment_type"])
    out["has_output"] = bool(out.get("output_path") and Path(out["output_path"]).is_file())
    out["has_preview"] = bool(out.get("preview_path") and Path(out["preview_path"]).is_file())
    return out


def _clean_facts(facts: dict[str, Any]) -> dict[str, Any]:
    allowed = {"situation", "result", "round", "note", "rank"}
    out: dict[str, Any] = {}
    for key, value in facts.items():
        if key not in allowed:
            raise InvalidInput(f"Fato desconhecido: {key}. Use: {', '.join(sorted(allowed))}.")
        if value in (None, ""):
            continue
        text = str(value).strip()
        if len(text) > 300:
            raise InvalidInput(f"O fato '{key}' é longo demais (máximo 300 caracteres).")
        out[key] = text
    return out


@router.get("")
def list_clips(
    c: Ctx,
    recording_id: int | None = None,
    status: str | None = None,
    type: str | None = None,
    map: str | None = None,
    agent: str | None = None,
    q: str | None = None,
    min_score: float | None = Query(None, ge=0, le=100),
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if recording_id is not None:
        clauses.append("v.recording_id = ?")
        params.append(recording_id)
    for column, value in (("status", status), ("moment_type", type)):
        if value:
            clauses.append(f"v.{column} = ?")
            params.append(value)
    for column, value in (("map", map), ("agent", agent)):
        if value:
            clauses.append(f"(COALESCE(v.{column}, r.{column}) = ?)")
            params.append(value)
    if min_score is not None:
        clauses.append("COALESCE(k.score, 0) >= ?")
        params.append(min_score)
    if q:
        clauses.append("instr(lower(v.title), lower(?)) > 0")
        params.append(q)
    if date_from:
        clauses.append("v.created_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("v.created_at <= ?")
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = c.db.query(
        "SELECT v.id FROM clips v JOIN recordings r ON r.id = v.recording_id "
        f"LEFT JOIN candidates k ON k.id = v.candidate_id {where} ORDER BY v.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    out = []
    for row in rows:
        clip = present(c.repos.clips.require(row["id"]))
        recording = c.repos.recordings.get(clip["recording_id"]) or {}
        candidate = c.repos.candidates.get(clip["candidate_id"]) if clip.get("candidate_id") else None
        clip["recording_name"] = recording.get("name")
        clip["map"] = clip.get("map") or recording.get("map")
        clip["agent"] = clip.get("agent") or recording.get("agent")
        # Manual cuts have no automatic score: show "no score", never a made-up 0.
        clip["score"] = candidate["score"] if candidate and not candidate.get("manual") else None
        out.append(clip)
    return out


@router.post("", status_code=201)
def create_clip(body: ClipCreate, c: Ctx) -> dict:
    """Create an editable clip from a candidate (approving it) or from a manual time range."""
    settings = c.settings.load()
    if body.candidate_id is not None:
        candidate = c.repos.candidates.require(body.candidate_id)
        existing = c.repos.clips.list("candidate_id = ?", (candidate["id"],), order_by="id DESC", limit=1)
        if existing:
            return present(existing[0])
        recording = c.repos.recordings.require(candidate["recording_id"])
        start, end = candidate["start_s"], candidate["end_s"]
        title, moment_type = candidate["title"], candidate["moment_type"]
        if candidate["status"] != "approved":
            c.repos.candidates.update(candidate["id"], status="approved")
    else:
        if body.recording_id is None or body.start_s is None or body.end_s is None:
            raise InvalidInput("Informe candidate_id ou recording_id com start_s e end_s.")
        recording = c.repos.recordings.require(body.recording_id)
        start, end = body.start_s, body.end_s
        title, moment_type = body.title or "Corte manual", body.moment_type or "outro"
    validate_type(moment_type)
    validate_range(recording, start, end)
    segments = c.repos.segments.in_range(recording["id"], start, end)
    clip = c.repos.clips.insert(
        candidate_id=body.candidate_id, recording_id=recording["id"], title=body.title or title,
        start_s=start, end_s=end, moment_type=moment_type, map=recording.get("map"),
        agent=recording.get("agent"), facts={}, render_config=settings.render.model_dump(),
        subtitle_style=settings.subtitle_style.model_dump(), subtitles=cues_from_segments(segments, start, end),
        status="draft",
    )
    return present(clip)


@router.get("/{clip_id}")
def get_clip(clip_id: int, c: Ctx) -> dict:
    clip = c.repos.clips.require(clip_id)
    recording = c.repos.recordings.require(clip["recording_id"])
    candidate = c.repos.candidates.get(clip["candidate_id"]) if clip.get("candidate_id") else None
    active = c.repos.jobs.list(
        "clip_id = ? AND state IN ('queued', 'running')", (clip_id,), order_by="id DESC", limit=5
    )
    latest = c.repos.jobs.list("clip_id = ?", (clip_id,), order_by="id DESC", limit=1)
    return {
        **present(clip),
        "recording": {k: recording.get(k) for k in ("id", "name", "duration_s", "width", "height", "map", "agent",
                                                    "audio_streams", "video_codec", "audio_codec")},
        "candidate": (
            {**{k: candidate.get(k) for k in ("id", "score", "confidence", "excerpt")}, "manual": bool(candidate.get("manual"))}
            if candidate else None
        ),
        "active_jobs": active,
        # Lets the editor surface a failed transcription/render/preview instead of failing silently.
        "last_job": jobs_present(latest[0]) if latest else None,
    }


@router.patch("/{clip_id}")
def patch_clip(clip_id: int, body: ClipPatch, c: Ctx) -> dict:
    clip = c.repos.clips.require(clip_id)
    raw = body.model_dump(exclude_unset=True)
    settings = c.settings.load()
    fields: dict[str, Any] = {}
    for key in ("title", "start_s", "end_s", "moment_type"):
        if key in raw:
            if raw[key] is None:
                raise InvalidInput(f"O campo '{key}' não pode ser vazio.")
            fields[key] = raw[key]
    for key in ("map", "agent"):
        if key in raw:
            fields[key] = raw[key] or None
    if "moment_type" in fields:
        validate_type(fields["moment_type"])
    if "start_s" in fields or "end_s" in fields:
        recording = c.repos.recordings.require(clip["recording_id"])
        validate_range(recording, fields.get("start_s", clip["start_s"]), fields.get("end_s", clip["end_s"]))
    if raw.get("facts") is not None:
        fields["facts"] = _clean_facts(raw["facts"])
    if raw.get("render_config") is not None:
        base = clip["render_config"] or settings.render.model_dump()
        fields["render_config"] = validate_model(RenderConfig, deep_merge(base, raw["render_config"])).model_dump()
    if raw.get("subtitle_style") is not None:
        base = clip["subtitle_style"] or settings.subtitle_style.model_dump()
        fields["subtitle_style"] = validate_model(SubtitleStyle, deep_merge(base, raw["subtitle_style"])).model_dump()
    if "subtitles" in raw and raw["subtitles"] is not None:
        duration = fields.get("end_s", clip["end_s"]) - fields.get("start_s", clip["start_s"])
        cues = [cue.model_dump() for cue in (body.subtitles or [])]
        if any(cue["end"] > duration + 0.5 for cue in cues):
            raise InvalidInput("Há legendas que terminam depois do fim do corte.")
        fields["subtitles"] = cues
    return present(c.repos.clips.update(clip_id, **fields))


@router.delete("/{clip_id}")
def delete_clip(clip_id: int, c: Ctx) -> dict:
    """Remove the clip from the library. Exported/preview files stay on disk (use Biblioteca > Limpeza)."""
    clip = c.repos.clips.require(clip_id)
    c.repos.clips.delete(clip_id)
    note = f"O vídeo exportado continua em {clip['output_path']}." if clip.get("output_path") else ""
    return {"status": "removido", "note": note}


@router.post("/{clip_id}/subtitles/from-transcript")
def subtitles_from_transcript(clip_id: int, c: Ctx) -> dict:
    clip = c.repos.clips.require(clip_id)
    segments = c.repos.segments.in_range(clip["recording_id"], clip["start_s"], clip["end_s"])
    if not segments:
        raise Conflict("Não há transcrição para este trecho. Use 'Transcrever este corte'.")
    cues = cues_from_segments(segments, clip["start_s"], clip["end_s"])
    return present(c.repos.clips.update(clip_id, subtitles=cues))


@router.post("/{clip_id}/transcribe", status_code=202)
def transcribe(clip_id: int, body: TranscribeBody, c: Ctx) -> dict:
    c.tools.require_ffmpeg()
    clip = c.repos.clips.require(clip_id)
    ready, message = transcription_available(c.settings.load())
    if not ready:
        raise InvalidInput(f"Transcrição indisponível: {message}")
    if c.repos.jobs.count("clip_id = ? AND kind = 'transcribe_clip' AND state IN ('queued', 'running')", (clip_id,)):
        raise Conflict("Já existe uma transcrição deste corte em andamento.")
    return c.jobs.submit(
        "transcribe_clip", f"Transcrever corte: {clip['title']}",
        lambda ctx: transcribe_clip(ctx, c, clip_id, allow_download=body.allow_model_download),
        recording_id=clip["recording_id"], clip_id=clip_id, params=body.model_dump(),
    )


def _check_render(c: Any, clip_id: int, mode: str) -> dict[str, Any]:
    c.tools.require_ffmpeg()
    clip = c.repos.clips.require(clip_id)
    recording = c.repos.recordings.require(clip["recording_id"])
    if not Path(recording["path"]).is_file():
        raise InvalidInput("O arquivo da gravação original não foi encontrado. Importe-o novamente.")
    cfg = RenderConfig.model_validate(clip["render_config"] or c.settings.load().render.model_dump())
    if mode == "final" and cfg.encoder not in c.tools.encoders():
        raise InvalidInput(
            f"O encoder '{cfg.encoder}' não está disponível neste FFmpeg. Escolha libx264 (CPU) ou outro "
            "encoder listado em Configurações."
        )
    return clip


@router.post("/{clip_id}/render", status_code=202)
def render(clip_id: int, body: RenderBody, c: Ctx) -> dict:
    """Queue a render. Nothing is rendered until you ask for it."""
    clip = _check_render(c, clip_id, body.mode)
    if c.repos.jobs.count("clip_id = ? AND kind = 'render' AND state IN ('queued', 'running')", (clip_id,)):
        raise Conflict("Já existe uma renderização deste corte em andamento ou na fila.")
    label = "Prévia" if body.mode == "preview" else "Renderizar"
    return c.jobs.submit(
        "render", f"{label}: {clip['title']}",
        lambda ctx: render_clip(ctx, c, clip_id, body.mode),
        recording_id=clip["recording_id"], clip_id=clip_id, params=body.model_dump(),
    )


@router.get("/{clip_id}/render-plan")
def render_plan(clip_id: int, c: Ctx, mode: Literal["final", "preview"] = "final") -> dict:
    """Show exactly what FFmpeg would run (nothing is executed)."""
    c.repos.clips.require(clip_id)
    plan, clip, _recording = plan_for_clip(c, clip_id, mode, Path("<saida>.mp4.part"))
    return {
        "mode": mode,
        "output_size": f"{plan.out_w}x{plan.out_h}",
        "duration_s": plan.duration,
        "command": plan.args,
        "filter_graph": plan.graph,
        "notes": plan.notes,
        "subtitles_applied": plan.ass_text is not None,
    }


@router.get("/{clip_id}/file")
def clip_file(clip_id: int, request: Request, c: Ctx, download: bool = False):
    clip = c.repos.clips.require(clip_id)
    if not clip.get("output_path"):
        raise NotFound("Este corte ainda não foi renderizado.")
    path = Path(clip["output_path"])
    return range_file_response(path, request, download_name=path.name if download else None)


@router.get("/{clip_id}/preview")
def clip_preview(clip_id: int, request: Request, c: Ctx):
    clip = c.repos.clips.require(clip_id)
    if not clip.get("preview_path"):
        raise NotFound("Este corte ainda não tem prévia renderizada.")
    return range_file_response(Path(clip["preview_path"]), request)


# --------------------------------------------------------------------------- copy suggestions


class CopyEdit(Strict):
    hooks: list[str] = Field(default_factory=list, max_length=10)
    titles: list[str] = Field(default_factory=list, max_length=10)
    caption: str = Field("", max_length=2200)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    description: str = Field("", max_length=2200)
    cover_text: list[str] = Field(default_factory=list, max_length=6)
    comment_cta: str = Field("", max_length=300)


@router.get("/{clip_id}/copy")
def get_copy(clip_id: int, c: Ctx) -> dict:
    clip = c.repos.clips.require(clip_id)
    return {"copy": clip.get("copy_pack")}


@router.post("/{clip_id}/copy/generate")
def generate(clip_id: int, c: Ctx) -> dict:
    clip = c.repos.clips.require(clip_id)
    recording = c.repos.recordings.require(clip["recording_id"])
    candidate = c.repos.candidates.get(clip["candidate_id"]) if clip.get("candidate_id") else None
    profile = c.settings.load_profile()
    settings = c.settings.load()
    facts = clip.get("facts") or {}
    segments = c.repos.segments.in_range(recording["id"], clip["start_s"], clip["end_s"])
    excerpt = " ".join(s["text"].strip() for s in segments)[:400]
    peak_text = ""
    if candidate and candidate.get("excerpt"):
        peak_text = candidate["excerpt"]
    data = CopyInput(
        moment_type=clip["moment_type"], recording_name=recording["name"], start_s=clip["start_s"],
        end_s=clip["end_s"], excerpt=excerpt, quote=short_quote(peak_text or excerpt),
        map=clip.get("map") or recording.get("map"), agent=clip.get("agent") or recording.get("agent"),
        situation=facts.get("situation"), result=facts.get("result"),
        rank=facts.get("rank") or profile.rank_current or None, target_rank=profile.rank_target or None,
        series=profile.series_name or None, channel=profile.channel_name or None, note=facts.get("note"),
        base_hashtags=settings.base_hashtags, clip_id=clip_id,
        confirmed_type=bool(candidate is None or candidate["status"] == "approved"),
    )
    pack = generate_copy(data)
    c.repos.clips.update(clip_id, copy_pack=pack)
    return {"copy": pack}


@router.put("/{clip_id}/copy")
def save_copy(clip_id: int, body: CopyEdit, c: Ctx) -> dict:
    clip = c.repos.clips.require(clip_id)
    pack = dict(clip.get("copy_pack") or {})
    pack.update(body.model_dump())
    pack["edited"] = True
    c.repos.clips.update(clip_id, copy_pack=pack)
    return {"copy": pack}
