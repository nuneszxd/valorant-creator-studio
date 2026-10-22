"""Trend radar: official-API collections, manual observations, and the dated history of trends."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import Field, field_validator

from ..errors import Conflict, InvalidInput
from ..models import Count, OptionalUrl, Strict
from ..radar.collect import analyze_manual, collect_twitch_clips, collect_youtube, quota_status
from ..utils import utcnow
from .deps import Ctx

router = APIRouter(prefix="/api/radar", tags=["radar de tendências"])

SOURCE_INFO = {
    "youtube": "YouTube Data API v3 (oficial). Busca pública + estatísticas públicas; dentro da cota diária.",
    "twitch_clips": "Twitch API (oficial). Clipes públicos da categoria VALORANT mais vistos no período.",
    "manual": "Observações que você cadastrou (TikTok e outras fontes sem API pública utilizável).",
}
LIMITATIONS = [
    "TikTok: não há API pública de tendências utilizada aqui. Use o Creative Center manualmente e cadastre "
    "o que observar na aba 'Observações manuais'.",
    "Ganchos falados, edição e legendas dos vídeos de terceiros não são acessíveis por estas fontes.",
    "Toda amostra é parcial; a confiança nunca passa de 'média'.",
]


class YouTubeRunBody(Strict):
    queries: list[str] = Field(
        default_factory=lambda: ["valorant", "valorant clutch", "valorant ranked", "valorant brasil"],
        min_length=1, max_length=8,
    )
    region: str = Field("BR", pattern=r"^[A-Z]{2}$")
    language: str | None = Field("pt", pattern=r"^[a-z]{2,3}$")
    days: int = Field(14, ge=1, le=90)
    order: Literal["viewCount", "date", "relevance"] = "viewCount"
    duration: Literal["short", "medium", "long", "any"] = "short"
    pages: int = Field(1, ge=1, le=3)

    @field_validator("queries")
    @classmethod
    def _queries(cls, value: list[str]) -> list[str]:
        cleaned = [q.strip() for q in value if q.strip()]
        if not cleaned or any(len(q) > 80 for q in cleaned):
            raise ValueError("Informe de 1 a 8 consultas de até 80 caracteres.")
        return cleaned


class TwitchRunBody(Strict):
    days: int = Field(7, ge=1, le=30)
    pages: int = Field(2, ge=1, le=5)
    language: str | None = Field("pt", pattern=r"^[a-z]{2,3}$")


class ManualBody(Strict):
    platform: Literal["tiktok", "instagram", "youtube", "twitch", "kwai", "outro"]
    url: OptionalUrl = None
    title: str = Field(min_length=1, max_length=300)
    channel: str | None = Field(None, max_length=120)
    published_at: str | None = Field(None, max_length=40)
    duration_s: float | None = Field(None, ge=0, le=7200)
    views: Count | None = None
    likes: Count | None = None
    comments: Count | None = None
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    format: str | None = Field(None, max_length=80)
    hook: str | None = Field(None, max_length=200)
    edit_style: str | None = Field(None, max_length=200)
    caption_style: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=1000)
    observed_at: str | None = Field(None, max_length=40)


@router.get("/status")
def status(c: Ctx) -> dict:
    last = {}
    for source in ("youtube", "twitch_clips", "manual"):
        rows = c.repos.radar_runs.list("source = ? AND status = 'done'", (source,), order_by="id DESC", limit=1)
        last[source] = rows[0] if rows else None
    return {
        "youtube": {"configured": c.config.integrations()["youtube"], "quota": quota_status(c)},
        "twitch": {"configured": c.config.integrations()["twitch"]},
        "manual_items": c.repos.radar_items.count("manual = 1"),
        "last_runs": last,
        "sources": SOURCE_INFO,
        "limitations": LIMITATIONS,
    }


def _ensure_no_running(c: Any, kind: str) -> None:
    if c.repos.jobs.count("kind = ? AND state IN ('queued', 'running')", (kind,)):
        raise Conflict("Já existe uma coleta desse tipo em andamento.")


@router.post("/runs/youtube", status_code=202)
def run_youtube(body: YouTubeRunBody, c: Ctx) -> dict:
    if not c.config.integrations()["youtube"]:
        raise InvalidInput("Configure YOUTUBE_API_KEY no arquivo .env (veja docs/USAGE.md).")
    _ensure_no_running(c, "radar_youtube")
    params = body.model_dump()
    return c.jobs.submit("radar_youtube", "Coletar tendências no YouTube",
                         lambda ctx: collect_youtube(ctx, c, params), params=params)


@router.post("/runs/twitch-clips", status_code=202)
def run_twitch(body: TwitchRunBody, c: Ctx) -> dict:
    if not c.config.integrations()["twitch"]:
        raise InvalidInput("Configure TWITCH_CLIENT_ID e TWITCH_CLIENT_SECRET no arquivo .env (veja docs/USAGE.md).")
    _ensure_no_running(c, "radar_twitch")
    params = body.model_dump()
    return c.jobs.submit("radar_twitch", "Coletar clipes de VALORANT na Twitch",
                         lambda ctx: collect_twitch_clips(ctx, c, params), params=params)


@router.get("/runs")
def list_runs(c: Ctx, source: str | None = None, limit: int = Query(30, ge=1, le=200)) -> list[dict]:
    rows = c.repos.radar_runs.list("source = ?" if source else "", (source,) if source else (),
                                   order_by="id DESC", limit=limit)
    for row in rows:
        row["trends_count"] = c.repos.trends.count("run_id = ?", (row["id"],))
    return rows


@router.get("/runs/{run_id}")
def get_run(run_id: int, c: Ctx) -> dict:
    run = c.repos.radar_runs.require(run_id)
    run["trends_count"] = c.repos.trends.count("run_id = ?", (run_id,))
    run["items_count"] = c.repos.radar_items.count("run_id = ?", (run_id,))
    return run


@router.delete("/runs/{run_id}")
def delete_run(run_id: int, c: Ctx) -> dict:
    c.repos.radar_runs.require(run_id)
    c.repos.radar_runs.delete(run_id)
    return {"status": "removido"}


@router.get("/trends")
def list_trends(
    c: Ctx,
    run_id: int | None = None,
    source: str | None = None,
    kind: str | None = None,
    confidence: str | None = None,
    latest: bool = False,
    limit: int = Query(200, ge=1, le=500),
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    if source:
        clauses.append("source = ?")
        params.append(source)
    if kind:
        clauses.append("kind = ?")
        params.append(kind)
    if confidence:
        clauses.append("confidence = ?")
        params.append(confidence)
    if latest:
        clauses.append(
            "run_id IN (SELECT MAX(id) FROM radar_runs WHERE status = 'done' GROUP BY source)"
        )
    return c.repos.trends.list(" AND ".join(clauses), params, order_by="collected_at DESC, id ASC", limit=limit)


@router.get("/items")
def list_items(c: Ctx, run_id: int | None = None, manual: bool | None = None,
               limit: int = Query(200, ge=1, le=1000)) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    if run_id is not None:
        clauses.append("run_id = ?")
        params.append(run_id)
    if manual is not None:
        clauses.append("manual = ?")
        params.append(1 if manual else 0)
    return c.repos.radar_items.list(" AND ".join(clauses), params, order_by="id DESC", limit=limit)


@router.post("/manual", status_code=201)
def add_manual(body: ManualBody, c: Ctx) -> dict:
    """Register something you observed by hand (e.g. a TikTok seen in the Creative Center)."""
    observed_at = body.observed_at or utcnow()
    hashtags = [h.strip().lstrip("#").lower() for h in body.hashtags if h.strip()]
    return c.repos.radar_items.insert(
        run_id=None, platform=body.platform, url=body.url, title=body.title, channel=body.channel,
        published_at=body.published_at, duration_s=body.duration_s, views=body.views, likes=body.likes,
        comments=body.comments, hashtags=hashtags, tags=[], observed_at=observed_at, manual=1, notes=body.notes,
        extra={"format": body.format, "hook": body.hook, "edit_style": body.edit_style,
               "caption_style": body.caption_style},
    )


@router.delete("/manual/{item_id}")
def delete_manual(item_id: int, c: Ctx) -> dict:
    item = c.repos.radar_items.require(item_id)
    if not item["manual"]:
        raise InvalidInput("Só observações manuais podem ser removidas por aqui.")
    c.repos.radar_items.delete(item_id)
    return {"status": "removido"}


@router.post("/manual/analyze")
def analyze_manual_items(c: Ctx) -> dict:
    return analyze_manual(c)
