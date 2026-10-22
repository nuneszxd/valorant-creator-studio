"""SQLite access. Stores metadata and local paths only - never the videos themselves."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from .utils import utcnow

log = logging.getLogger(__name__)

SCHEMA_V1 = """
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE recordings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT 'local',
    source_ref TEXT,
    source_meta TEXT,
    size_bytes INTEGER,
    duration_s REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    video_codec TEXT,
    audio_codec TEXT,
    audio_streams INTEGER NOT NULL DEFAULT 0,
    game TEXT NOT NULL DEFAULT 'Valorant',
    map TEXT,
    agent TEXT,
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'imported',
    last_error TEXT,
    imported_at TEXT NOT NULL,
    recorded_at TEXT
);

CREATE TABLE jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    recording_id INTEGER REFERENCES recordings(id) ON DELETE SET NULL,
    clip_id INTEGER,
    params TEXT,
    progress REAL,
    progress_label TEXT,
    message TEXT,
    error TEXT,
    result TEXT,
    cancel_requested INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX idx_jobs_state ON jobs(state);

CREATE TABLE analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    job_id INTEGER,
    level TEXT NOT NULL,
    options TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    stats TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE analysis_signals (
    analysis_id INTEGER NOT NULL REFERENCES analyses(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    PRIMARY KEY (analysis_id, kind)
);

CREATE TABLE transcript_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    analysis_id INTEGER REFERENCES analyses(id) ON DELETE CASCADE,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    text TEXT NOT NULL,
    words TEXT
);
CREATE INDEX idx_segments_recording ON transcript_segments(recording_id, start_s);

CREATE TABLE candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    analysis_id INTEGER REFERENCES analyses(id) ON DELETE SET NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    title TEXT NOT NULL,
    moment_type TEXT NOT NULL DEFAULT 'pico_audio',
    score REAL NOT NULL DEFAULT 0,
    confidence TEXT NOT NULL DEFAULT 'baixa',
    reasons TEXT,
    excerpt TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    outcome TEXT,
    tags TEXT,
    manual INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_candidates_recording ON candidates(recording_id, score DESC);

CREATE TABLE clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id INTEGER REFERENCES candidates(id) ON DELETE SET NULL,
    recording_id INTEGER NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    start_s REAL NOT NULL,
    end_s REAL NOT NULL,
    moment_type TEXT NOT NULL DEFAULT 'outro',
    map TEXT,
    agent TEXT,
    facts TEXT,
    render_config TEXT,
    subtitles TEXT,
    subtitle_style TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    output_path TEXT,
    output_size INTEGER,
    rendered_at TEXT,
    last_error TEXT,
    preview_path TEXT,
    copy_pack TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    path TEXT NOT NULL UNIQUE,
    size_bytes INTEGER,
    recording_id INTEGER,
    clip_id INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER REFERENCES clips(id) ON DELETE SET NULL,
    platform TEXT NOT NULL,
    url TEXT,
    status TEXT NOT NULL DEFAULT 'published',
    planned_for TEXT,
    published_at TEXT,
    format TEXT,
    theme TEXT,
    hook TEXT,
    duration_s REAL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    shares INTEGER,
    avg_watch_s REAL,
    retention_pct REAL,
    notes TEXT,
    feedback TEXT,
    metrics_updated_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    data TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE ideas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    format TEXT,
    status TEXT NOT NULL DEFAULT 'idea',
    rationale TEXT,
    script TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE radar_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    params TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    collected_at TEXT NOT NULL,
    finished_at TEXT,
    sample_size INTEGER NOT NULL DEFAULT 0,
    quota TEXT,
    error TEXT,
    job_id INTEGER
);

CREATE TABLE radar_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER REFERENCES radar_runs(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    external_id TEXT,
    url TEXT,
    title TEXT,
    channel TEXT,
    published_at TEXT,
    duration_s REAL,
    views INTEGER,
    likes INTEGER,
    comments INTEGER,
    language TEXT,
    tags TEXT,
    hashtags TEXT,
    query TEXT,
    observed_at TEXT NOT NULL,
    manual INTEGER NOT NULL DEFAULT 0,
    notes TEXT,
    extra TEXT
);
CREATE INDEX idx_radar_items_run ON radar_items(run_id);

CREATE TABLE trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES radar_runs(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    source TEXT NOT NULL,
    source_url TEXT,
    collected_at TEXT NOT NULL,
    observed TEXT,
    evidence TEXT NOT NULL DEFAULT 'observado',
    relevance TEXT,
    suggestion TEXT,
    confidence TEXT NOT NULL DEFAULT 'baixa',
    limitations TEXT,
    sample_size INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX idx_trends_run ON trends(run_id);

CREATE TABLE quota_usage (
    day TEXT NOT NULL,
    source TEXT NOT NULL,
    calls INTEGER NOT NULL DEFAULT 0,
    units INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, source)
);
"""

MIGRATIONS: list[tuple[int, str]] = [(1, SCHEMA_V1)]


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        return conn

    def migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = self.connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
            )
            applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
            for version, script in MIGRATIONS:
                if version in applied:
                    continue
                log.info("Applying database migration %s", version)
                # The schema change and its bookkeeping row commit together, so a crash can never leave a
                # half-recorded migration behind.
                record = f"INSERT INTO schema_migrations (version, applied_at) VALUES ({int(version)}, '{utcnow()}');"
                try:
                    conn.executescript("BEGIN;\n" + script + "\n" + record + "\nCOMMIT;")
                except Exception:
                    if conn.in_transaction:
                        conn.execute("ROLLBACK")
                    raise
        finally:
            conn.close()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
        conn = self.connect()
        try:
            return [dict(row) for row in conn.execute(sql, tuple(params)).fetchall()]
        finally:
            conn.close()

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict[str, Any] | None:
        conn = self.connect()
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        conn = self.connect()
        try:
            row = conn.execute(sql, tuple(params)).fetchone()
            return row[0] if row else None
        finally:
            conn.close()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run one write statement (autocommit). Returns lastrowid."""
        conn = self.connect()
        try:
            cursor = conn.execute(sql, tuple(params))
            return int(cursor.lastrowid or 0)
        finally:
            conn.close()

    def execute_count(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run one write statement (autocommit). Returns the number of rows changed."""
        conn = self.connect()
        try:
            return int(conn.execute(sql, tuple(params)).rowcount)
        finally:
            conn.close()
