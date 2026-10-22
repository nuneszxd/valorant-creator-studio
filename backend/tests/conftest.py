from __future__ import annotations

import shutil
import time

import pytest
from fastapi.testclient import TestClient

from vcs.config import AppConfig
from vcs.main import create_app

HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))


def pytest_collection_modifyitems(config, items):
    if HAVE_FFMPEG:
        return
    skip = pytest.mark.skip(reason="ffmpeg/ffprobe não encontrados no PATH")
    for item in items:
        if "requires_ffmpeg" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def app_config(tmp_path):
    return AppConfig(data_dir=tmp_path / "data", frontend_dist=tmp_path / "no-dist")


@pytest.fixture
def client(app_config):
    app = create_app(app_config)
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


@pytest.fixture
def ctx(client):
    return client.app.state.ctx


@pytest.fixture
def recording(ctx, tmp_path):
    """A recording row pointing at a dummy file (no ffmpeg needed). Never a real video."""
    path = tmp_path / "live_fixture.mp4"
    path.write_bytes(b"\x00" * 16)
    return ctx.repos.recordings.insert(
        name=path.name, path=str(path), imported_at="2026-01-01T00:00:00+00:00", duration_s=120.0,
        width=1920, height=1080, fps=60.0, video_codec="h264", audio_codec="aac", audio_streams=1,
        size_bytes=16, map="Ascent", agent="Jett",
    )


def wait_for(predicate, timeout: float = 15.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condição não satisfeita dentro do tempo limite")
