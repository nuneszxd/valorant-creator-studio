"""Settings and creator profile endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..models import AppSettings, CreatorProfile
from .deps import Ctx

router = APIRouter(prefix="/api", tags=["configurações"])


@router.get("/settings")
def get_settings(c: Ctx) -> dict:
    return {
        "settings": c.settings.load().model_dump(),
        "defaults": AppSettings().model_dump(),
        "effective_output_dir": str(c.settings.effective_output_dir()),
        "data_dir": str(c.config.data_dir),
        "integrations": c.config.integrations(),
    }


@router.patch("/settings")
def patch_settings(body: dict[str, Any], c: Ctx) -> dict:
    """Partial update. Secrets (Twitch/YouTube) are never accepted here: they live in the .env file."""
    updated = c.settings.patch(body)
    return {"settings": updated.model_dump(), "effective_output_dir": str(c.settings.effective_output_dir())}


@router.get("/profile")
def get_profile(c: Ctx) -> dict:
    return c.settings.load_profile().model_dump()


@router.put("/profile")
def put_profile(body: CreatorProfile, c: Ctx) -> dict:
    return c.settings.save_profile(body).model_dump()
