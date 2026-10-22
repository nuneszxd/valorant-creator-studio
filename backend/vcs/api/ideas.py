"""Ideas and scripts: suggestions from profile + data, saved ideas, script skeletons."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import Field

from ..models import Strict
from ..recommendations import FORMATS, build_script, suggest_ideas
from .deps import Ctx

router = APIRouter(prefix="/api/ideas", tags=["ideias e roteiros"])

STATUS = Literal["idea", "planned", "recorded", "published", "discarded"]
STATUS_LABELS = {"idea": "ideia", "planned": "planejada", "recorded": "gravada", "published": "publicada",
                 "discarded": "descartada"}


class IdeaBody(Strict):
    title: str = Field(min_length=1, max_length=160)
    format: str | None = Field(None, max_length=60)
    status: STATUS = "idea"
    rationale: list[dict[str, Any]] | None = Field(None, max_length=20)
    script: dict[str, Any] | None = None
    source: Literal["manual", "sugestao"] = "manual"


class IdeaPatch(Strict):
    title: str | None = Field(None, min_length=1, max_length=160)
    format: str | None = Field(None, max_length=60)
    status: STATUS | None = None
    rationale: list[dict[str, Any]] | None = Field(None, max_length=20)
    script: dict[str, Any] | None = None


def present(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label"] = STATUS_LABELS.get(out["status"], out["status"])
    return out


@router.get("/formats")
def formats() -> dict:
    return {"formats": {k: {"title": v["title"], "why": v["why"], "next": v["next"]} for k, v in FORMATS.items()}}


@router.post("/suggest")
def suggest(c: Ctx, limit: int = Query(6, ge=1, le=10)) -> dict:
    """Suggestions explained by their reasons. Nothing is saved until you save an idea."""
    profile = c.settings.load_profile()
    trends = c.repos.trends.list(
        "run_id IN (SELECT MAX(id) FROM radar_runs WHERE status = 'done' GROUP BY source)", order_by="id ASC"
    )
    ideas = suggest_ideas(
        profile,
        publications=c.repos.publications.list(order_by="id ASC"),
        candidates=c.repos.candidates.list(order_by="id ASC"),
        trends=trends,
        limit=limit,
    )
    has_profile = bool(profile.channel_name or profile.rank_current or profile.formats_to_try)
    return {
        "ideas": ideas,
        "notes": ([] if has_profile else ["Preencha o Perfil do canal para sugestões mais úteis."]),
    }


@router.get("")
def list_ideas(c: Ctx, status: str | None = None) -> list[dict]:
    rows = c.repos.ideas.list("status = ?" if status else "", (status,) if status else (), order_by="id DESC")
    return [present(r) for r in rows]


@router.post("", status_code=201)
def create_idea(body: IdeaBody, c: Ctx) -> dict:
    return present(c.repos.ideas.insert(**body.model_dump()))


@router.patch("/{idea_id}")
def patch_idea(idea_id: int, body: IdeaPatch, c: Ctx) -> dict:
    c.repos.ideas.require(idea_id)
    return present(c.repos.ideas.update(idea_id, **body.model_dump(exclude_unset=True)))


@router.delete("/{idea_id}")
def delete_idea(idea_id: int, c: Ctx) -> dict:
    c.repos.ideas.require(idea_id)
    c.repos.ideas.delete(idea_id)
    return {"status": "removido"}


@router.post("/{idea_id}/script")
def make_script(idea_id: int, c: Ctx) -> dict:
    idea = c.repos.ideas.require(idea_id)
    script = build_script(idea["title"], idea.get("format"), c.settings.load_profile())
    return present(c.repos.ideas.update(idea_id, script=script))
