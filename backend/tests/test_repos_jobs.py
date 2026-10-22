from __future__ import annotations

import sys

import pytest

from vcs.errors import AppError, NotFound
from vcs.jobs.manager import JobCancelled

from .conftest import wait_for


def test_repo_insert_get_update_and_json_fields(ctx):
    repo = ctx.repos.recordings
    row = repo.insert(
        name="live.mp4", path="C:/videos/live.mp4", imported_at="2026-01-01T00:00:00+00:00",
        source_meta={"vod": 123},
    )
    assert row["id"] > 0
    assert row["source_meta"] == {"vod": 123}
    assert row["game"] == "Valorant"
    updated = repo.update(row["id"], map="Ascent", source_meta={"vod": 456})
    assert updated["map"] == "Ascent" and updated["source_meta"] == {"vod": 456}
    assert repo.count("map = ?", ("Ascent",)) == 1
    repo.delete(row["id"])
    assert repo.get(row["id"]) is None


def test_repo_rejects_unknown_columns_and_missing_rows(ctx):
    with pytest.raises(ValueError):
        ctx.repos.recordings.insert(name="x", path="p", imported_at="t", hacked="1; DROP TABLE x")
    with pytest.raises(NotFound):
        ctx.repos.recordings.require(999)


def test_job_success_failure_and_result(ctx):
    ok = ctx.jobs.submit("test", "ok", lambda c: {"answer": 42})
    wait_for(lambda: ctx.repos.jobs.require(ok["id"])["state"] == "succeeded")
    assert ctx.repos.jobs.require(ok["id"])["result"] == {"answer": 42}

    def boom(_c):
        raise AppError("falha amigável")

    bad = ctx.jobs.submit("test", "bad", boom)
    wait_for(lambda: ctx.repos.jobs.require(bad["id"])["state"] == "failed")
    assert ctx.repos.jobs.require(bad["id"])["error"] == "falha amigável"

    def crash(_c):
        raise RuntimeError("client_secret=supersecretvalue")

    crashed = ctx.jobs.submit("test", "crash", crash)
    wait_for(lambda: ctx.repos.jobs.require(crashed["id"])["state"] == "failed")
    assert "supersecretvalue" not in ctx.repos.jobs.require(crashed["id"])["error"]


def test_job_progress_is_null_unless_reported(ctx):
    seen = {}

    def work(c):
        seen["before"] = ctx.repos.jobs.require(c.job_id)["progress"]
        c.set_progress(0.5, "metade", force=True)
        seen["mid"] = ctx.repos.jobs.require(c.job_id)["progress"]
        return {}

    job = ctx.jobs.submit("test", "progress", work)
    wait_for(lambda: ctx.repos.jobs.require(job["id"])["state"] == "succeeded")
    assert seen["before"] is None
    assert seen["mid"] == 0.5


def test_cancel_queued_job(ctx):
    import threading

    gate = threading.Event()
    blocker = ctx.jobs.submit("test", "blocker", lambda c: gate.wait(10) and {})
    wait_for(lambda: ctx.repos.jobs.require(blocker["id"])["state"] == "running")
    queued = ctx.jobs.submit("test", "queued", lambda c: {})
    cancelled = ctx.jobs.cancel(queued["id"])
    assert cancelled["state"] == "cancelled"
    gate.set()
    wait_for(lambda: ctx.repos.jobs.require(blocker["id"])["state"] == "succeeded")
    assert ctx.repos.jobs.require(queued["id"])["state"] == "cancelled"


def test_cancel_running_job_terminates_process(ctx):
    def work(c):
        c.run([sys.executable, "-c", "import time; time.sleep(60)"])
        return {}

    job = ctx.jobs.submit("test", "sleeper", work)
    wait_for(lambda: ctx.repos.jobs.require(job["id"])["state"] == "running")
    ctx.jobs.cancel(job["id"])
    wait_for(lambda: ctx.repos.jobs.require(job["id"])["state"] == "cancelled", timeout=20)


def test_cancel_finished_job_conflicts(ctx):
    job = ctx.jobs.submit("test", "quick", lambda c: {})
    wait_for(lambda: ctx.repos.jobs.require(job["id"])["state"] == "succeeded")
    with pytest.raises(AppError) as info:
        ctx.jobs.cancel(job["id"])
    assert info.value.status_code == 409


def test_job_cancelled_exception_marks_cancelled(ctx):
    def work(_c):
        raise JobCancelled()

    job = ctx.jobs.submit("test", "self-cancel", work)
    wait_for(lambda: ctx.repos.jobs.require(job["id"])["state"] == "cancelled")


def test_job_temp_dir_is_removed_after_run(ctx):
    paths = {}

    def work(c):
        paths["dir"] = c.temp_dir
        (c.temp_dir / "x.tmp").write_text("x")
        return {}

    job = ctx.jobs.submit("test", "tmp", work)
    wait_for(lambda: ctx.repos.jobs.require(job["id"])["state"] == "succeeded")
    assert not paths["dir"].exists()
