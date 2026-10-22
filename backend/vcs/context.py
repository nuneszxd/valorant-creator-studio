"""Application context: wires config, database, repositories, job queue and tools together."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AppConfig
from .db import Database
from .jobs.manager import JobManager
from .media.ffmpeg import FFmpegTools
from .repos import Repos
from .settings_store import SettingsStore


@dataclass
class AppContext:
    config: AppConfig
    db: Database
    repos: Repos
    settings: SettingsStore
    jobs: JobManager
    tools: FFmpegTools
    # Lets tests inject an httpx.MockTransport so integrations never touch the network in tests.
    http_transport: Any = None


def build_context(config: AppConfig) -> AppContext:
    config.ensure_dirs()
    db = Database(config.db_path)
    db.migrate()
    # Items left "in progress" by a crashed/closed run can never finish: reset them.
    db.execute(
        "UPDATE recordings SET status = CASE WHEN EXISTS ("
        "SELECT 1 FROM analyses a WHERE a.recording_id = recordings.id AND a.status = 'done'"
        ") THEN 'analyzed' ELSE 'imported' END WHERE status = 'analyzing'"
    )
    db.execute(
        "UPDATE clips SET status = CASE WHEN output_path IS NOT NULL THEN 'ready' ELSE 'draft' END, "
        "last_error = 'Renderização interrompida.' WHERE status = 'rendering'"
    )
    db.execute(
        "UPDATE radar_runs SET status = 'error', error = 'Coleta interrompida.' WHERE status = 'running'"
    )
    db.execute(
        "UPDATE analyses SET status = 'error', error = 'Análise interrompida.' WHERE status = 'running'"
    )
    return AppContext(
        config=config,
        db=db,
        repos=Repos(db),
        settings=SettingsStore(db, config),
        jobs=JobManager(db, config),
        tools=FFmpegTools.discover(config.ffmpeg_path, config.ffprobe_path),
    )
