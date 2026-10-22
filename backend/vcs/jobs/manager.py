"""Background job queue.

Jobs run one at a time in a single worker thread (heavy local processing). State lives in SQLite
so the UI can poll it. Progress is only reported when the job has real information; otherwise it
stays NULL (indeterminate) - nothing is simulated.
"""

from __future__ import annotations

import logging
import queue
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Callable

from ..config import AppConfig
from ..db import Database
from ..errors import AppError, Conflict
from ..repos import JobsRepo
from ..security import redact
from ..utils import clamp, utcnow
from .procs import ProcResult, run_streaming, terminate_process

log = logging.getLogger(__name__)

FINISHED_STATES = ("succeeded", "failed", "cancelled")
STATE_LABELS = {
    "queued": "aguardando",
    "running": "em andamento",
    "succeeded": "concluída",
    "failed": "com erro",
    "cancelled": "cancelada",
}


class JobCancelled(Exception):
    """Raised inside a job when the user cancelled it."""


class JobContext:
    def __init__(self, manager: "JobManager", job_id: int) -> None:
        self.manager = manager
        self.job_id = job_id
        self._cancel = threading.Event()
        self._procs: set[Any] = set()
        self._lock = threading.Lock()
        self._last_write = 0.0
        self._last_label: str | None = None
        self._temp: Path | None = None

    # -- cancellation -------------------------------------------------------------
    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise JobCancelled()

    def request_cancel(self) -> None:
        self._cancel.set()
        with self._lock:
            procs = list(self._procs)
        for proc in procs:
            terminate_process(proc)

    def register_process(self, proc: Any) -> None:
        with self._lock:
            self._procs.add(proc)
        if self._cancel.is_set():
            terminate_process(proc)

    def unregister_process(self, proc: Any) -> None:
        with self._lock:
            self._procs.discard(proc)

    # -- progress -----------------------------------------------------------------
    def set_progress(self, fraction: float | None, label: str | None = None, *, force: bool = False) -> None:
        """Report real progress (0..1) or None for indeterminate."""
        now = time.monotonic()
        changed_label = label is not None and label != self._last_label
        done = fraction is not None and fraction >= 1.0
        if not (force or changed_label or done or now - self._last_write >= 0.4):
            return
        self._last_write = now
        fields: dict[str, Any] = {"progress": None if fraction is None else clamp(fraction, 0.0, 1.0)}
        if label is not None:
            fields["progress_label"] = label
            self._last_label = label
        self.manager.repo.update(self.job_id, **fields)

    def set_message(self, message: str) -> None:
        self.manager.repo.update(self.job_id, message=message)

    # -- helpers ------------------------------------------------------------------
    @property
    def temp_dir(self) -> Path:
        if self._temp is None:
            self._temp = self.manager.config.jobs_dir / str(self.job_id)
            self._temp.mkdir(parents=True, exist_ok=True)
        return self._temp

    def run(self, args: list[Any], *, on_line: Callable[[str], None] | None = None,
            cwd: Path | None = None, timeout: float | None = None) -> ProcResult:
        return run_streaming(args, cwd=cwd, ctx=self, on_line=on_line, timeout=timeout)

    def cleanup(self) -> None:
        if self._temp is None:
            return
        jobs_root = self.manager.config.jobs_dir.resolve()
        target = self._temp.resolve()
        if target != jobs_root and target.is_relative_to(jobs_root):
            shutil.rmtree(target, ignore_errors=True)
        self._temp = None


class JobManager:
    def __init__(self, db: Database, config: AppConfig) -> None:
        self.db = db
        self.config = config
        self.repo = JobsRepo(db)
        self._queue: queue.Queue[tuple[int, Callable[[JobContext], Any]]] = queue.Queue()
        self._contexts: dict[int, JobContext] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- lifecycle ----------------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self.recover_interrupted()
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, name="vcs-jobs", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        with self._lock:
            contexts = list(self._contexts.values())
        for ctx in contexts:
            ctx.request_cancel()
        if self._thread:
            self._thread.join(timeout=timeout)

    def recover_interrupted(self) -> None:
        """Jobs left queued/running by a previous run can never finish: mark them honestly."""
        self.db.execute(
            "UPDATE jobs SET state = 'failed', finished_at = ?, "
            "error = 'Interrompida: o aplicativo foi encerrado durante a execução.' "
            "WHERE state IN ('queued', 'running')",
            (utcnow(),),
        )
        jobs_dir = self.config.jobs_dir
        if jobs_dir.is_dir():
            for child in jobs_dir.iterdir():
                if child.is_dir():
                    shutil.rmtree(child, ignore_errors=True)

    # -- API ----------------------------------------------------------------------
    def submit(
        self,
        kind: str,
        label: str,
        func: Callable[[JobContext], Any],
        *,
        recording_id: int | None = None,
        clip_id: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        job = self.repo.insert(
            kind=kind, label=label, state="queued", recording_id=recording_id, clip_id=clip_id,
            params=params,
        )
        self._queue.put((job["id"], func))
        return job

    def cancel(self, job_id: int) -> dict[str, Any]:
        job = self.repo.require(job_id)
        if job["state"] in FINISHED_STATES:
            raise Conflict("Esta tarefa já foi finalizada.")
        if job["state"] == "queued":
            return self.repo.update(job_id, state="cancelled", finished_at=utcnow(), cancel_requested=1)
        with self._lock:
            ctx = self._contexts.get(job_id)
        self.repo.update(job_id, cancel_requested=1)
        if ctx is not None:
            ctx.request_cancel()
        return self.repo.require(job_id)

    def active_count(self) -> int:
        return self.repo.count("state IN ('queued', 'running')")

    # -- worker -------------------------------------------------------------------
    def _worker(self) -> None:
        while not self._stop.is_set():
            try:
                job_id, func = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                self._run(job_id, func)
            except Exception:  # pragma: no cover - defensive: the worker must never die
                log.exception("Job worker error")

    def _run(self, job_id: int, func: Callable[[JobContext], Any]) -> None:
        job = self.repo.get(job_id)
        if job is None or job["state"] != "queued":
            return  # cancelled while waiting
        ctx = JobContext(self, job_id)
        with self._lock:
            self._contexts[job_id] = ctx
        self.repo.update(job_id, state="running", started_at=utcnow())
        secrets = self.config.secrets()
        outcome: dict[str, Any]
        try:
            result = func(ctx)
            outcome = {"state": "succeeded", "result": result if isinstance(result, (dict, list)) else None}
        except JobCancelled:
            outcome = {"state": "cancelled"}
        except AppError as exc:
            outcome = {"state": "failed", "error": redact(exc.message, secrets)}
        except Exception as exc:
            log.exception("Job %s failed", job_id)
            outcome = {
                "state": "failed",
                "error": redact(f"Erro inesperado ({type(exc).__name__}): {exc}", secrets),
            }
        # Clean up before publishing the final state so observers never see a finished job
        # that still has temporary files lying around.
        ctx.cleanup()
        with self._lock:
            self._contexts.pop(job_id, None)
        self.repo.update(job_id, finished_at=utcnow(), **outcome)
