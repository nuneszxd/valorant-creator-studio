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


def wait_for(predicate, timeout: float = 15.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise AssertionError("condição não satisfeita dentro do tempo limite")
