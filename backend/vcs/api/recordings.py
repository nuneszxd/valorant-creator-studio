"""Recordings: import local files, list/inspect, stream for preview, remove from the library."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Query, Request
from pydantic import Field

from ..errors import Conflict, InvalidInput
from ..integrations.twitch import make_twitch_client, parse_twitch_url
from ..models import Strict
from ..security import validate_media_file
from ..streaming import range_file_response
from ..utils import loads, median, utcnow
from .deps import Ctx

router = APIRouter(prefix="/api/recordings", tags=["gravações"])

PLAYABLE_SUFFIXES = {".mp4", ".m4v", ".webm", ".mov"}
PLAYABLE_VIDEO = {"h264", "vp8", "vp9", "av1"}
PLAYABLE_AUDIO = {None, "aac", "mp3", "opus", "vorbis", "flac"}


class ImportBody(Strict):
    path: str = Field(min_length=1, max_length=1000)
    source: Literal["local", "twitch"] = "local"
    twitch_url: str | None = Field(None, max_length=300)
    game: str = Field("Valorant", max_length=60)
    map: str | None = Field(None, max_length=40)
    agent: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=1000)
    recorded_at: str | None = Field(None, max_length=40)


class RecordingPatch(Strict):
    name: str | None = Field(None, min_length=1, max_length=200)
    game: str | None = Field(None, max_length=60)
    map: str | None = Field(None, max_length=40)
    agent: str | None = Field(None, max_length=40)
    notes: str | None = Field(None, max_length=1000)
    recorded_at: str | None = Field(None, max_length=40)


def present(rec: dict[str, Any]) -> dict[str, Any]:
    out = dict(rec)
    suffix = Path(rec["path"]).suffix.lower()
    out["file_exists"] = Path(rec["path"]).is_file()
    out["browser_playable"] = (
        suffix in PLAYABLE_SUFFIXES
        and rec.get("video_codec") in PLAYABLE_VIDEO
        and rec.get("audio_codec") in PLAYABLE_AUDIO
    )
    return out


@router.get("")
def list_recordings(
    c: Ctx,
    status: str | None = None,
    game: str | None = None,
    map: str | None = None,
    agent: str | None = None,
    source: str | None = None,
    q: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (("status", status), ("game", game), ("map", map), ("agent", agent), ("source", source)):
        if value:
            clauses.append(f"r.{column} = ?")
            params.append(value)
    if q:
        clauses.append("instr(lower(r.name), lower(?)) > 0")
        params.append(q)
    if date_from:
        clauses.append("r.imported_at >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("r.imported_at <= ?")
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = c.db.query(
        "SELECT r.*, "
        "(SELECT COUNT(*) FROM candidates k WHERE k.recording_id = r.id) AS candidates_count, "
        "(SELECT COUNT(*) FROM candidates k WHERE k.recording_id = r.id AND k.status = 'approved') AS approved_count, "
        "(SELECT COUNT(*) FROM clips v WHERE v.recording_id = r.id) AS clips_count "
        f"FROM recordings r {where} ORDER BY r.id DESC LIMIT ? OFFSET ?",
        [*params, limit, offset],
    )
    for row in rows:
        row["source_meta"] = loads(row.get("source_meta"))
    return [present(r) for r in rows]


@router.post("", status_code=201)
def import_recording(body: ImportBody, c: Ctx) -> dict:
    """Register a local video file (no copy is made; only its path and metadata are stored)."""
    path = validate_media_file(body.path)
    existing = c.repos.recordings.list("path = ?", (str(path),), limit=1)
    if existing:
        raise Conflict("Esta gravação já foi importada.", details={"id": existing[0]["id"]})
    info = c.tools.probe(path)
    if not info.duration_s or info.duration_s <= 0:
        raise InvalidInput("Não foi possível determinar a duração deste vídeo.")

    warnings: list[str] = []
    source_ref: str | None = None
    source_meta: dict[str, Any] | None = None
    if body.source == "twitch":
        if not body.twitch_url:
            raise InvalidInput("Informe o link do VOD da Twitch.")
        parsed = parse_twitch_url(body.twitch_url)
        if parsed["kind"] != "vod":
            raise InvalidInput("O link precisa ser de um VOD (twitch.tv/videos/NÚMERO).")
        source_ref = parsed["id"]
        source_meta = {"url": body.twitch_url.strip()}
        client = make_twitch_client(c.config, c.http_transport)
        if client is not None:
            try:
                video = client.get_video(parsed["id"])
                if video:
                    source_meta.update({k: video.get(k) for k in ("title", "user_name", "created_at", "duration_s")})
                    expected = video.get("duration_s")
                    if expected and abs(expected - info.duration_s) / expected > 0.05:
                        warnings.append(
                            f"A duração do arquivo ({info.duration_s / 60:.1f} min) difere do VOD na Twitch "
                            f"({expected / 60:.1f} min). O download pode estar incompleto."
                        )
                    if not body.recorded_at and video.get("created_at"):
                        body.recorded_at = video["created_at"]
                else:
                    warnings.append("A Twitch não encontrou esse VOD (expirado ou privado); o arquivo foi importado mesmo assim.")
            except Exception as exc:  # metadata is a bonus: never block the import
                warnings.append(f"Não consegui consultar os metadados na Twitch: {getattr(exc, 'message', exc)}")
            finally:
                client.close()

    row = c.repos.recordings.insert(
        name=path.name, path=str(path), source=body.source, source_ref=source_ref, source_meta=source_meta,
        size_bytes=info.size_bytes, duration_s=info.duration_s, width=info.width, height=info.height,
        fps=info.fps, video_codec=info.video_codec, audio_codec=info.audio_codec,
        audio_streams=info.audio_streams, game=body.game, map=body.map, agent=body.agent,
        notes=body.notes, status="imported", imported_at=utcnow(), recorded_at=body.recorded_at,
    )
    if info.audio_streams == 0:
        warnings.append("Esta gravação não tem faixa de áudio: a análise automática não vai funcionar.")
    return {**present(row), "warnings": warnings}


@router.get("/{recording_id}")
def get_recording(recording_id: int, c: Ctx) -> dict:
    rec = c.repos.recordings.require(recording_id)
    latest = c.repos.analyses.list("recording_id = ?", (recording_id,), order_by="id DESC", limit=1)
    return {
        **present(rec),
        "latest_analysis": latest[0] if latest else None,
        "candidates_count": c.repos.candidates.count("recording_id = ?", (recording_id,)),
        "clips_count": c.repos.clips.count("recording_id = ?", (recording_id,)),
        "transcript_segments": c.repos.segments.count("recording_id = ?", (recording_id,)),
    }


@router.patch("/{recording_id}")
def patch_recording(recording_id: int, body: RecordingPatch, c: Ctx) -> dict:
    c.repos.recordings.require(recording_id)
    fields = body.model_dump(exclude_unset=True)
    return present(c.repos.recordings.update(recording_id, **fields))


@router.delete("/{recording_id}")
def delete_recording(recording_id: int, c: Ctx) -> dict:
    """Remove the recording and its analysis data from the library. The video file is never touched."""
    rec = c.repos.recordings.require(recording_id)
    c.repos.recordings.delete(recording_id)
    return {"status": "removido", "note": f"O arquivo original continua em {rec['path']}."}


@router.get("/{recording_id}/stream")
def stream_recording(recording_id: int, request: Request, c: Ctx):
    rec = c.repos.recordings.require(recording_id)
    return range_file_response(Path(rec["path"]), request)


@router.get("/{recording_id}/analyses")
def list_analyses(recording_id: int, c: Ctx) -> list[dict]:
    c.repos.recordings.require(recording_id)
    return c.repos.analyses.list("recording_id = ?", (recording_id,), order_by="id DESC")


@router.get("/{recording_id}/transcript")
def get_transcript(
    recording_id: int, c: Ctx,
    start: float = Query(0, ge=0), end: float | None = Query(None, ge=0),
) -> list[dict]:
    rec = c.repos.recordings.require(recording_id)
    stop = end if end is not None else (rec["duration_s"] or 10**9)
    return c.repos.segments.in_range(recording_id, start, stop)


@router.get("/{recording_id}/signals")
def get_signals(recording_id: int, c: Ctx) -> dict:
    """Loudness curve and scene events of the latest finished analysis (for the timeline chart)."""
    c.repos.recordings.require(recording_id)
    latest = c.repos.analyses.list("recording_id = ? AND status = 'done'", (recording_id,), order_by="id DESC", limit=1)
    if not latest:
        return {"analysis_id": None, "window_s": None, "rms_db": [], "scenes": [], "p50": None, "p95": None}
    rows = c.db.query("SELECT kind, data FROM analysis_signals WHERE analysis_id = ?", (latest[0]["id"],))
    data = {r["kind"]: loads(r["data"], {}) for r in rows}
    audio = data.get("audio") or {}
    rms = audio.get("rms_db") or []
    window = audio.get("window_s") or 0.5
    step = 1
    if len(rms) > 1500:
        step = -(-len(rms) // 1500)
        rms = [max(rms[i:i + step]) for i in range(0, len(rms), step)]
    return {
        "analysis_id": latest[0]["id"],
        "window_s": window * step,
        "rms_db": rms,
        "p50": audio.get("p50"),
        "p95": audio.get("p95"),
        "scenes": (data.get("scenes") or {}).get("events", []),
        "median_db": median(rms),
    }
