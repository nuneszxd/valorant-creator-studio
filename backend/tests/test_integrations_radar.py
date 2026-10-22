"""Twitch / YouTube / radar tests. Network is replaced by httpx.MockTransport with synthetic payloads
that exist ONLY in these tests (the app itself never fabricates data)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from vcs.config import AppConfig
from vcs.errors import InvalidInput
from vcs.integrations.twitch import (
    TwitchClient,
    parse_duration,
    parse_twitch_url,
    resolve_link,
)
from vcs.main import create_app
from vcs.models import CreatorProfile
from vcs.radar.analyzer import analyze_items, confidence_for, theme_shares
from vcs.radar.youtube import YouTubeClient, extract_hashtags, parse_iso_duration

from .conftest import wait_for


def test_parse_twitch_url_variants():
    assert parse_twitch_url("https://www.twitch.tv/videos/123456789") == {"kind": "vod", "id": "123456789"}
    assert parse_twitch_url("twitch.tv/videos/42?t=1h2m") == {"kind": "vod", "id": "42"}
    assert parse_twitch_url("https://www.twitch.tv/Some_Streamer") == {"kind": "channel", "login": "some_streamer"}
    assert parse_twitch_url("https://clips.twitch.tv/AbcDef-123")["kind"] == "clip"
    for bad in ("", "https://example.com/videos/1", "https://www.twitch.tv/videos", "https://www.twitch.tv/directory"):
        with pytest.raises(InvalidInput):
            parse_twitch_url(bad)


def test_parse_durations():
    assert parse_duration("3h2m1s") == 3 * 3600 + 2 * 60 + 1
    assert parse_duration("45s") == 45 and parse_duration("12m") == 720
    assert parse_duration("") is None and parse_duration("abc") is None
    assert parse_iso_duration("PT1M5S") == 65 and parse_iso_duration("PT1H") == 3600
    assert parse_iso_duration("P0D") is None and parse_iso_duration(None) is None


def twitch_handler(request: httpx.Request) -> httpx.Response:
    if request.url.host == "id.twitch.tv":
        return httpx.Response(200, json={"access_token": "tok-test", "expires_in": 3600})
    assert request.headers["Authorization"] == "Bearer tok-test" and request.headers["Client-Id"] == "cid"
    if request.url.path == "/helix/videos":
        if request.url.params["id"] == "111":
            return httpx.Response(200, json={"data": [{
                "id": "111", "title": "Ranked Valorant", "user_name": "Streamer", "user_login": "streamer",
                "created_at": "2026-01-01T10:00:00Z", "url": "https://www.twitch.tv/videos/111",
                "view_count": 50, "duration": "1h0m0s", "type": "archive", "language": "pt",
                "thumbnail_url": "", "muted_segments": [{"duration": 30, "offset": 100}]}]})
        return httpx.Response(200, json={"data": []})
    if request.url.path == "/helix/streams":
        return httpx.Response(200, json={"data": [{"title": "ao vivo"}] if request.url.params["user_login"] == "live" else []})
    if request.url.path == "/helix/games":
        return httpx.Response(200, json={"data": [{"id": "516575", "name": "VALORANT"}]})
    if request.url.path == "/helix/clips":
        assert request.url.params["game_id"] == "516575"
        return httpx.Response(200, json={"data": [
            {"id": "c1", "url": "https://clips.twitch.tv/c1", "title": "clutch 1v3 insano", "broadcaster_name": "A",
             "created_at": "2026-02-01T00:00:00Z", "duration": 28.0, "view_count": 900, "language": "pt"},
            {"id": "c2", "url": "https://clips.twitch.tv/c2", "title": "ace no ascent", "broadcaster_name": "B",
             "created_at": "2026-02-01T01:00:00Z", "duration": 20.0, "view_count": 500, "language": "en"},
        ], "pagination": {}})
    return httpx.Response(404)


def test_twitch_client_and_resolve_link_flows():
    client = TwitchClient("cid", "secret", transport=httpx.MockTransport(twitch_handler))
    vod = resolve_link(client, "https://www.twitch.tv/videos/111")
    assert vod["metadata_available"] and vod["video"]["duration_s"] == 3600
    assert vod["can_download_via_api"] is False
    assert any("silenciados" in m for m in vod["messages"]) and vod["download_steps"]
    missing = resolve_link(client, "https://www.twitch.tv/videos/222")
    assert missing["metadata_available"] is False and any("expirar" in m or "expirado" in m for m in missing["messages"])
    live = resolve_link(client, "https://www.twitch.tv/live")
    assert live["live"]["is_live"] is True
    offline = resolve_link(client, "https://www.twitch.tv/offline")
    assert offline["live"]["is_live"] is False
    anonymous = resolve_link(None, "https://www.twitch.tv/videos/111")
    assert anonymous["metadata_available"] is False and any("TWITCH_CLIENT_ID" in m for m in anonymous["messages"])
    client.close()


def test_twitch_auth_failure_has_friendly_message():
    def reject(request):
        return httpx.Response(401, json={"message": "invalid client"})

    client = TwitchClient("cid", "bad", transport=httpx.MockTransport(reject))
    with pytest.raises(Exception) as info:
        client.get_video("1")
    assert "recusou as credenciais" in info.value.message and "bad" not in info.value.message


@pytest.fixture
def twitch_client(tmp_path):
    config = AppConfig(data_dir=tmp_path / "data", frontend_dist=tmp_path / "nodist",
                       twitch_client_id="cid", twitch_client_secret="secret-value")
    app = create_app(config)
    app.state.ctx.http_transport = httpx.MockTransport(twitch_handler)
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def test_resolve_endpoint_never_offers_download(twitch_client):
    data = twitch_client.post("/api/imports/twitch/resolve", json={"url": "https://www.twitch.tv/videos/111"}).json()
    assert data["video"]["title"] == "Ranked Valorant" and data["can_download_via_api"] is False
    assert twitch_client.post("/api/imports/twitch/resolve", json={"url": "lixo"}).status_code == 422
    assert "secret-value" not in json.dumps(data)


def test_resolve_endpoint_without_credentials(client):
    data = client.post("/api/imports/twitch/resolve", json={"url": "https://www.twitch.tv/videos/111"}).json()
    assert data["metadata_available"] is False and data["download_steps"]


def test_twitch_clips_collection_end_to_end(twitch_client):
    status = twitch_client.get("/api/radar/status").json()
    assert status["twitch"]["configured"] is True and status["youtube"]["configured"] is False
    job = twitch_client.post("/api/radar/runs/twitch-clips", json={"days": 7, "pages": 1, "language": "pt"}).json()
    wait_for(lambda: twitch_client.get(f"/api/jobs/{job['id']}").json()["state"] in ("succeeded", "failed"))
    finished = twitch_client.get(f"/api/jobs/{job['id']}").json()
    assert finished["state"] == "succeeded", finished["error"]
    runs = twitch_client.get("/api/radar/runs").json()
    assert runs[0]["source"] == "twitch_clips" and runs[0]["status"] == "done" and runs[0]["sample_size"] == 1
    items = twitch_client.get("/api/radar/items", params={"run_id": runs[0]["id"]}).json()
    assert [i["external_id"] for i in items] == ["c1"]  # the English clip was filtered out by language


def test_youtube_not_configured_is_a_clear_error(client):
    response = client.post("/api/radar/runs/youtube", json={})
    assert response.status_code == 422 and "YOUTUBE_API_KEY" in response.json()["error"]["message"]


def youtube_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["x-goog-api-key"] == "yt-key-123"
    assert "yt-key-123" not in str(request.url)  # the key must never travel in the URL
    if request.url.path.endswith("/search"):
        query = request.url.params["q"]
        assert request.url.params["regionCode"] == "BR" and request.url.params["videoDuration"] == "short"
        ids = ["a1", "a2", "a3"] if query == "valorant" else ["a3", "a4"]
        return httpx.Response(200, json={"items": [{"id": {"videoId": i}} for i in ids]})
    ids = request.url.params["id"].split(",")
    now = datetime.now(timezone.utc)
    def video(i, n):
        return {"id": i, "snippet": {"title": f"Clutch 1v3 no Ascent #valorant #clutch {i}", "channelTitle": "Canal",
                                     "publishedAt": (now - timedelta(days=n)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "tags": ["valorant"], "description": "desc #ranked"},
                "contentDetails": {"duration": "PT30S"},
                "statistics": {"viewCount": str(1000 * n), "likeCount": "50", "commentCount": "5"}}
    return httpx.Response(200, json={"items": [video(i, k + 1) for k, i in enumerate(ids)]})


@pytest.fixture
def youtube_client(tmp_path):
    config = AppConfig(data_dir=tmp_path / "data", frontend_dist=tmp_path / "nodist", youtube_api_key="yt-key-123")
    app = create_app(config)
    app.state.ctx.http_transport = httpx.MockTransport(youtube_handler)
    with TestClient(app, base_url="http://127.0.0.1:8000") as test_client:
        yield test_client


def test_youtube_collection_tracks_quota_and_stores_dated_history(youtube_client):
    body = {"queries": ["valorant", "valorant clutch"], "pages": 1}
    job = youtube_client.post("/api/radar/runs/youtube", json=body).json()
    wait_for(lambda: youtube_client.get(f"/api/jobs/{job['id']}").json()["state"] in ("succeeded", "failed"))
    finished = youtube_client.get(f"/api/jobs/{job['id']}").json()
    assert finished["state"] == "succeeded", finished["error"]
    assert finished["result"]["items"] == 4  # a3 appears in both searches and is stored once

    status = youtube_client.get("/api/radar/status").json()
    assert status["youtube"]["quota"]["search_calls_used"] == 2
    assert status["youtube"]["quota"]["search_calls_remaining"] == 98

    run = youtube_client.get("/api/radar/runs").json()[0]
    assert run["status"] == "done" and run["collected_at"] and run["quota"]["search_calls"] == 2
    trends = youtube_client.get("/api/radar/trends", params={"run_id": run["id"]}).json()
    assert trends, "a collection must produce dated trends"
    for trend in trends:
        assert trend["collected_at"] == run["collected_at"] and trend["source"] == "youtube"
        assert set(trend["observed"]) == {"observed", "estimated", "hypotheses"}
        assert trend["confidence"] in ("muito baixa", "baixa", "média")

    # a second collection keeps the first one as history
    job2 = youtube_client.post("/api/radar/runs/youtube", json=body).json()
    wait_for(lambda: youtube_client.get(f"/api/jobs/{job2['id']}").json()["state"] == "succeeded")
    assert len(youtube_client.get("/api/radar/runs").json()) == 2
    latest = youtube_client.get("/api/radar/trends", params={"latest": True}).json()
    assert {t["run_id"] for t in latest} == {youtube_client.get("/api/radar/runs").json()[0]["id"]}


def test_youtube_refuses_collections_that_exceed_the_daily_quota(youtube_client):
    youtube_client.patch("/api/settings", json={"youtube_search_daily_limit": 1})
    job = youtube_client.post("/api/radar/runs/youtube", json={"queries": ["a", "b"]}).json()
    wait_for(lambda: youtube_client.get(f"/api/jobs/{job['id']}").json()["state"] == "failed")
    assert "restam" in youtube_client.get(f"/api/jobs/{job['id']}").json()["error"]
    assert youtube_client.get("/api/radar/status").json()["youtube"]["quota"]["search_calls_used"] == 0


def test_youtube_helpers():
    assert extract_hashtags("Clutch #Valorant #valorant", "x #Ranked") == ["valorant", "ranked"]
    client = YouTubeClient("k", transport=httpx.MockTransport(lambda r: httpx.Response(
        403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}})))
    with pytest.raises(Exception) as info:
        client.search("x", region="BR", language="pt", published_after="2026-01-01T00:00:00Z", order="viewCount",
                      duration="short")
    assert "cota diária" in info.value.message


# --------------------------------------------------------------------------- analyzer


def item(title, views, days_old=3, duration=30, hashtags=None, now=None):
    now = now or datetime(2026, 3, 1, tzinfo=timezone.utc)
    return {"title": title, "views": views, "duration_s": duration, "hashtags": hashtags or [],
            "published_at": (now - timedelta(days=days_old)).isoformat(), "url": f"https://example.test/{abs(hash(title)) % 999}",
            "channel": "c"}


def test_analyzer_separates_observed_estimated_and_hypotheses_and_caps_confidence():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    items = (
        [item(f"Clutch 1v{i % 4 + 1} absurdo", 5000 + i * 100, hashtags=["valorant", "clutch"], now=now) for i in range(20)]
        + [item(f"Dica de lineup no Ascent {i}", 800, duration=50, hashtags=["valorant"], now=now) for i in range(6)]
        + [item("Ranked Diamante para Imortal ep 1", 1200, now=now), item("Ranked jornada ep 2", 900, now=now),
           item("Ranked elo subindo ep 3", 700, now=now)]
    )
    trends = analyze_items(
        items, source="youtube", source_url="https://youtube.test", collected_at=now.isoformat(),
        profile=CreatorProfile(rank_current="Diamante 2", rank_target="Imortal 1", preferred_types=["clutch"]),
        sample_note="amostra de teste",
    )
    by_label = {t["label"]: t for t in trends}
    clutch = by_label["Clutch / situação de desvantagem"]
    assert clutch["observed"]["observed"]["videos_com_o_tema"] == 20
    assert clutch["observed"]["estimated"]["mediana_visualizacoes_por_dia"] is not None
    assert clutch["observed"]["hypotheses"] and clutch["sample_size"] == 20
    assert clutch["confidence"] == "média"  # never above "média"
    assert "amostra de teste" in clutch["limitations"] and clutch["source_url"] == "https://youtube.test"
    assert by_label["Dicas / guias / lineups"]["confidence"] == "baixa"  # n=6
    assert any(t["kind"] == "hashtag" for t in trends) and any(t["kind"] == "duracao" for t in trends)
    assert {t["evidence"] for t in trends} == {"observado"}
    assert all(t["confidence"] != "alta" for t in trends)
    assert analyze_items([], source="x", source_url=None, collected_at=now.isoformat(), profile=CreatorProfile(),
                         sample_note="") == []


def test_analyzer_detects_theme_shift_between_collections():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    before = [item(f"Clutch {i}", 100, now=now) for i in range(5)] + [item(f"Outro vídeo {i}", 100, now=now) for i in range(25)]
    after = [item(f"Clutch {i}", 100, now=now) for i in range(18)] + [item(f"Outro vídeo {i}", 100, now=now) for i in range(12)]
    previous = {"collected_at": "2026-02-01T00:00:00+00:00", "n": 30, "theme_share": theme_shares(before)}
    trends = analyze_items(after, source="youtube", source_url=None, collected_at=now.isoformat(),
                           profile=CreatorProfile(), sample_note="x", previous=previous)
    change = next(t for t in trends if t["kind"] == "mudanca")
    assert change["observed"]["observed"]["coleta_anterior"] == "2026-02-01T00:00:00+00:00"
    assert any(c["variacao_pontos_percentuais"] > 0 for c in change["observed"]["observed"]["mudancas"])


def test_confidence_levels():
    assert [confidence_for(n) for n in (1, 5, 14, 15, 500)] == ["muito baixa", "baixa", "baixa", "média", "média"]


def test_manual_observations_and_analysis(client):
    assert client.post("/api/radar/manual/analyze").status_code == 422
    for i in range(4):
        created = client.post("/api/radar/manual", json={
            "platform": "tiktok", "title": f"Clutch 1v3 no Ascent {i}", "views": 1000 + i, "hashtags": ["#Valorant"],
            "format": "clutch", "hook": "pergunta", "duration_s": 25, "url": "https://www.tiktok.com/@x/video/1"})
        assert created.status_code == 201
    assert created.json()["hashtags"] == ["valorant"] and created.json()["manual"] == 1
    assert len(client.get("/api/radar/items", params={"manual": True}).json()) == 4
    result = client.post("/api/radar/manual/analyze").json()
    assert result["items"] == 4
    runs = client.get("/api/radar/runs", params={"source": "manual"}).json()
    assert runs and runs[0]["status"] == "done"
    assert client.delete(f"/api/radar/manual/{created.json()['id']}").status_code == 200
