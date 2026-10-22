"""Dashboard overview, library facets and controlled cleanup of files the app created."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import Field

from ..analysis.moment_types import MOMENT_TYPES
from ..errors import InvalidInput
from ..jobs.manager import STATE_LABELS
from ..models import Strict
from .deps import Ctx

router = APIRouter(prefix="/api", tags=["biblioteca"])

DELETABLE_SUFFIXES = {".mp4", ".part", ".ass", ".wav"}
DELETABLE_KINDS = {"export", "preview", "temp"}


def _counts(c: Any, table: str, column: str) -> dict[str, int]:
    rows = c.db.query(f"SELECT {column} AS k, COUNT(*) AS n FROM {table} GROUP BY {column}")
    return {r["k"]: r["n"] for r in rows}


@router.get("/overview")
def overview(c: Ctx) -> dict:
    jobs = c.repos.jobs
    last_radar: dict[str, Any] = {}
    for source in ("youtube", "twitch_clips", "manual"):
        rows = c.repos.radar_runs.list("source = ? AND status = 'done'", (source,), order_by="id DESC", limit=1)
        last_radar[source] = (
            {"id": rows[0]["id"], "collected_at": rows[0]["collected_at"], "sample_size": rows[0]["sample_size"]}
            if rows else None
        )
    profile = c.settings.load_profile()
    export_bytes = c.db.scalar("SELECT COALESCE(SUM(size_bytes), 0) FROM artifacts WHERE kind = 'export'") or 0
    preview_bytes = c.db.scalar("SELECT COALESCE(SUM(size_bytes), 0) FROM artifacts WHERE kind = 'preview'") or 0
    return {
        "recordings": {"total": c.repos.recordings.count(), "by_status": _counts(c, "recordings", "status")},
        "candidates": {"total": c.repos.candidates.count(), "by_status": _counts(c, "candidates", "status")},
        "clips": {"total": c.repos.clips.count(), "by_status": _counts(c, "clips", "status")},
        "publications": {
            "total": c.repos.publications.count(),
            "published": c.repos.publications.count("status = 'published'"),
            "planned": c.repos.publications.count("status = 'planned'"),
        },
        "ideas": c.repos.ideas.count("status != 'discarded'"),
        "jobs": {
            "counts": {s: jobs.count("state = ?", (s,)) for s in STATE_LABELS},
            "recent": jobs.list(order_by="id DESC", limit=6),
            "labels": STATE_LABELS,
        },
        "recent_recordings": c.repos.recordings.list(order_by="id DESC", limit=5),
        "top_pending_candidates": c.db.query(
            "SELECT k.id, k.title, k.score, k.confidence, k.moment_type, k.start_s, k.end_s, r.name AS recording_name "
            "FROM candidates k JOIN recordings r ON r.id = k.recording_id WHERE k.status = 'pending' "
            "ORDER BY k.score DESC LIMIT 5"
        ),
        "radar": last_radar,
        "disk": {"exports_bytes": export_bytes, "previews_bytes": preview_bytes},
        "setup": {
            "ffmpeg": bool(c.tools.ffmpeg and c.tools.ffprobe),
            "profile_filled": bool(profile.channel_name or profile.rank_current),
            "has_recording": c.repos.recordings.count() > 0,
            "integrations": c.config.integrations(),
        },
    }


@router.get("/library/facets")
def facets(c: Ctx) -> dict:
    def distinct(sql: str) -> list[str]:
        return [r["v"] for r in c.db.query(sql) if r["v"]]

    return {
        "games": distinct("SELECT DISTINCT game AS v FROM recordings ORDER BY game"),
        "maps": distinct("SELECT DISTINCT COALESCE(c.map, r.map) AS v FROM recordings r LEFT JOIN clips c ON c.recording_id = r.id ORDER BY v"),
        "agents": distinct("SELECT DISTINCT COALESCE(c.agent, r.agent) AS v FROM recordings r LEFT JOIN clips c ON c.recording_id = r.id ORDER BY v"),
        "moment_types": [{"key": k, "label": v} for k, v in MOMENT_TYPES.items()],
        "platforms": ["tiktok", "instagram", "youtube", "twitch", "kwai", "outro"],
    }


# --------------------------------------------------------------------------- cleanup


def _norm(path: str) -> str:
    """Case/symlink/relative-insensitive form used to compare paths (Windows paths are case-insensitive)."""
    return os.path.normcase(os.path.realpath(path))


def _original_paths(c: Any) -> set[str]:
    return {_norm(r["path"]) for r in c.db.query("SELECT path FROM recordings")}


def _deletable(c: Any, row: dict[str, Any], originals: set[str]) -> tuple[bool, str]:
    path = Path(row["path"])
    if _norm(row["path"]) in originals:
        return False, "é uma gravação original"
    if row["kind"] not in DELETABLE_KINDS:
        return False, "tipo de arquivo não removível por aqui"
    if path.suffix.lower() not in DELETABLE_SUFFIXES:
        return False, "extensão não removível por aqui"
    if not path.is_file():
        return False, "arquivo não existe mais"
    if row["kind"] == "temp" and c.repos.jobs.count("kind = 'render' AND state IN ('queued', 'running')"):
        return False, "uma renderização está em andamento"
    return True, ""


@router.get("/cleanup/preview")
def cleanup_preview(c: Ctx) -> dict:
    """List files created by the app that can be deleted. Nothing is deleted by this call."""
    originals = _original_paths(c)
    items = []
    for row in c.repos.artifacts.list(order_by="id DESC"):
        ok, reason = _deletable(c, row, originals)
        items.append({**row, "exists": Path(row["path"]).is_file(), "deletable": ok, "reason": reason})
    total = sum(i["size_bytes"] or 0 for i in items if i["deletable"])
    return {"artifacts": items, "deletable_bytes": total,
            "note": "Só aparecem arquivos que o próprio aplicativo registrou. Gravações originais nunca são removíveis."}


class CleanupBody(Strict):
    artifact_ids: list[int] = Field(default_factory=list, max_length=2000)
    confirm: bool = False


@router.post("/cleanup")
def cleanup(body: CleanupBody, c: Ctx) -> dict:
    """Delete the selected app-created files. Requires `confirm: true`; originals are never touched."""
    if not body.confirm:
        raise InvalidInput("Confirmação explícita necessária: envie confirm=true depois de revisar a lista.")
    originals = _original_paths(c)
    deleted: list[str] = []
    failed: list[dict[str, str]] = []
    for artifact_id in body.artifact_ids:
        row = c.repos.artifacts.get(artifact_id)
        if row is None:
            continue
        ok, reason = _deletable(c, row, originals)
        if not ok:
            if reason == "arquivo não existe mais":
                c.repos.artifacts.delete(artifact_id)
            else:
                failed.append({"path": row["path"], "reason": reason})
            continue
        try:
            Path(row["path"]).unlink()
        except OSError as exc:
            failed.append({"path": row["path"], "reason": exc.strerror or str(exc)})
            continue
        c.repos.artifacts.delete(artifact_id)
        deleted.append(row["path"])
        if row["kind"] == "export":
            c.db.execute(
                "UPDATE clips SET output_path = NULL, output_size = NULL, status = 'draft' WHERE output_path = ?",
                (row["path"],),
            )
        elif row["kind"] == "preview":
            c.db.execute("UPDATE clips SET preview_path = NULL WHERE preview_path = ?", (row["path"],))
    return {"deleted": deleted, "failed": failed}
