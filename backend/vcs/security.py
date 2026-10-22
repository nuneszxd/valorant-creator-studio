"""Security helpers: local-only request guard, path validation and secret redaction."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Iterable

from .errors import Forbidden, InvalidInput, NotFound

VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".mov", ".webm", ".avi", ".flv", ".m4v", ".wmv", ".mpg", ".mpeg",
    ".ts", ".mts", ".m2ts",
}

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


# --------------------------------------------------------------------------- request guard


def host_without_port(value: str) -> str:
    value = value.strip().lower()
    if value.startswith("["):
        end = value.find("]")
        return value[1:end] if end != -1 else value
    if value.count(":") == 1:
        return value.split(":")[0]
    return value


class LocalOnlyMiddleware:
    """Pure-ASGI guard against DNS rebinding and cross-site requests to the local API.

    * The Host header must be a loopback name (blocks DNS rebinding).
    * State-changing requests must not come from a foreign Origin or a cross-site fetch (CSRF).
    """

    def __init__(self, app, *, allowed_hosts: Iterable[str], allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.allowed_hosts = frozenset(allowed_hosts)
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = host_without_port(headers.get("host", ""))
        if host not in self.allowed_hosts:
            await self._deny(send, "Host não permitido: o aplicativo só responde em localhost.")
            return
        # Backslashes / leading "//" would let a crafted URL reach UNC paths (SMB) on Windows.
        path = scope.get("path", "")
        if "\\" in path or "\x00" in path or path.startswith("//"):
            await self._deny(send, "Caminho inválido.")
            return
        # Browsers label cross-site subresource loads (<img>, <video>, fetch...) on every method.
        if headers.get("sec-fetch-site") == "cross-site":
            await self._deny(send, "Requisição entre sites bloqueada.")
            return
        if scope["method"] not in SAFE_METHODS:
            origin = headers.get("origin")
            if origin is not None and origin not in self.allowed_origins:
                await self._deny(send, "Origem não permitida para esta operação.")
                return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                extra = [
                    (b"x-frame-options", b"DENY"),
                    (b"content-security-policy", b"frame-ancestors 'none'"),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                ]
                message = {**message, "headers": [*message.get("headers", []), *extra]}
            await send(message)

        await self.app(scope, receive, send_with_headers)

    @staticmethod
    async def _deny(send, message: str) -> None:
        body = json.dumps({"error": {"code": "forbidden", "message": message}}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


# --------------------------------------------------------------------------- paths


def _reject_network_path(value: str, path: Path) -> None:
    """Refuse UNC / network paths before touching the filesystem (resolving them would open SMB)."""
    drive = getattr(path, "drive", "") or ""
    if value.startswith("\\\\") or value.startswith("//") or drive.startswith("\\\\") or drive.startswith("//"):
        raise InvalidInput("Caminhos de rede (UNC) não são aceitos. Copie o arquivo para um disco local.")


def validate_media_file(raw: str) -> Path:
    """Validate a user-provided path to a local video file and return its resolved path."""
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidInput("Informe o caminho do arquivo de vídeo.")
    value = raw.strip().strip('"')
    if "\x00" in value:
        raise InvalidInput("Caminho inválido.")
    path = Path(value).expanduser()
    _reject_network_path(value, path)
    if not path.is_absolute():
        raise InvalidInput(
            "Use o caminho completo do arquivo (por exemplo, C:\\Videos\\partida.mp4)."
        )
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise NotFound(f"Arquivo não encontrado: {value}") from exc
    _reject_network_path("", resolved)
    if not resolved.is_file():
        raise InvalidInput("O caminho informado não é um arquivo.")
    if resolved.suffix.lower() not in VIDEO_EXTENSIONS:
        allowed = ", ".join(sorted(VIDEO_EXTENSIONS))
        raise InvalidInput(
            f"Extensão não suportada ({resolved.suffix or 'sem extensão'}). Use: {allowed}."
        )
    return resolved


def validate_directory(raw: str, *, create: bool = False) -> Path:
    if not isinstance(raw, str) or not raw.strip():
        raise InvalidInput("Informe o caminho da pasta.")
    value = raw.strip().strip('"')
    if "\x00" in value:
        raise InvalidInput("Caminho de pasta inválido.")
    path = Path(value).expanduser()
    _reject_network_path(value, path)
    if not path.is_absolute():
        raise InvalidInput("Use o caminho completo da pasta.")
    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise InvalidInput(f"Não foi possível criar a pasta: {exc.strerror or exc}") from exc
    try:
        resolved = path.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise NotFound(f"Pasta não encontrada: {value}") from exc
    _reject_network_path("", resolved)
    if not resolved.is_dir():
        raise InvalidInput("O caminho informado não é uma pasta.")
    return resolved


def ensure_within(path: Path, root: Path) -> Path:
    """Return the resolved path if it lies inside root, otherwise raise Forbidden."""
    resolved = path.resolve()
    root_resolved = root.resolve()
    if resolved != root_resolved and not resolved.is_relative_to(root_resolved):
        raise Forbidden("Operação fora das pastas gerenciadas pelo aplicativo.")
    return resolved


_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def safe_filename(name: str, default: str = "arquivo", max_len: int = 80) -> str:
    ascii_text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9._\- ]+", "_", ascii_text)
    cleaned = re.sub(r"[ _]+", "_", cleaned).strip("._ -")
    if not cleaned:
        cleaned = default
    if cleaned.lower().split(".")[0] in _RESERVED:
        cleaned = "_" + cleaned
    return cleaned[:max_len]


# --------------------------------------------------------------------------- redaction

_KEY_VALUE = re.compile(
    r"(?i)\b(client[_-]?secret|api[_-]?key|access[_-]?token|refresh[_-]?token|authorization|password|secret|token)\b"
    r"([\"']?\s*[=:]\s*[\"']?)(?:Bearer\s+|OAuth\s+)?([^\s&\"',;]+)"
)
_BEARER = re.compile(r"(?i)\b(bearer|oauth)\s+[A-Za-z0-9\-._~+/]{8,}=*")


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    for secret in secrets:
        if secret and len(secret) >= 4:
            text = text.replace(secret, "***")
    text = _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    text = _BEARER.sub(lambda m: f"{m.group(1)} ***", text)
    return text


def error_text(exc: BaseException, secrets: Iterable[str] = ()) -> str:
    """User-facing text for an exception, with secrets masked, safe to store in the database."""
    message = getattr(exc, "message", None) or f"{type(exc).__name__}: {exc}"
    return redact(str(message), secrets)


class RedactingFormatter(logging.Formatter):
    def __init__(self, fmt: str, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        self._secrets = [s for s in secrets if s]

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record), self._secrets)


def setup_logging(logs_dir: Path | None, secrets: Iterable[str] = (), level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if getattr(root, "_vcs_configured", False):
        return
    formatter = RedactingFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s", secrets)
    handlers: list[logging.Handler] = []
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    handlers.append(stream)
    if logs_dir is not None:
        try:
            logs_dir.mkdir(parents=True, exist_ok=True)
            file_handler = RotatingFileHandler(
                logs_dir / "app.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except OSError:
            pass
    root.handlers = handlers
    root.setLevel(level)
    # httpx logs full request URLs at INFO; keep them out of the logs.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._vcs_configured = True  # type: ignore[attr-defined]
