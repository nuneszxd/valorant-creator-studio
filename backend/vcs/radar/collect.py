"""Radar collection jobs (YouTube search, Twitch clips) and analysis of manual observations.

Only official APIs with the user's own credentials. Every item and trend keeps its source, link and
collection date, so earlier collections stay available as history.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..errors import AppError, InvalidInput
from ..integrations.twitch import make_twitch_client
from ..jobs.manager import JobCancelled
from ..security import error_text
from ..utils import utcnow
from .analyzer import analyze_items, theme_shares
from .youtube import YouTubeClient, extract_hashtags, quota_day

log = logging.getLogger(__name__)

SEARCH_SOURCE = "youtube_search"


def quota_status(app: Any) -> dict[str, Any]:
    day = quota_day()
    row = app.db.one("SELECT calls, units FROM quota_usage WHERE day = ? AND source = ?", (day, SEARCH_SOURCE))
    used = int(row["calls"]) if row else 0
    limit = app.settings.load().youtube_search_daily_limit
    return {"day": day, "search_calls_used": used, "search_calls_limit": limit,
            "search_calls_remaining": max(limit - used, 0)}


def _add_usage(app: Any, source: str, calls: int, units: int) -> None:
    app.db.execute(
        "INSERT INTO quota_usage (day, source, calls, units) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(day, source) DO UPDATE SET calls = calls + excluded.calls, units = units + excluded.units",
        (quota_day(), source, calls, units),
    )


def _previous_summary(app: Any, source: str, run_id: int, queries: list[str] | None) -> dict[str, Any] | None:
    rows = app.repos.radar_runs.list("source = ? AND status = 'done' AND id != ?", (source, run_id),
                                     order_by="id DESC", limit=1)
    if not rows:
        return None
    previous = rows[0]
    summary = (previous.get("params") or {}).get("summary")
    if not summary:
        return None
    if queries is not None and (previous.get("params") or {}).get("queries") != queries:
        return None
    return {"collected_at": previous["collected_at"], "n": summary.get("n", 0),
            "theme_share": summary.get("theme_share") or {}}


def _store_items(app: Any, run_id: int, platform: str, observed_at: str, items: list[dict[str, Any]]) -> None:
    for item in items:
        app.repos.radar_items.insert(
            run_id=run_id, platform=platform, external_id=item.get("external_id"), url=item.get("url"),
            title=item.get("title"), channel=item.get("channel"), published_at=item.get("published_at"),
            duration_s=item.get("duration_s"), views=item.get("views"), likes=item.get("likes"),
            comments=item.get("comments"), language=item.get("language"), tags=item.get("tags") or [],
            hashtags=item.get("hashtags") or [], query=item.get("query"), observed_at=observed_at, manual=0,
            extra=item.get("extra"),
        )


def _finish(app: Any, run: dict[str, Any], items: list[dict[str, Any]], *, source: str, source_url: str | None,
            sample_note: str, quota: dict[str, Any], queries: list[str] | None) -> int:
    profile = app.settings.load_profile()
    previous = _previous_summary(app, source, run["id"], queries)
    trends = analyze_items(items, source=source, source_url=source_url, collected_at=run["collected_at"],
                           profile=profile, sample_note=sample_note, previous=previous)
    for trend in trends:
        app.repos.trends.insert(run_id=run["id"], **trend)
    params = dict(run.get("params") or {})
    params["summary"] = {"n": len(items), "theme_share": theme_shares(items)}
    app.repos.radar_runs.update(run["id"], status="done", finished_at=utcnow(), sample_size=len(items),
                                quota=quota, params=params)
    return len(trends)


def collect_youtube(ctx: Any, app: Any, params: dict[str, Any]) -> dict[str, Any]:
    key = app.config.youtube_api_key
    if not key:
        raise AppError("Configure YOUTUBE_API_KEY no arquivo .env para usar o radar do YouTube "
                       "(veja docs/USAGE.md).", code="not_configured")
    queries: list[str] = params["queries"]
    pages: int = params["pages"]
    needed = len(queries) * pages
    quota = quota_status(app)
    if needed > quota["search_calls_remaining"]:
        raise AppError(
            f"Esta coleta usaria {needed} buscas, mas restam {quota['search_calls_remaining']} hoje "
            f"(limite {quota['search_calls_limit']}). Reduza as consultas/páginas ou espere a cota renovar.",
            code="youtube_quota", status_code=429,
        )
    collected_at = utcnow()
    run = app.repos.radar_runs.insert(source="youtube", params=params, status="running",
                                      collected_at=collected_at, sample_size=0, job_id=ctx.job_id)
    client = YouTubeClient(key, transport=app.http_transport)
    published_after = (datetime.now(timezone.utc) - timedelta(days=params["days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        found: dict[str, list[str]] = {}
        calls = 0
        for query in queries:
            token = None
            for _page in range(pages):
                ctx.check_cancelled()
                ctx.set_progress(calls / needed, f"Buscando no YouTube: “{query}” ({calls + 1}/{needed})", force=True)
                ids, token = client.search(
                    query, region=params["region"], language=params.get("language"),
                    published_after=published_after, order=params["order"], duration=params["duration"],
                    page_token=token,
                )
                calls += 1
                _add_usage(app, SEARCH_SOURCE, 1, 0)
                for vid in ids:
                    found.setdefault(vid, []).append(query)
                if not token:
                    break
        ctx.check_cancelled()
        ctx.set_progress(None, "Lendo estatísticas públicas dos vídeos", force=True)
        details = client.videos(list(found))
        _add_usage(app, "youtube_other", -(-len(found) // 50), -(-len(found) // 50))
        items = []
        for detail in details:
            detail["query"] = (found.get(detail["external_id"]) or [""])[0]
            detail["extra"] = {"queries": found.get(detail["external_id"])}
            items.append(detail)
        _store_items(app, run["id"], "youtube", collected_at, items)
        first_query = queries[0].replace(" ", "+")
        trends = _finish(
            app, run, items, source="youtube",
            source_url=f"https://www.youtube.com/results?search_query={first_query}",
            sample_note=(f"Amostra de {len(items)} vídeos retornados por {len(queries)} busca(s) na API do YouTube "
                         f"(região {params['region']}, até {params['days']} dias, ordenados por "
                         f"{params['order']}); não é o conjunto de todos os vídeos."),
            quota={"search_calls": calls, **quota_status(app)}, queries=queries,
        )
    except JobCancelled:
        app.repos.radar_runs.update(run["id"], status="cancelled", finished_at=utcnow())
        raise
    except Exception as exc:
        app.repos.radar_runs.update(run["id"], status="error", finished_at=utcnow(),
                                    error=error_text(exc, app.config.secrets()))
        raise
    finally:
        client.close()
    return {"run_id": run["id"], "items": len(items), "trends": trends, "search_calls": calls}


def collect_twitch_clips(ctx: Any, app: Any, params: dict[str, Any]) -> dict[str, Any]:
    client = make_twitch_client(app.config, app.http_transport)
    if client is None:
        raise AppError("Configure TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET no arquivo .env para usar os clipes "
                       "da Twitch (veja docs/USAGE.md).", code="not_configured")
    collected_at = utcnow()
    run = app.repos.radar_runs.insert(source="twitch_clips", params=params, status="running",
                                      collected_at=collected_at, sample_size=0, job_id=ctx.job_id)
    try:
        ctx.set_progress(None, "Procurando a categoria VALORANT na Twitch", force=True)
        game_id = client.get_game_id("VALORANT")
        if not game_id:
            raise AppError("A Twitch não retornou a categoria VALORANT.")
        now = datetime.now(timezone.utc)
        started = (now - timedelta(days=params["days"])).strftime("%Y-%m-%dT%H:%M:%SZ")
        ended = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        clips: list[dict[str, Any]] = []
        cursor = None
        for page in range(params["pages"]):
            ctx.check_cancelled()
            ctx.set_progress(page / params["pages"], f"Lendo clipes públicos ({page + 1}/{params['pages']})", force=True)
            batch, cursor = client.get_clips(game_id, started, ended, first=100, after=cursor)
            clips.extend(batch)
            if not cursor:
                break
        language = params.get("language")
        items = []
        for clip in clips:
            if language and (clip.get("language") or "").lower() != language.lower():
                continue
            items.append({
                "external_id": clip.get("id"), "url": clip.get("url"), "title": clip.get("title"),
                "channel": clip.get("broadcaster_name"), "published_at": clip.get("created_at"),
                "duration_s": clip.get("duration"), "views": clip.get("view_count"),
                "language": clip.get("language"), "tags": [], "hashtags": extract_hashtags(clip.get("title")),
                "extra": {"creator": clip.get("creator_name"), "vod_offset": clip.get("vod_offset"),
                          "is_featured": clip.get("is_featured")},
            })
        _store_items(app, run["id"], "twitch_clip", collected_at, items)
        trends = _finish(
            app, run, items, source="twitch_clips",
            source_url="https://www.twitch.tv/directory/category/valorant/clips",
            sample_note=(f"Amostra de {len(items)} clipes públicos da categoria VALORANT"
                         f"{' em ' + language if language else ''}, dos últimos {params['days']} dias, "
                         "ordenados por visualizações pela API; clipes são curtos e escolhidos por quem assiste."),
            quota={}, queries=None,
        )
    except JobCancelled:
        app.repos.radar_runs.update(run["id"], status="cancelled", finished_at=utcnow())
        raise
    except Exception as exc:
        app.repos.radar_runs.update(run["id"], status="error", finished_at=utcnow(),
                                    error=error_text(exc, app.config.secrets()))
        raise
    finally:
        client.close()
    return {"run_id": run["id"], "items": len(items), "trends": trends}


def analyze_manual(app: Any) -> dict[str, Any]:
    """Analyze the observations typed in by hand (platforms without a usable API, e.g. TikTok)."""
    rows = app.repos.radar_items.list("manual = 1", order_by="id ASC")
    if len(rows) < 3:
        raise InvalidInput("Cadastre pelo menos 3 observações manuais para gerar uma análise.")
    collected_at = utcnow()
    run = app.repos.radar_runs.insert(source="manual", params={"item_ids": [r["id"] for r in rows]},
                                      status="running", collected_at=collected_at, sample_size=0)
    items = []
    for row in rows:
        item = dict(row)
        item["views"] = row.get("views")
        items.append(item)
    try:
        trends = _finish(
            app, run, items, source="manual", source_url=None,
            sample_note=("Observações registradas manualmente por você (links e números que você viu); "
                         "a seleção depende do que você escolheu observar."),
            quota={}, queries=None,
        )
    except Exception as exc:
        app.repos.radar_runs.update(run["id"], status="error", finished_at=utcnow(),
                                    error=error_text(exc, app.config.secrets()))
        raise
    return {"run_id": run["id"], "items": len(items), "trends": trends}
