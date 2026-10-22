"""API tests for candidates, clips, copy, publications, ideas, cleanup (no ffmpeg required)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from vcs.copywriting.generator import CopyInput, generate_copy, short_quote
from vcs.reports import build_report, duration_bucket


def new_candidate(client, recording, **overrides):
    body = {"recording_id": recording["id"], "start_s": 30, "end_s": 60, "title": "Teste", "moment_type": "clutch"}
    body.update(overrides)
    response = client.post("/api/candidates", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- candidates


def test_candidate_create_validation_and_listing(client, recording):
    cand = new_candidate(client, recording)
    assert cand["manual"] is True and cand["status"] == "pending" and cand["duration_s"] == 30

    assert client.post("/api/candidates", json={"recording_id": recording["id"], "start_s": 10, "end_s": 11}).status_code == 422
    assert client.post("/api/candidates", json={"recording_id": recording["id"], "start_s": 10, "end_s": 500}).status_code == 422
    assert client.post("/api/candidates", json={"recording_id": recording["id"], "start_s": 100, "end_s": 140}).status_code == 422
    assert client.post("/api/candidates", json={"recording_id": recording["id"], "start_s": 1, "end_s": 20,
                                                "moment_type": "inexistente"}).status_code == 422
    assert client.post("/api/candidates", json={"recording_id": 999, "start_s": 1, "end_s": 20}).status_code == 404

    listed = client.get("/api/candidates", params={"recording_id": recording["id"]}).json()
    assert [c["id"] for c in listed] == [cand["id"]]
    assert listed[0]["recording_name"] == recording["name"] and listed[0]["recording_map"] == "Ascent"
    assert client.get("/api/candidates", params={"type": "tilt"}).json() == []
    assert client.get("/api/candidates", params={"status": "pending", "map": "Ascent"}).json()


def test_candidate_review_flow_and_feedback_fields(client, recording):
    cand = new_candidate(client, recording)
    url = f"/api/candidates/{cand['id']}"
    patched = client.patch(url, json={"status": "approved", "outcome": "good", "title": "Novo título",
                                      "start_s": 28, "end_s": 62, "tags": ["ranked"]}).json()
    assert patched["status"] == "approved" and patched["status_label"] == "aprovado"
    assert patched["outcome"] == "good" and patched["outcome_label"] == "bom"
    assert patched["start_s"] == 28 and patched["tags"] == ["ranked"]

    assert client.patch(url, json={"start_s": 70, "end_s": 71}).status_code == 422
    assert client.patch(url, json={"status": "banana"}).status_code == 422
    assert client.patch(url, json={"title": None}).status_code == 422
    cleared = client.patch(url, json={"outcome": None}).json()
    assert cleared["outcome"] is None

    detail = client.get(url).json()
    assert detail["recording"]["id"] == recording["id"] and detail["clip_id"] is None
    assert client.delete(url).status_code == 200
    assert client.get(url).status_code == 404


# --------------------------------------------------------------------------- clips + copy


def test_clip_from_candidate_approves_and_is_idempotent(client, recording):
    cand = new_candidate(client, recording)
    first = client.post("/api/clips", json={"candidate_id": cand["id"]})
    assert first.status_code == 201
    clip = first.json()
    assert clip["status"] == "draft" and clip["start_s"] == 30 and clip["render_config"]["width"] == 1080
    assert client.get(f"/api/candidates/{cand['id']}").json()["status"] == "approved"
    again = client.post("/api/clips", json={"candidate_id": cand["id"]}).json()
    assert again["id"] == clip["id"]
    assert client.get(f"/api/candidates/{cand['id']}").json()["clip_id"] == clip["id"]


def test_clip_patch_merges_config_validates_and_builds_subtitles(client, recording, ctx):
    clip = client.post("/api/clips", json={"recording_id": recording["id"], "start_s": 10, "end_s": 40,
                                           "title": "Manual"}).json()
    url = f"/api/clips/{clip['id']}"
    ok = client.patch(url, json={"render_config": {"layout": "solid", "crf": 24},
                                 "subtitle_style": {"highlight_color": "#00FF00"},
                                 "facts": {"situation": "1v3", "result": "vitória", "round": ""}})
    assert ok.status_code == 200, ok.text
    body = ok.json()
    assert body["render_config"]["layout"] == "solid" and body["render_config"]["crf"] == 24
    assert body["render_config"]["width"] == 1080  # untouched
    assert body["subtitle_style"]["highlight_color"] == "#00FF00"
    assert body["facts"] == {"situation": "1v3", "result": "vitória"}

    assert client.patch(url, json={"render_config": {"width": 1001}}).status_code == 422
    assert client.patch(url, json={"render_config": {"encoder": "rm -rf"}}).status_code == 422
    assert client.patch(url, json={"subtitle_style": {"font": "Arial; rm"}}).status_code == 422
    assert client.patch(url, json={"facts": {"hack": "x"}}).status_code == 422
    assert client.patch(url, json={"start_s": 50, "end_s": 40}).status_code == 422

    cues = [{"start": 0.5, "end": 2.0, "text": "olha isso"}]
    assert client.patch(url, json={"subtitles": cues}).json()["subtitles"][0]["text"] == "olha isso"
    assert client.patch(url, json={"subtitles": [{"start": 3, "end": 2, "text": "x"}]}).status_code == 422
    assert client.patch(url, json={"subtitles": [{"start": 0, "end": 99, "text": "x"}]}).status_code == 422


def test_clip_subtitles_from_transcript(client, recording, ctx):
    clip = client.post("/api/clips", json={"recording_id": recording["id"], "start_s": 10, "end_s": 40}).json()
    url = f"/api/clips/{clip['id']}/subtitles/from-transcript"
    assert client.post(url).status_code == 409  # nothing transcribed yet
    ctx.repos.segments.replace_for_ranges(
        recording["id"], [(0, 100)],
        [{"start_s": 12.0, "end_s": 15.0, "text": "meu deus que clutch", "words": [
            {"start": 12.0, "end": 12.5, "text": "meu"}, {"start": 12.5, "end": 13.0, "text": "deus"},
            {"start": 13.0, "end": 14.0, "text": "que"}, {"start": 14.0, "end": 15.0, "text": "clutch"}]}],
    )
    cues = client.post(url).json()["subtitles"]
    assert cues[0]["start"] == 2.0 and cues[0]["text"] == "meu deus que clutch"
    plan = client.get(f"/api/clips/{clip['id']}/render-plan")
    assert plan.status_code in (200, 503)  # 503 only when ffmpeg is not installed


def test_copy_generation_api_uses_only_known_facts(client, recording):
    client.put("/api/profile", json={**client.get("/api/profile").json(), "rank_current": "Diamante 2",
                                     "rank_target": "Imortal 1", "series_name": "Rumo ao Imortal"})
    cand = new_candidate(client, recording, moment_type="clutch")
    clip = client.post("/api/clips", json={"candidate_id": cand["id"]}).json()
    client.patch(f"/api/clips/{clip['id']}", json={"facts": {"situation": "1v3", "result": "vitória"}})
    pack = client.post(f"/api/clips/{clip['id']}/copy/generate").json()["copy"]
    assert len(pack["hooks"]) == 3 and 1 <= len(pack["titles"]) <= 3
    assert any("1v3" in h for h in pack["hooks"])
    assert all(tag.startswith("#") for tag in pack["hashtags"]) and "#valorant" in pack["hashtags"]
    assert "#jett" in pack["hashtags"] and "#ascent" in pack["hashtags"] and "#diamante" in pack["hashtags"]
    assert "vitória" in pack["caption"] and "None" not in str(pack)
    assert client.get(f"/api/clips/{clip['id']}/copy").json()["copy"]["hooks"] == pack["hooks"]
    edited = client.put(f"/api/clips/{clip['id']}/copy", json={"hooks": ["meu gancho"], "caption": "x"}).json()["copy"]
    assert edited["hooks"] == ["meu gancho"] and edited["edited"] is True


def test_copy_generator_skips_templates_with_missing_facts_and_flags_unconfirmed_type():
    pack = generate_copy(CopyInput(moment_type="clutch", recording_name="a.mp4", start_s=5, end_s=35,
                                   confirmed_type=False, clip_id=1))
    assert len(pack["hooks"]) == 3
    assert not any("{" in h for h in pack["hooks"] + pack["titles"])
    assert not any("None" in h for h in pack["hooks"])
    assert any("confirme" in n for n in pack["notes"])
    assert any("situação" in n for n in pack["notes"])
    rich = generate_copy(CopyInput(moment_type="clutch", recording_name="a.mp4", start_s=5, end_s=35, map="Bind",
                                   agent="reyna", situation="1v2", quote="olha só isso", clip_id=2))
    assert any("1v2" in h for h in rich["hooks"] + rich["titles"])
    assert "#reyna" in rich["hashtags"] and "#bind" in rich["hashtags"]
    assert short_quote("um dois três quatro cinco seis sete oito nove dez onze", 4) == "um dois três quatro"


# --------------------------------------------------------------------------- publications


def pub(client, **overrides):
    body = {"platform": "tiktok", "format": "clutch", "views": 1000, "likes": 100, "comments": 10, "shares": 5,
            "published_at": "2026-01-01T12:00:00+00:00"}
    body.update(overrides)
    response = client.post("/api/publications", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def test_publication_crud_and_defaults_from_clip(client, recording):
    cand = new_candidate(client, recording, moment_type="engracado")
    clip = client.post("/api/clips", json={"candidate_id": cand["id"]}).json()
    created = pub(client, clip_id=clip["id"], format=None)
    assert created["duration_s"] == 30 and created["theme"] == "Momento engraçado"
    assert created["metrics_updated_at"]
    planned = pub(client, status="planned", views=None, likes=None, comments=None, shares=None,
                  planned_for="2026-02-01T10:00:00+00:00", published_at=None)
    assert planned["status_label"] == "planejada" and planned["published_at"] is None
    updated = client.patch(f"/api/publications/{created['id']}", json={"views": 5000, "feedback": "good"}).json()
    assert updated["views"] == 5000 and updated["feedback"] == "good"
    assert client.patch(f"/api/publications/{created['id']}", json={"platform": None}).status_code == 422
    assert client.post("/api/publications", json={"platform": "orkut"}).status_code == 422
    assert client.post("/api/publications", json={"platform": "tiktok", "retention_pct": 140}).status_code == 422
    assert len(client.get("/api/publications", params={"status": "published"}).json()) == 1
    assert client.delete(f"/api/publications/{created['id']}").status_code == 200


def test_report_api_and_caveats(client):
    for i in range(6):
        pub(client, format="clutch", views=1000 + i * 100)
    pub(client, format="engraçado", views=300)
    report = client.get("/api/reports/publications", params={"group_by": "format"}).json()
    groups = {g["group"]: g for g in report["groups"]}
    assert groups["clutch"]["n"] == 6 and groups["clutch"]["median_views"] == 1250
    assert any("Amostra pequena" in w for w in groups["engraçado"]["warnings"])
    assert not any("Amostra pequena" in w for w in groups["clutch"]["warnings"])
    assert "não prova" in report["reading_note"]
    assert client.get("/api/reports/publications", params={"group_by": "banana"}).status_code == 422


def test_build_report_flags_recent_and_dominant_videos():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    rows = [
        {"id": i, "status": "published", "format": "x", "views": v, "published_at": (now - timedelta(days=10)).isoformat(),
         "likes": 1, "comments": 0, "shares": 0}
        for i, v in enumerate([100, 110, 120, 130, 140, 5000], start=1)
    ]
    rows.append({"id": 99, "status": "published", "format": "x", "views": 90,
                 "published_at": (now - timedelta(hours=5)).isoformat()})
    report = build_report(rows, "format", now)
    warnings = report["groups"][0]["warnings"]
    assert any("menos de 48" in w for w in warnings)
    assert any("único vídeo" in w for w in warnings)
    assert report["overall"]["with_views"] == 7
    assert duration_bucket(20) == "15–30 s" and duration_bucket(None) == "(sem valor informado)"


# --------------------------------------------------------------------------- ideas


def test_ideas_suggestions_are_explained_and_crud_works(client, recording):
    client.put("/api/profile", json={**client.get("/api/profile").json(), "rank_current": "Diamante 2",
                                     "rank_target": "Imortal 1", "formats_to_try": ["clutch da live"],
                                     "preferred_types": ["clutch"]})
    for _ in range(3):
        new_candidate(client, recording, moment_type="clutch")
    data = client.post("/api/ideas/suggest").json()
    ideas = data["ideas"]
    assert ideas and ideas == sorted(ideas, key=lambda i: i["priority"], reverse=True)
    top = next(i for i in ideas if i["format"] == "clutch")
    kinds = {r["kind"] for r in top["reasons"]}
    assert {"hipotese", "perfil", "material"} <= kinds
    assert "não uma previsão" in top["priority_note"]
    assert any(i["format"] == "serie_jornada" and "Diamante 2" in i["title"] for i in ideas)

    saved = client.post("/api/ideas", json={"title": top["title"], "format": top["format"],
                                            "rationale": top["reasons"], "source": "sugestao"}).json()
    scripted = client.post(f"/api/ideas/{saved['id']}/script").json()
    assert len(scripted["script"]["beats"]) == 5 and scripted["script"]["beats"][0]["your_text"] == ""
    assert client.patch(f"/api/ideas/{saved['id']}", json={"status": "planned"}).json()["status_label"] == "planejada"
    assert client.delete(f"/api/ideas/{saved['id']}").status_code == 200
    assert client.get("/api/ideas/formats").json()["formats"]["clutch"]["title"]


# --------------------------------------------------------------------------- library + cleanup


def test_overview_and_facets(client, recording):
    new_candidate(client, recording)
    data = client.get("/api/overview").json()
    assert data["recordings"]["total"] == 1 and data["candidates"]["by_status"]["pending"] == 1
    assert data["top_pending_candidates"][0]["recording_name"] == recording["name"]
    assert set(data["setup"]) >= {"ffmpeg", "profile_filled", "has_recording", "integrations"}
    facets = client.get("/api/library/facets").json()
    assert "Ascent" in facets["maps"] and "Jett" in facets["agents"]


def test_cleanup_requires_confirmation_and_never_deletes_originals(client, ctx, recording, app_config):
    export = app_config.default_output_dir / "corte.mp4"
    export.parent.mkdir(parents=True, exist_ok=True)
    export.write_bytes(b"x" * 10)
    ctx.repos.artifacts.register("export", str(export), 10)
    original_artifact = ctx.repos.artifacts.insert(kind="export", path=recording["path"], size_bytes=16)
    partial = app_config.default_output_dir / "meio.mp4.part"
    partial.write_bytes(b"y")

    preview = client.get("/api/cleanup/preview").json()
    by_path = {a["path"]: a for a in preview["artifacts"]}
    assert by_path[str(export)]["deletable"] is True
    assert by_path[recording["path"]]["deletable"] is False
    assert any(p["path"] == str(partial) for p in preview["partials"])

    ids = [a["id"] for a in preview["artifacts"]]
    refused = client.post("/api/cleanup", json={"artifact_ids": ids})
    assert refused.status_code == 422 and export.exists()

    done = client.post("/api/cleanup", json={"artifact_ids": ids, "delete_partials": True, "confirm": True}).json()
    assert str(export) in done["deleted"] and str(partial) in done["deleted"]
    assert any(f["path"] == recording["path"] for f in done["failed"])
    assert not export.exists() and not partial.exists()
    from pathlib import Path

    assert Path(recording["path"]).exists()
    assert original_artifact["id"] in ids
