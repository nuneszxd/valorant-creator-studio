"""Runtime configuration, read from environment variables and an optional .env file.

Secrets (Twitch/YouTube credentials) only ever come from the environment / .env and are
never stored in the database, returned by the API or written to logs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class ConfigError(Exception):
    pass


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8-sig")
    except OSError:
        return values
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def load_dotenv(path: Path | None = None) -> list[str]:
    """Load .env files into os.environ without overriding variables that are already set."""
    candidates = [path] if path else [Path.cwd() / ".env", REPO_ROOT / ".env"]
    loaded: list[str] = []
    for candidate in candidates:
        if candidate and candidate.is_file():
            for key, value in parse_env_file(candidate).items():
                os.environ.setdefault(key, value)
            loaded.append(str(candidate))
    return loaded


def _env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _resolve_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def check_host(host: str) -> None:
    if host not in LOOPBACK_HOSTS and _env("VCS_ALLOW_NON_LOCAL") != "1":
        raise ConfigError(
            f"O endereço {host!r} não é local. Por segurança o servidor só aceita 127.0.0.1/localhost. "
            "(Defina VCS_ALLOW_NON_LOCAL=1 apenas se souber o que está fazendo.)"
        )


@dataclass(frozen=True)
class AppConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    data_dir: Path = REPO_ROOT / "data"
    output_dir: Path | None = None
    ffmpeg_path: str | None = None
    ffprobe_path: str | None = None
    twitch_client_id: str | None = field(default=None, repr=False)
    twitch_client_secret: str | None = field(default=None, repr=False)
    youtube_api_key: str | None = field(default=None, repr=False)
    extra_origins: tuple[str, ...] = ()
    frontend_dist: Path = REPO_ROOT / "frontend" / "dist"
    # The Vite dev server origin is only trusted when VCS_DEV=1 (otherwise any other program serving
    # on that port could call the API).
    dev_ports: tuple[int, ...] = ()
    # Swagger UI loads scripts from a CDN, so it is opt-in (VCS_DEV=1 or VCS_API_DOCS=1).
    api_docs: bool = False

    @property
    def db_path(self) -> Path:
        return self.data_dir / "app.db"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def jobs_dir(self) -> Path:
        return self.work_dir / "jobs"

    @property
    def previews_dir(self) -> Path:
        return self.data_dir / "previews"

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def logs_dir(self) -> Path:
        return self.data_dir / "logs"

    @property
    def default_output_dir(self) -> Path:
        return self.output_dir or (self.data_dir / "output")

    @property
    def allowed_hosts(self) -> frozenset[str]:
        return frozenset(LOOPBACK_HOSTS)

    @property
    def allowed_origins(self) -> frozenset[str]:
        origins: set[str] = set(self.extra_origins)
        ports = {self.port, *self.dev_ports}
        for port in ports:
            for host in ("127.0.0.1", "localhost"):
                origins.add(f"http://{host}:{port}")
        return frozenset(origins)

    def ensure_dirs(self) -> None:
        for directory in (
            self.data_dir,
            self.work_dir,
            self.jobs_dir,
            self.previews_dir,
            self.models_dir,
            self.logs_dir,
            self.default_output_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def secrets(self) -> list[str]:
        return [
            s
            for s in (self.twitch_client_id, self.twitch_client_secret, self.youtube_api_key)
            if s
        ]

    def integrations(self) -> dict[str, bool]:
        """Which integrations have credentials configured (never the credentials themselves)."""
        return {
            "twitch": bool(self.twitch_client_id and self.twitch_client_secret),
            "youtube": bool(self.youtube_api_key),
        }

    @classmethod
    def from_env(cls) -> "AppConfig":
        host = _env("VCS_HOST") or "127.0.0.1"
        check_host(host)
        try:
            port = int(_env("VCS_PORT") or "8000")
        except ValueError as exc:
            raise ConfigError("VCS_PORT precisa ser um número inteiro.") from exc
        if not 1 <= port <= 65535:
            raise ConfigError("VCS_PORT precisa estar entre 1 e 65535.")

        data_dir = _resolve_path(_env("VCS_DATA_DIR") or "data")
        output = _env("VCS_OUTPUT_DIR")
        extra = tuple(o.strip() for o in (_env("VCS_ALLOWED_ORIGINS") or "").split(",") if o.strip())
        dev = _env("VCS_DEV") == "1"
        return cls(
            dev_ports=(5173,) if dev else (),
            api_docs=dev or _env("VCS_API_DOCS") == "1",
            host=host,
            port=port,
            data_dir=data_dir,
            output_dir=_resolve_path(output) if output else None,
            ffmpeg_path=_env("VCS_FFMPEG_PATH"),
            ffprobe_path=_env("VCS_FFPROBE_PATH"),
            twitch_client_id=_env("TWITCH_CLIENT_ID"),
            twitch_client_secret=_env("TWITCH_CLIENT_SECRET"),
            youtube_api_key=_env("YOUTUBE_API_KEY"),
            extra_origins=extra,
        )
