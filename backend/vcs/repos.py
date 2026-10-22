"""Thin data-access layer: one Repo per table. Column names are whitelisted per repo."""

from __future__ import annotations

from typing import Any, Iterable, Sequence

from .db import Database
from .errors import NotFound
from .utils import dumps, loads, utcnow


class Repo:
    table = ""
    columns: tuple[str, ...] = ()
    json_fields: tuple[str, ...] = ()
    noun = "Registro"

    def __init__(self, db: Database) -> None:
        self.db = db

    # -- encoding -----------------------------------------------------------------
    def _decode(self, row: dict[str, Any]) -> dict[str, Any]:
        for name in self.json_fields:
            if name in row:
                row[name] = loads(row[name])
        return row

    def _encode(self, fields: dict[str, Any]) -> dict[str, Any]:
        data: dict[str, Any] = {}
        for key, value in fields.items():
            if key not in self.columns:
                raise ValueError(f"Coluna inválida para {self.table}: {key}")
            data[key] = dumps(value) if key in self.json_fields and value is not None else value
        return data

    # -- reads --------------------------------------------------------------------
    def get(self, row_id: int) -> dict[str, Any] | None:
        row = self.db.one(f"SELECT * FROM {self.table} WHERE id = ?", (row_id,))
        return self._decode(row) if row else None

    def require(self, row_id: int) -> dict[str, Any]:
        row = self.get(row_id)
        if row is None:
            raise NotFound(f"{self.noun} {row_id} não encontrado.")
        return row

    def list(
        self,
        where: str = "",
        params: Sequence[Any] = (),
        order_by: str = "id DESC",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        sql = f"SELECT * FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY {order_by}"
        args: list[Any] = list(params)
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            args.extend([limit, offset])
        return [self._decode(r) for r in self.db.query(sql, args)]

    def count(self, where: str = "", params: Sequence[Any] = ()) -> int:
        sql = f"SELECT COUNT(*) FROM {self.table}"
        if where:
            sql += f" WHERE {where}"
        return int(self.db.scalar(sql, params) or 0)

    # -- writes -------------------------------------------------------------------
    def insert(self, **fields: Any) -> dict[str, Any]:
        data = self._encode(fields)
        now = utcnow()
        if "created_at" in self.columns and "created_at" not in data:
            data["created_at"] = now
        if "updated_at" in self.columns and "updated_at" not in data:
            data["updated_at"] = now
        cols = ", ".join(data)
        marks = ", ".join("?" for _ in data)
        new_id = self.db.execute(
            f"INSERT INTO {self.table} ({cols}) VALUES ({marks})", tuple(data.values())
        )
        return self.require(new_id)

    def update(self, row_id: int, **fields: Any) -> dict[str, Any]:
        data = self._encode(fields)
        if not data:
            return self.require(row_id)
        if "updated_at" in self.columns and "updated_at" not in data:
            data["updated_at"] = utcnow()
        sets = ", ".join(f"{key} = ?" for key in data)
        self.db.execute(f"UPDATE {self.table} SET {sets} WHERE id = ?", (*data.values(), row_id))
        return self.require(row_id)

    def delete(self, row_id: int) -> None:
        self.db.execute(f"DELETE FROM {self.table} WHERE id = ?", (row_id,))


class RecordingsRepo(Repo):
    table = "recordings"
    noun = "Gravação"
    json_fields = ("source_meta",)
    columns = (
        "name", "path", "source", "source_ref", "source_meta", "size_bytes", "duration_s", "width",
        "height", "fps", "video_codec", "audio_codec", "audio_streams", "game", "map", "agent",
        "notes", "status", "last_error", "imported_at", "recorded_at",
    )


class JobsRepo(Repo):
    table = "jobs"
    noun = "Tarefa"
    json_fields = ("params", "result")
    columns = (
        "kind", "label", "state", "recording_id", "clip_id", "params", "progress", "progress_label",
        "message", "error", "result", "cancel_requested", "created_at", "started_at", "finished_at",
    )


class AnalysesRepo(Repo):
    table = "analyses"
    noun = "Análise"
    json_fields = ("options", "stats")
    columns = (
        "recording_id", "job_id", "level", "options", "status", "stats", "error", "created_at",
        "finished_at",
    )


class SegmentsRepo(Repo):
    table = "transcript_segments"
    noun = "Trecho"
    json_fields = ("words",)
    columns = ("recording_id", "analysis_id", "start_s", "end_s", "text", "words")

    def replace_for_ranges(
        self, recording_id: int, ranges: Iterable[tuple[float, float]], segments: Iterable[dict[str, Any]]
    ) -> None:
        """Replace stored segments overlapping the given ranges with new ones (single transaction)."""
        with self.db.tx() as conn:
            for start, end in ranges:
                conn.execute(
                    "DELETE FROM transcript_segments WHERE recording_id = ? AND start_s < ? AND end_s > ?",
                    (recording_id, end, start),
                )
            for seg in segments:
                conn.execute(
                    "INSERT INTO transcript_segments (recording_id, analysis_id, start_s, end_s, text, words) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        recording_id,
                        seg.get("analysis_id"),
                        seg["start_s"],
                        seg["end_s"],
                        seg["text"],
                        dumps(seg.get("words")) if seg.get("words") is not None else None,
                    ),
                )

    def in_range(self, recording_id: int, start: float, end: float) -> list[dict[str, Any]]:
        return self.list(
            "recording_id = ? AND end_s > ? AND start_s < ?",
            (recording_id, start, end),
            order_by="start_s ASC",
        )


class CandidatesRepo(Repo):
    table = "candidates"
    noun = "Candidato"
    json_fields = ("reasons", "tags")
    columns = (
        "recording_id", "analysis_id", "start_s", "end_s", "title", "moment_type", "score",
        "confidence", "reasons", "excerpt", "status", "outcome", "tags", "manual", "created_at",
        "updated_at",
    )


class ClipsRepo(Repo):
    table = "clips"
    noun = "Corte"
    json_fields = ("facts", "render_config", "subtitles", "subtitle_style", "copy_pack")
    columns = (
        "candidate_id", "recording_id", "title", "start_s", "end_s", "moment_type", "map", "agent",
        "facts", "render_config", "subtitles", "subtitle_style", "status", "output_path",
        "output_size", "rendered_at", "last_error", "preview_path", "copy_pack", "created_at",
        "updated_at",
    )


class ArtifactsRepo(Repo):
    table = "artifacts"
    noun = "Arquivo"
    columns = ("kind", "path", "size_bytes", "recording_id", "clip_id", "created_at")

    def register(self, kind: str, path: str, size: int | None, *, recording_id: int | None = None,
                 clip_id: int | None = None) -> None:
        self.db.execute(
            "INSERT INTO artifacts (kind, path, size_bytes, recording_id, clip_id, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(path) DO UPDATE SET size_bytes = excluded.size_bytes, kind = excluded.kind",
            (kind, path, size, recording_id, clip_id, utcnow()),
        )


class PublicationsRepo(Repo):
    table = "publications"
    noun = "Publicação"
    columns = (
        "clip_id", "platform", "url", "status", "planned_for", "published_at", "format", "theme",
        "hook", "duration_s", "views", "likes", "comments", "shares", "avg_watch_s", "retention_pct",
        "notes", "feedback", "metrics_updated_at", "created_at", "updated_at",
    )


class IdeasRepo(Repo):
    table = "ideas"
    noun = "Ideia"
    json_fields = ("rationale", "script")
    columns = (
        "title", "format", "status", "rationale", "script", "source", "created_at", "updated_at",
    )


class RadarRunsRepo(Repo):
    table = "radar_runs"
    noun = "Coleta"
    json_fields = ("params", "quota")
    columns = (
        "source", "params", "status", "collected_at", "finished_at", "sample_size", "quota", "error",
        "job_id",
    )


class RadarItemsRepo(Repo):
    table = "radar_items"
    noun = "Item do radar"
    json_fields = ("tags", "hashtags", "extra")
    columns = (
        "run_id", "platform", "external_id", "url", "title", "channel", "published_at", "duration_s",
        "views", "likes", "comments", "language", "tags", "hashtags", "query", "observed_at",
        "manual", "notes", "extra",
    )


class TrendsRepo(Repo):
    table = "trends"
    noun = "Tendência"
    json_fields = ("observed",)
    columns = (
        "run_id", "kind", "label", "source", "source_url", "collected_at", "observed", "evidence",
        "relevance", "suggestion", "confidence", "limitations", "sample_size",
    )


class Repos:
    def __init__(self, db: Database) -> None:
        self.recordings = RecordingsRepo(db)
        self.jobs = JobsRepo(db)
        self.analyses = AnalysesRepo(db)
        self.segments = SegmentsRepo(db)
        self.candidates = CandidatesRepo(db)
        self.clips = ClipsRepo(db)
        self.artifacts = ArtifactsRepo(db)
        self.publications = PublicationsRepo(db)
        self.ideas = IdeasRepo(db)
        self.radar_runs = RadarRunsRepo(db)
        self.radar_items = RadarItemsRepo(db)
        self.trends = TrendsRepo(db)
