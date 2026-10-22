"""Twitch link resolution (official API; metadata only - the app never downloads VODs)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import Field

from ..integrations.twitch import make_twitch_client, resolve_link
from ..models import Strict
from .deps import Ctx

router = APIRouter(prefix="/api/imports", tags=["importação"])


class ResolveBody(Strict):
    url: str = Field(min_length=1, max_length=300)


@router.post("/twitch/resolve")
def resolve_twitch(body: ResolveBody, c: Ctx) -> dict:
    """Explain what is possible with a Twitch link and how to get the video file legitimately."""
    client = make_twitch_client(c.config, c.http_transport)
    try:
        return resolve_link(client, body.url)
    finally:
        if client is not None:
            client.close()
