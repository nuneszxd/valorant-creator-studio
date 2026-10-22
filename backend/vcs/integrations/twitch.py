"""Twitch Helix API client (official API, app access token / client-credentials flow).

What this can do (public data only, no user login, no scopes): read VOD metadata, check whether a
channel is live, and list public Valorant clips. What it cannot do: download a VOD. Twitch does not
offer that through the API, so the app asks the user to download their own VOD (Video Producer)
and select the file locally. Nothing here tries to bypass any access restriction.
"""

from __future__ import annotations

import re
import time
from typing import Any

import httpx

from ..errors import AppError, InvalidInput, Unavailable

TOKEN_URL = "https://id.twitch.tv/oauth2/token"
API_URL = "https://api.twitch.tv/helix"

_VOD = re.compile(r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/videos/(\d+)(?:[/?#].*)?$", re.I)
_CLIP_A = re.compile(r"^(?:https?://)?clips\.twitch\.tv/([\w-]+)", re.I)
_CLIP_B = re.compile(r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/[A-Za-z0-9_]+/clip/([\w-]+)", re.I)
_CHANNEL = re.compile(r"^(?:https?://)?(?:www\.|m\.)?twitch\.tv/([A-Za-z0-9_]{3,25})/?(?:[?#].*)?$", re.I)
_RESERVED = {
    "videos", "directory", "downloads", "jobs", "p", "settings", "subscriptions", "wallet", "friends",
    "inventory", "drops", "turbo", "store", "search", "popout", "embed", "moderator", "u", "dashboard",
}
_DURATION = re.compile(r"^(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?$")

RETENTION_NOTE = (
    "Segundo a página de ajuda da Twitch, as transmissões anteriores ficam guardadas por 7 dias "
    "(canais comuns), 14 dias (Afiliados) ou 60 dias (Parceiros, Prime e Turbo). Esses prazos podem "
    "mudar: confira no seu Painel do Criador."
)
DOWNLOAD_STEPS = [
    "Abra o Painel do Criador da Twitch (dashboard.twitch.tv).",
    "Vá em Conteúdo > Video Producer.",
    "No VOD desejado, clique nos três pontinhos e escolha Baixar.",
    "Quando o download terminar, volte aqui e escolha o arquivo baixado (botão 'Escolher arquivo').",
]


def parse_twitch_url(url: str) -> dict[str, str]:
    value = (url or "").strip()
    if not value:
        raise InvalidInput("Cole o link do VOD ou da live da Twitch.")
    if match := _VOD.match(value):
        return {"kind": "vod", "id": match.group(1)}
    if match := (_CLIP_A.match(value) or _CLIP_B.match(value)):
        return {"kind": "clip", "slug": match.group(1)}
    if (match := _CHANNEL.match(value)) and match.group(1).lower() not in _RESERVED:
        return {"kind": "channel", "login": match.group(1).lower()}
    raise InvalidInput("Link da Twitch não reconhecido. Use o formato https://www.twitch.tv/videos/NÚMERO.")


def parse_duration(text: str | None) -> float | None:
    """Twitch durations look like '3h2m1s'."""
    if not text:
        return None
    match = _DURATION.match(text.strip())
    if not match or not any(match.groups()):
        return None
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return float(hours * 3600 + minutes * 60 + seconds)


class TwitchClient:
    def __init__(self, client_id: str, client_secret: str, http: httpx.Client | None = None,
                 transport: Any = None) -> None:
        self.client_id = client_id
        self._secret = client_secret
        self._http = http or httpx.Client(timeout=15.0, transport=transport)
        self._owns_http = http is None
        self._token: str | None = None
        self._expires_at = 0.0

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "TwitchClient":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- plumbing -----------------------------------------------------------------
    def _ensure_token(self, force: bool = False) -> str:
        if self._token and not force and time.time() < self._expires_at - 60:
            return self._token
        try:
            response = self._http.post(
                TOKEN_URL,
                data={"client_id": self.client_id, "client_secret": self._secret,
                      "grant_type": "client_credentials"},
            )
        except httpx.HTTPError as exc:
            raise Unavailable("Não consegui falar com a Twitch (verifique a conexão com a internet).") from exc
        if response.status_code in (400, 401, 403):
            raise AppError(
                "A Twitch recusou as credenciais (TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET no .env). "
                "Confira os valores em dev.twitch.tv/console.",
                code="twitch_auth", status_code=502,
            )
        if response.status_code >= 400:
            raise AppError(f"A Twitch respondeu com erro {response.status_code} ao autenticar.", status_code=502)
        data = response.json()
        self._token = data["access_token"]
        self._expires_at = time.time() + float(data.get("expires_in", 0))
        return self._token

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(2):
            token = self._ensure_token(force=attempt == 1)
            try:
                response = self._http.get(
                    f"{API_URL}{path}", params=params,
                    headers={"Client-Id": self.client_id, "Authorization": f"Bearer {token}"},
                )
            except httpx.HTTPError as exc:
                raise Unavailable("Não consegui falar com a Twitch (verifique a conexão com a internet).") from exc
            if response.status_code == 401 and attempt == 0:
                continue
            if response.status_code == 429:
                raise AppError("Limite de requisições da Twitch atingido. Tente de novo em alguns minutos.",
                               code="twitch_rate_limit", status_code=429)
            if response.status_code >= 400:
                raise AppError(f"A Twitch respondeu com erro {response.status_code}.", status_code=502)
            return response.json()
        raise AppError("Falha de autenticação com a Twitch.", code="twitch_auth", status_code=502)

    # -- endpoints ----------------------------------------------------------------
    def get_video(self, video_id: str) -> dict[str, Any] | None:
        data = self._get("/videos", {"id": video_id}).get("data") or []
        if not data:
            return None
        v = data[0]
        return {
            "id": v.get("id"), "title": v.get("title"), "user_name": v.get("user_name"),
            "user_login": v.get("user_login"), "created_at": v.get("created_at"),
            "url": v.get("url"), "view_count": v.get("view_count"),
            "duration_s": parse_duration(v.get("duration")), "type": v.get("type"),
            "language": v.get("language"), "thumbnail_url": v.get("thumbnail_url"),
            "muted_segments": v.get("muted_segments"),
        }

    def get_stream(self, login: str) -> dict[str, Any] | None:
        data = self._get("/streams", {"user_login": login}).get("data") or []
        return data[0] if data else None

    def get_game_id(self, name: str) -> str | None:
        data = self._get("/games", {"name": name}).get("data") or []
        return data[0]["id"] if data else None

    def get_clips(self, game_id: str, started_at: str, ended_at: str, *, first: int = 100,
                  after: str | None = None) -> tuple[list[dict[str, Any]], str | None]:
        params: dict[str, Any] = {"game_id": game_id, "started_at": started_at, "ended_at": ended_at,
                                  "first": min(max(first, 1), 100)}
        if after:
            params["after"] = after
        body = self._get("/clips", params)
        return body.get("data") or [], (body.get("pagination") or {}).get("cursor")


def make_twitch_client(config: Any, transport: Any = None) -> TwitchClient | None:
    """A client when credentials are configured in the environment, otherwise None."""
    if config.twitch_client_id and config.twitch_client_secret:
        return TwitchClient(config.twitch_client_id, config.twitch_client_secret, transport=transport)
    return None


def resolve_link(client: TwitchClient | None, url: str) -> dict[str, Any]:
    """Explain what can be done with a Twitch link. Never downloads anything."""
    parsed = parse_twitch_url(url)
    result: dict[str, Any] = {
        "kind": parsed["kind"],
        "metadata_available": False,
        "can_download_via_api": False,
        "retention_note": RETENTION_NOTE,
        "download_steps": DOWNLOAD_STEPS,
        "messages": [],
        "video": None,
        "live": None,
    }
    messages: list[str] = result["messages"]
    messages.append(
        "A API oficial da Twitch não permite baixar VODs. Baixe o seu próprio VOD pelo Video Producer "
        "e importe o arquivo aqui."
    )
    if parsed["kind"] == "clip":
        messages.append("Este é um link de clipe. Importe o arquivo do clipe ou use o VOD completo.")
        return result
    if client is None:
        messages.append(
            "Para ler título, duração e disponibilidade do VOD, configure TWITCH_CLIENT_ID e "
            "TWITCH_CLIENT_SECRET no arquivo .env (opcional)."
        )
        return result
    if parsed["kind"] == "vod":
        video = client.get_video(parsed["id"])
        if video is None:
            messages.append(
                "A Twitch não encontrou este VOD: ele pode ter expirado, sido apagado ou estar privado. "
                "Se você ainda tem o arquivo, selecione-o diretamente."
            )
            return result
        result["metadata_available"] = True
        result["video"] = video
        if video.get("muted_segments"):
            messages.append("Este VOD tem trechos silenciados pela Twitch (música protegida, por exemplo).")
        return result
    stream = client.get_stream(parsed["login"])
    result["metadata_available"] = True
    result["live"] = {"login": parsed["login"], "is_live": stream is not None,
                      "title": stream.get("title") if stream else None}
    if stream:
        messages.append("A live está em andamento. O VOD só fica disponível depois que ela terminar.")
    else:
        messages.append("O canal não está ao vivo. Cole o link de um VOD (twitch.tv/videos/NÚMERO).")
    return result
