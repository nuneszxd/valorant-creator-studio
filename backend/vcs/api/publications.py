"""Publication tracking (manual entry always works) and comparison reports."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import Field

from ..analysis.moment_types import MOMENT_TYPES
from ..errors import InvalidInput
from ..models import Strict
from ..reports import GROUP_FIELDS, build_report
from ..utils import utcnow
from .deps import Ctx

router = APIRouter(prefix="/api", tags=["publicações"])

PLATFORMS = Literal["tiktok", "instagram", "youtube", "twitch", "kwai", "outro"]
STATUS_LABELS = {"planned": "planejada", "published": "publicada"}


class PublicationBody(Strict):
    clip_id: int | None = None
    platform: PLATFORMS
    url: str | None = Field(None, max_length=500)
    status: Literal["planned", "published"] = "published"
    planned_for: str | None = Field(None, max_length=40)
    published_at: str | None = Field(None, max_length=40)
    format: str | None = Field(None, max_length=80)
    theme: str | None = Field(None, max_length=80)
    hook: str | None = Field(None, max_length=200)
    duration_s: float | None = Field(None, ge=0, le=7200)
    views: int | None = Field(None, ge=0)
    likes: int | None = Field(None, ge=0)
    comments: int | None = Field(None, ge=0)
    shares: int | None = Field(None, ge=0)
    avg_watch_s: float | None = Field(None, ge=0, le=7200)
    retention_pct: float | None = Field(None, ge=0, le=100)
    notes: str | None = Field(None, max_length=2000)
    feedback: Literal["good", "bad"] | None = None


class PublicationPatch(Strict):
    clip_id: int | None = None
    platform: PLATFORMS | None = None
    url: str | None = Field(None, max_length=500)
    status: Literal["planned", "published"] | None = None
    planned_for: str | None = Field(None, max_length=40)
    published_at: str | None = Field(None, max_length=40)
    format: str | None = Field(None, max_length=80)
    theme: str | None = Field(None, max_length=80)
    hook: str | None = Field(None, max_length=200)
    duration_s: float | None = Field(None, ge=0, le=7200)
    views: int | None = Field(None, ge=0)
    likes: int | None = Field(None, ge=0)
    comments: int | None = Field(None, ge=0)
    shares: int | None = Field(None, ge=0)
    avg_watch_s: float | None = Field(None, ge=0, le=7200)
    retention_pct: float | None = Field(None, ge=0, le=100)
    notes: str | None = Field(None, max_length=2000)
    feedback: Literal["good", "bad"] | None = None


METRIC_FIELDS = ("views", "likes", "comments", "shares", "avg_watch_s", "retention_pct")


def present(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label"] = STATUS_LABELS.get(out["status"], out["status"])
    return out


@router.get("/publications")
def list_publications(
    c: Ctx,
    platform: str | None = None,
    status: str | None = None,
    format: str | None = None,
    theme: str | None = None,
    clip_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> list[dict]:
    clauses: list[str] = []
    params: list[Any] = []
    for column, value in (("platform", platform), ("status", status), ("format", format), ("theme", theme)):
        if value:
            clauses.append(f"{column} = ?")
            params.append(value)
    if clip_id is not None:
        clauses.append("clip_id = ?")
        params.append(clip_id)
    if date_from:
        clauses.append("COALESCE(published_at, planned_for, created_at) >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("COALESCE(published_at, planned_for, created_at) <= ?")
        params.append(date_to + "T23:59:59" if len(date_to) == 10 else date_to)
    rows = c.repos.publications.list(" AND ".join(clauses), params, order_by="COALESCE(published_at, planned_for, created_at) DESC, id DESC", limit=limit, offset=offset)
    return [present(r) for r in rows]


@router.post("/publications", status_code=201)
def create_publication(body: PublicationBody, c: Ctx) -> dict:
    fields = body.model_dump()
    if body.clip_id is not None:
        clip = c.repos.clips.require(body.clip_id)
        if fields["duration_s"] is None:
            fields["duration_s"] = round(clip["end_s"] - clip["start_s"], 1)
        if not fields["theme"]:
            fields["theme"] = MOMENT_TYPES.get(clip["moment_type"])
    if any(fields[name] is not None for name in METRIC_FIELDS):
        fields["metrics_updated_at"] = utcnow()
    if fields["status"] == "published" and not fields["published_at"]:
        fields["published_at"] = utcnow()
    return present(c.repos.publications.insert(**fields))


@router.get("/publications/{publication_id}")
def get_publication(publication_id: int, c: Ctx) -> dict:
    return present(c.repos.publications.require(publication_id))


@router.patch("/publications/{publication_id}")
def patch_publication(publication_id: int, body: PublicationPatch, c: Ctx) -> dict:
    c.repos.publications.require(publication_id)
    fields = body.model_dump(exclude_unset=True)
    if "platform" in fields and fields["platform"] is None:
        raise InvalidInput("A plataforma não pode ficar vazia.")
    if "status" in fields and fields["status"] is None:
        raise InvalidInput("O status não pode ficar vazio.")
    if fields.get("clip_id") is not None:
        c.repos.clips.require(fields["clip_id"])
    if any(name in fields for name in METRIC_FIELDS):
        fields["metrics_updated_at"] = utcnow()
    return present(c.repos.publications.update(publication_id, **fields))


@router.delete("/publications/{publication_id}")
def delete_publication(publication_id: int, c: Ctx) -> dict:
    c.repos.publications.require(publication_id)
    c.repos.publications.delete(publication_id)
    return {"status": "removido"}


@router.get("/reports/publications")
def publications_report(c: Ctx, group_by: str = "format") -> dict:
    if group_by not in GROUP_FIELDS:
        raise InvalidInput(f"group_by inválido. Use: {', '.join(GROUP_FIELDS)}.")
    rows = c.repos.publications.list(order_by="id ASC")
    return build_report(rows, group_by)
