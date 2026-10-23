"""End-to-end tests with real FFmpeg on synthetic videos generated at test time."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from vcs.doctor import run_checks
from vcs.media.ffmpeg import FFmpegTools

from .conftest import wait_for
from .helpers import make_test_video

pytestmark = pytest.mark.requires_ffmpeg

TERMINAL = ("succeeded", "failed", "cancelled")


def finish(client, job, timeout=180):
    wait_for(lambda: client.get(f"/api/jobs/{job['id']}").json()["state"] in TERMINAL, timeout=timeout)
    return client.get(f"/api/jobs/{job['id']}").json()


def import_video(client, path, **extra):
    response = client.post("/api/recordings", json={"path": str(path), **extra})
    assert response.status_code == 201, response.text
    return response.json()


def test_import_probe_and_range_streaming(client, tmp_path):
    video = make_test_video(tmp_path / "partida.mp4", seconds=6)
    rec = import_video(client, video, map="Ascent")
    assert (rec["width"], rec["height"]) == (640, 360) and rec["audio_streams"] == 1
    assert rec["duration_s"] == pytest.approx(6, abs=0.6)
    assert rec["status"] == "imported" and rec["browser_playable"] is True and rec["warnings"] == []

    dup = client.post("/api/recordings", json={"path": str(video)})
    assert dup.status_code == 409 and dup.json()["error"]["details"]["id"] == rec["id"]

    size = video.stat().st_size
    full = client.get(f"/api/recordings/{rec['id']}/stream")
    assert full.status_code == 200 and len(full.content) == size
    part = client.get(f"/api/recordings/{rec['id']}/stream", headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100
    assert part.headers["content-range"] == f"bytes 0-99/{size}"
    tail = client.get(f"/api/recordings/{rec['id']}/stream", headers={"Range": "bytes=-50"})
    assert tail.status_code == 206 and len(tail.content) == 50
    assert client.get(f"/api/recordings/{rec['id']}/stream", headers={"Range": "bytes=999999999-"}).status_code == 416

    listed = client.get("/api/recordings", params={"map": "Ascent", "q": "PARTIDA"}).json()
    assert [r["id"] for r in listed] == [rec["id"]] and listed[0]["file_exists"] is True
    assert client.patch(f"/api/recordings/{rec['id']}", json={"agent": "Jett"}).json()["agent"] == "Jett"

    removed = client.delete(f"/api/recordings/{rec['id']}").json()
    assert "continua em" in removed["note"] and video.exists()  # the original is never deleted


def test_import_rejects_bad_inputs(client, tmp_path):
    fake = tmp_path / "falso.mp4"
    fake.write_bytes(b"not a video at all")
    assert client.post("/api/recordings", json={"path": str(fake)}).status_code == 422
    assert client.post("/api/recordings", json={"path": "partida.mp4"}).status_code == 422
    assert client.post("/api/recordings", json={"path": str(tmp_path / "nao_existe.mp4")}).status_code == 404
    audio_only = tmp_path / "som.mp4"
    audio_only.write_bytes(b"")
    assert client.post("/api/recordings", json={"path": str(audio_only)}).status_code == 422
    video = make_test_video(tmp_path / "ok.mp4", seconds=3)
    twitch_without_url = client.post("/api/recordings", json={"path": str(video), "source": "twitch"})
    assert twitch_without_url.status_code == 422


def test_light_analysis_finds_the_loud_burst_and_keeps_reviewed_work(client, tmp_path):
    video = make_test_video(tmp_path / "live.mp4", seconds=40, burst=(18, 20))
    rec = import_video(client, video)
    job = client.post(f"/api/recordings/{rec['id']}/analyze", json={"level": "leve"}).json()
    assert job["state"] == "queued"
    done = finish(client, job)
    assert done["state"] == "succeeded", done["error"]
    assert done["result"]["candidates_created"] >= 1

    candidates = client.get("/api/candidates", params={"recording_id": rec["id"]}).json()
    assert candidates, "the burst must produce a candidate"
    best = candidates[0]
    assert best["start_s"] <= 19 <= best["end_s"]
    assert best["moment_type"] == "pico_audio" and best["status"] == "pending"
    assert best["score"] > 0 and best["reasons"] and best["confidence"] in ("baixa", "média", "alta")
    assert any(r["key"] == "audio_intensity" and r["value"] > 0.9 for r in best["reasons"])

    signals = client.get(f"/api/recordings/{rec['id']}/signals").json()
    assert len(signals["rms_db"]) >= 70
    loudest = max(range(len(signals["rms_db"])), key=lambda i: signals["rms_db"][i])
    assert 17 <= loudest * signals["window_s"] <= 21
    assert client.get(f"/api/recordings/{rec['id']}").json()["status"] == "analyzed"

    # approve it, re-analyze: reviewed candidate stays and is not duplicated
    client.patch(f"/api/candidates/{best['id']}", json={"status": "approved"})
    again = finish(client, client.post(f"/api/recordings/{rec['id']}/analyze", json={"level": "leve"}).json())
    assert again["state"] == "succeeded"
    after = client.get("/api/candidates", params={"recording_id": rec["id"]}).json()
    assert [c["id"] for c in after if c["status"] == "approved"] == [best["id"]]
    assert len(after) == 1


def test_analysis_with_scene_detection_runs(client, tmp_path):
    video = make_test_video(tmp_path / "cenas.mp4", seconds=20, burst=(8, 10))
    rec = import_video(client, video)
    done = finish(client, client.post(f"/api/recordings/{rec['id']}/analyze",
                                      json={"level": "leve", "scenes": True}).json())
    assert done["state"] == "succeeded", done["error"]
    assert done["result"]["scene_events"] is not None
    assert "scenes" in client.get(f"/api/recordings/{rec['id']}/signals").json()


def test_analysis_without_audio_fails_clearly(client, tmp_path):
    video = make_test_video(tmp_path / "mudo.mp4", seconds=5, with_audio=False)
    rec = import_video(client, video)
    assert any("sem faixa de áudio" in w or "não tem faixa de áudio" in w for w in rec["warnings"])
    done = finish(client, client.post(f"/api/recordings/{rec['id']}/analyze", json={"level": "leve"}).json())
    assert done["state"] == "failed" and "faixa de áudio" in done["error"]
    assert client.get(f"/api/recordings/{rec['id']}").json()["status"] == "imported"


@pytest.mark.skipif(importlib.util.find_spec("faster_whisper") is not None, reason="faster-whisper is installed")
def test_transcription_levels_are_refused_when_the_engine_is_missing(client, tmp_path):
    video = make_test_video(tmp_path / "a.mp4", seconds=5)
    rec = import_video(client, video)
    refused = client.post(f"/api/recordings/{rec['id']}/analyze", json={"level": "padrao"})
    assert refused.status_code == 422 and "Transcrição indisponível" in refused.json()["error"]["message"]
    levels = client.get("/api/analysis/levels").json()
    assert levels["provider_ready"] is False and "padrao" in levels["levels"]


def test_render_preview_and_final_with_all_layouts(client, tmp_path):
    video = make_test_video(tmp_path / "game.mp4", seconds=10)
    rec = import_video(client, video)
    clip = client.post("/api/clips", json={"recording_id": rec["id"], "start_s": 2, "end_s": 8, "title": "Teste"}).json()
    url = f"/api/clips/{clip['id']}"
    patched = client.patch(url, json={
        "render_config": {"width": 360, "height": 640, "preset": "ultrafast", "crf": 28},
        "subtitles": [{"start": 0.5, "end": 3.0, "text": "olha esse clutch aqui"}],
    })
    assert patched.status_code == 200, patched.text

    plan = client.get(f"{url}/render-plan").json()
    assert "-filter_complex" in plan["command"] and plan["output_size"] == "360x640"

    tools = FFmpegTools.discover()
    ass_available = "ass" in tools.filters()

    preview_job = finish(client, client.post(f"{url}/render", json={"mode": "preview"}).json())
    assert preview_job["state"] == "succeeded", preview_job["error"]
    clip_after = client.get(url).json()
    assert clip_after["has_preview"] is True and clip_after["status"] == "draft"
    info = tools.probe(Path(clip_after["preview_path"]))
    assert (info.width, info.height) == (540, 960)

    for layout in ("blur", "solid", "fill"):
        client.patch(url, json={"render_config": {"layout": layout}})
        job = finish(client, client.post(f"{url}/render", json={"mode": "final"}).json())
        assert job["state"] == "succeeded", f"{layout}: {job['error']}"
        if layout == "blur" and not ass_available:
            assert "Legendas não aplicadas" in (job["message"] or "")
        out = client.get(url).json()
        assert out["status"] == "ready" and out["has_output"] is True and out["output_size"] > 1000
        probed = tools.probe(Path(out["output_path"]))
        assert (probed.width, probed.height) == (360, 640)
        assert probed.duration_s == pytest.approx(6, abs=0.7) and probed.audio_streams == 1

    served = client.get(f"{url}/file", params={"download": True})
    assert served.status_code == 200 and "attachment" in served.headers["content-disposition"]
    assert Path(out["output_path"]).parent == Path(client.get("/api/settings").json()["effective_output_dir"])
    assert video.exists()
    leftovers = list(Path(out["output_path"]).parent.glob("*.part"))
    assert leftovers == []

    # exports are tracked so the cleanup tool can find them (and only them)
    kinds = {a["kind"] for a in client.get("/api/cleanup/preview").json()["artifacts"]}
    assert {"export", "preview"} <= kinds


def frame_md5(ffmpeg: str, video: str, at: float) -> str:
    """MD5 of the decoded frame at `at` seconds - changes when anything is drawn on the picture."""
    import subprocess

    out = subprocess.run(
        [ffmpeg, "-nostdin", "-v", "error", "-ss", str(at), "-i", str(video), "-frames:v", "1", "-f", "framemd5", "-"],
        capture_output=True, text=True, check=True, timeout=60,
    ).stdout
    rows = [line for line in out.splitlines() if line and not line.startswith("#")]
    return rows[-1].split(",")[-1].strip()


def test_subtitles_are_really_burned_into_the_rendered_video(client, tmp_path):
    """The earlier suite passed while subtitles were silently skipped: prove the text is drawn on the frame."""
    tools = FFmpegTools.discover()
    if "ass" not in tools.filters():
        pytest.skip("this FFmpeg build has no libass ('ass' filter)")
    video = make_test_video(tmp_path / "legenda.mp4", seconds=6)
    rec = import_video(client, video)
    clip = client.post("/api/clips", json={"recording_id": rec["id"], "start_s": 0, "end_s": 6}).json()
    url = f"/api/clips/{clip['id']}"
    cues = [{"start": 0.2, "end": 5.5, "text": "olha esse clutch aqui agora"}]
    base = {"width": 360, "height": 640, "preset": "ultrafast", "crf": 28, "layout": "solid"}
    saved = client.patch(url, json={"subtitles": cues, "render_config": {**base, "subtitles": False}})
    assert saved.status_code == 200, saved.text

    def render_and_hash():
        job = finish(client, client.post(f"{url}/render", json={"mode": "final"}).json())
        assert job["state"] == "succeeded", job["error"]
        path = client.get(url).json()["output_path"]
        return job, frame_md5(tools.ffmpeg, path, 1.5)

    _, plain_a = render_and_hash()
    _, plain_b = render_and_hash()
    assert plain_a == plain_b, "encoding must be deterministic for this comparison to mean anything"

    client.patch(url, json={"render_config": {"subtitles": True}})
    plan = client.get(f"{url}/render-plan").json()
    assert plan["subtitles_applied"] is True and "ass=filename=subs.ass" in plan["filter_graph"]
    job, with_subtitles = render_and_hash()
    assert "Legendas não aplicadas" not in (job["message"] or "")
    if with_subtitles == plain_a:
        pytest.fail(
            "the subtitle text was not drawn on the video\n"
            f"job message={job['message']!r}\nresult={job['result']!r}\n"
            + diagnose_missing_subtitles(tools, plan, tmp_path, plain_a)
        )


def diagnose_missing_subtitles(tools, plan, tmp_path, plain_md5) -> str:
    """Re-run pieces of the render outside the app to find which layer loses the subtitles."""
    import subprocess

    script = plan["ass"] or ""
    (tmp_path / "subs.ass").write_text(script, encoding="utf-8")

    def run(args):
        proc = subprocess.run(args, capture_output=True, text=True, cwd=str(tmp_path), timeout=120)
        rows = [line for line in proc.stdout.splitlines() if line and not line.startswith("#")]
        digest = rows[-1].split(",")[-1].strip() if rows and "," in rows[-1] else ""
        return digest, proc.stderr[-800:]

    black = [tools.ffmpeg, "-nostdin", "-hide_banner", "-v", "warning", "-f", "lavfi", "-i", "color=c=black:s=360x640:r=10:d=3"]
    tail = ["-ss", "1.5", "-frames:v", "1", "-f", "framemd5", "-"]
    blank, _ = run(black + tail)
    drawn_a, err_a = run(black + ["-vf", "ass=filename=subs.ass"] + tail)

    command = list(plan["command"])
    command[-1] = str(tmp_path / "direct.mp4")
    proc = subprocess.run(command, capture_output=True, text=True, cwd=str(tmp_path), timeout=120)
    direct, _ = run([tools.ffmpeg, "-nostdin", "-v", "error", "-ss", "1.5", "-i", str(tmp_path / "direct.mp4"),
                     "-frames:v", "1", "-f", "framemd5", "-"])
    return (
        f"[A] app's ASS script alone on a black frame at 1.5s: drawn={drawn_a != blank} stderr={err_a!r}\n"
        f"[B] app's exact command run directly: rc={proc.returncode} drawn={direct != plain_md5} stderr={proc.stderr[-600:]!r}\n"
        f"ASS script head:\n{chr(10).join(script.splitlines()[:16])}"
    )


def test_libass_draws_text_with_the_installed_ffmpeg(tmp_path):
    """Isolates FFmpeg+libass+fonts from the rest of the pipeline: draw big text on a black frame."""
    import subprocess

    from vcs.media.subtitles import build_ass
    from vcs.models import SubtitleStyle

    tools = FFmpegTools.discover()
    if "ass" not in tools.filters():
        pytest.skip("this FFmpeg build has no libass ('ass' filter)")
    cue = {"start": 0.0, "end": 3.0, "text": "TESTE DE LEGENDA", "words": None}
    style = SubtitleStyle(highlight_words=False, size_pct=8)
    (tmp_path / "s.ass").write_text(build_ass([cue], style, 360, 640), encoding="utf-8")

    def first_frame_md5(extra: list[str]) -> tuple[str, str]:
        proc = subprocess.run(
            [tools.ffmpeg, "-nostdin", "-hide_banner", "-v", "warning", "-f", "lavfi", "-i", "color=c=black:s=360x640:r=10:d=2",
             *extra, "-frames:v", "1", "-f", "framemd5", "-"],
            capture_output=True, text=True, cwd=str(tmp_path), timeout=60,
        )
        rows = [line for line in proc.stdout.splitlines() if line and not line.startswith("#")]
        return (rows[-1].split(",")[-1].strip() if rows else ""), proc.stderr

    plain, _ = first_frame_md5([])
    drawn, stderr = first_frame_md5(["-vf", "ass=filename=s.ass"])
    assert drawn and drawn != plain, f"libass drew nothing. FFmpeg stderr:\n{stderr[-1500:]}"


def test_render_refuses_unavailable_encoder_and_missing_source(client, tmp_path):
    video = make_test_video(tmp_path / "x.mp4", seconds=6)
    rec = import_video(client, video)
    clip = client.post("/api/clips", json={"recording_id": rec["id"], "start_s": 0, "end_s": 5}).json()
    url = f"/api/clips/{clip['id']}"
    encoders = FFmpegTools.discover().encoders()
    missing = next((e for e in ("h264_qsv", "h264_nvenc", "h264_amf") if e not in encoders), None)
    if missing:
        client.patch(url, json={"render_config": {"encoder": missing}})
        refused = client.post(f"{url}/render", json={"mode": "final"})
        assert refused.status_code == 422 and missing in refused.json()["error"]["message"]
        client.patch(url, json={"render_config": {"encoder": "libx264"}})
    video.unlink()
    assert client.post(f"{url}/render", json={"mode": "final"}).status_code == 422


def test_encoder_test_endpoint_and_doctor(client, app_config):
    result = client.post("/api/system/test-encoder", json={"encoder": "libx264"}).json()
    assert result["ok"] is True, result["detail"]
    assert client.post("/api/system/test-encoder", json={"encoder": "rm"}).status_code == 422
    checks = {c["name"]: c for c in run_checks(app_config)}
    assert checks["FFmpeg"]["status"] == "OK" and checks["ffprobe"]["status"] == "OK"
    assert checks["Encoder libx264 (CPU)"]["status"] == "OK"
