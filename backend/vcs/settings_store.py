"""Persistence for app settings and the creator profile (JSON documents in SQLite)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .config import AppConfig
from .db import Database
from .errors import InvalidInput
from .models import AppSettings, CreatorProfile
from .security import validate_directory
from .utils import deep_merge, dumps, loads, utcnow

log = logging.getLogger(__name__)

SETTINGS_KEY = "app"


def format_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for err in exc.errors()[:5]:
        loc = ".".join(str(p) for p in err.get("loc", ()))
        parts.append(f"{loc}: {err.get('msg', 'valor inválido')}" if loc else str(err.get("msg")))
    return "; ".join(parts) or "Valores inválidos."


class SettingsStore:
    def __init__(self, db: Database, config: AppConfig) -> None:
        self.db = db
        self.config = config

    # -- app settings -------------------------------------------------------------
    def load(self) -> AppSettings:
        row = self.db.one("SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,))
        data = loads(row["value"], {}) if row else {}
        try:
            return AppSettings.model_validate(data)
        except ValidationError:
            log.warning("Stored settings are invalid; falling back to defaults.")
            return AppSettings()

    def save(self, settings: AppSettings) -> AppSettings:
        self.db.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SETTINGS_KEY, dumps(settings.model_dump())),
        )
        return settings

    def patch(self, patch: dict[str, Any]) -> AppSettings:
        merged = deep_merge(self.load().model_dump(), patch)
        try:
            updated = AppSettings.model_validate(merged)
        except ValidationError as exc:
            raise InvalidInput(format_validation_error(exc)) from exc
        if updated.output_dir:
            updated.output_dir = str(validate_directory(updated.output_dir, create=True))
        return self.save(updated)

    def effective_output_dir(self, *, create: bool = False) -> Path:
        """Output folder in use. Reading it never touches the disk (a missing drive must not break the UI);
        pass create=True right before writing a file."""
        settings = self.load()
        path = Path(settings.output_dir) if settings.output_dir else self.config.default_output_dir
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    # -- creator profile ----------------------------------------------------------
    def load_profile(self) -> CreatorProfile:
        row = self.db.one("SELECT data FROM profile WHERE id = 1")
        data = loads(row["data"], {}) if row else {}
        try:
            return CreatorProfile.model_validate(data)
        except ValidationError:
            return CreatorProfile()

    def save_profile(self, profile: CreatorProfile) -> CreatorProfile:
        self.db.execute(
            "INSERT INTO profile (id, data, updated_at) VALUES (1, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at",
            (dumps(profile.model_dump()), utcnow()),
        )
        return profile


def validate_model(model: type[BaseModel], data: dict[str, Any]) -> BaseModel:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise InvalidInput(format_validation_error(exc)) from exc
