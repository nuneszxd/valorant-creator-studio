from __future__ import annotations

from fastapi.testclient import TestClient

from vcs.config import AppConfig
from vcs.main import create_app


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_openapi_contract_is_available_and_interactive_docs_are_opt_in(client, tmp_path):
    assert client.get("/api/openapi.json").status_code == 200
    # Swagger UI loads scripts from a CDN, so it is off unless explicitly enabled.
    assert client.get("/api/docs").status_code == 404

    app = create_app(AppConfig(data_dir=tmp_path / "docs-data", frontend_dist=tmp_path / "nodist", api_docs=True))
    with TestClient(app, base_url="http://127.0.0.1:8000") as docs_client:
        assert docs_client.get("/api/docs").status_code == 200


def test_security_headers_and_hostile_paths(client):
    response = client.get("/api/health")
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["x-content-type-options"] == "nosniff"
    # A backslash path could point at a Windows network share (UNC): refused before any file access.
    assert client.get("/%5C%5Chost%5Cshare%5Cx").status_code == 403
    assert client.get("/api/health", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    assert client.get("/api/health", headers={"sec-fetch-site": "same-origin"}).status_code == 200


def test_dev_origin_is_only_trusted_in_dev_mode(client, tmp_path):
    assert client.post("/api/jobs/clear-finished", headers={"origin": "http://localhost:5173"}).status_code == 403
    app = create_app(AppConfig(data_dir=tmp_path / "dev-data", frontend_dist=tmp_path / "nodist", dev_ports=(5173,)))
    with TestClient(app, base_url="http://127.0.0.1:8000") as dev_client:
        assert dev_client.post("/api/jobs/clear-finished", headers={"origin": "http://localhost:5173"}).status_code == 200


def test_foreign_host_header_is_blocked(client):
    response = client.get("/api/health", headers={"host": "evil.example"})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_cross_origin_writes_are_blocked_but_same_origin_and_no_origin_work(client):
    blocked = client.post("/api/jobs/clear-finished", headers={"origin": "http://evil.example"})
    assert blocked.status_code == 403
    cross_site = client.post("/api/jobs/clear-finished", headers={"sec-fetch-site": "cross-site"})
    assert cross_site.status_code == 403
    ok_origin = client.post("/api/jobs/clear-finished", headers={"origin": "http://127.0.0.1:8000"})
    assert ok_origin.status_code == 200
    no_origin = client.post("/api/jobs/clear-finished")
    assert no_origin.status_code == 200


def test_unknown_api_route_returns_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404


def test_root_explains_missing_frontend(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Interface ainda não compilada" in response.json()["message"]


def test_capabilities_shape_and_no_secrets(client):
    data = client.get("/api/system/capabilities").json()
    assert set(data["ffmpeg"]) >= {"available", "encoders", "filters", "version"}
    assert set(data["integrations"]) == {"twitch", "youtube"}
    assert "transcription" in data and "paths" in data
    assert "client_secret" not in str(data).lower()


def test_moment_types(client):
    types = client.get("/api/system/moment-types").json()["types"]
    assert any(t["key"] == "clutch" for t in types)


def test_settings_defaults_patch_and_validation(client, tmp_path):
    data = client.get("/api/settings").json()
    assert data["settings"]["whisper_model"] == "base"
    assert data["settings"]["render"]["width"] == 1080

    patched = client.patch("/api/settings", json={"whisper_model": "small", "render": {"crf": 22}})
    assert patched.status_code == 200
    body = patched.json()["settings"]
    assert body["whisper_model"] == "small" and body["render"]["crf"] == 22
    assert body["render"]["height"] == 1920  # untouched fields are preserved

    bad = client.patch("/api/settings", json={"render": {"width": 1081}})
    assert bad.status_code == 422
    assert "error" in bad.json()

    unknown = client.patch("/api/settings", json={"twitch_client_secret": "x"})
    assert unknown.status_code == 422

    out = tmp_path / "meus_cortes"
    set_out = client.patch("/api/settings", json={"output_dir": str(out)})
    assert set_out.status_code == 200
    assert out.is_dir()

    relative = client.patch("/api/settings", json={"output_dir": "relativo"})
    assert relative.status_code == 422

    # Reading the settings never touches the disk: an unplugged output drive must not break the UI.
    out.rmdir()
    assert client.get("/api/settings").status_code == 200
    assert client.get("/api/system/capabilities").status_code == 200
    assert not out.exists()


def test_whisper_cpp_paths_are_validated_because_they_are_executed(client):
    refused = client.patch("/api/settings", json={"whisper_cpp_path": "C:\\Windows\\System32\\cmd.exe"})
    assert refused.status_code == 422
    assert client.patch("/api/settings", json={"whisper_cpp_model_path": "C:\\x\\notes.txt"}).status_code == 422
    ok = client.patch("/api/settings", json={"whisper_cpp_path": "D:\\tools\\whisper-cli.exe",
                                             "whisper_cpp_model_path": "D:\\tools\\ggml-base.bin"})
    assert ok.status_code == 200 and ok.json()["settings"]["whisper_cpp_path"].endswith("whisper-cli.exe")
    cleared = client.patch("/api/settings", json={"whisper_cpp_path": None, "whisper_cpp_model_path": None})
    assert cleared.json()["settings"]["whisper_cpp_path"] is None


def test_profile_roundtrip_and_validation(client):
    profile = client.get("/api/profile").json()
    assert profile["preferred_duration_min_s"] == 20
    profile.update(channel_name="Meu Canal", rank_current="Diamante 2", rank_target="Imortal 1",
                   agents=["Jett", "Reyna"], preferred_types=["clutch", "engracado"])
    saved = client.put("/api/profile", json=profile)
    assert saved.status_code == 200
    assert client.get("/api/profile").json()["channel_name"] == "Meu Canal"

    profile["preferred_types"] = ["nao_existe"]
    assert client.put("/api/profile", json=profile).status_code == 422
    profile["preferred_types"] = []
    profile["preferred_duration_min_s"] = 90
    profile["preferred_duration_max_s"] = 30
    assert client.put("/api/profile", json=profile).status_code == 422


def test_jobs_endpoints(client, ctx):
    assert client.get("/api/jobs").json() == []
    assert client.get("/api/jobs/999").status_code == 404
    summary = client.get("/api/jobs/summary").json()
    assert summary["counts"]["queued"] == 0 and "labels" in summary
    assert client.get("/api/jobs?state=banana").status_code == 422

    job = ctx.jobs.submit("test", "x", lambda c: {"ok": True})
    from .conftest import wait_for

    wait_for(lambda: client.get(f"/api/jobs/{job['id']}").json()["state"] == "succeeded")
    listed = client.get("/api/jobs?state=succeeded").json()
    assert listed and listed[0]["state_label"] == "concluída"
    assert client.post(f"/api/jobs/{job['id']}/cancel").status_code == 409
