"""YouTube Data API v3 client (official API, API key sent in a header - never in the URL/logs)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..errors import AppError, Unavailable

API_URL = "https://www.googleapis.com/youtube/v3"
_ISO_DURATION = re.compile(r"^P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?$")
_HASHTAG = re.compile(r"#([\w]{2,40})", re.UNICODE)


def parse_iso_duration(text: str | None) -> float | None:
    if not text:
        return None
    match = _ISO_DURATION.match(text)
    if not match or not any(match.groups()):
        return None
    days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return float(days * 86400 + hours * 3600 + minutes * 60 + seconds)


def extract_hashtags(*texts: str | None) -> list[str]:
    found: list[str] = []
    for text in texts:
        for tag in _HASHTAG.findall(text or ""):
            low = tag.lower()
            if low not in found:
                found.append(low)
    return found


def quota_day() -> str:
    """YouTube quotas reset at midnight Pacific Time."""
    try:
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        now = datetime.now(timezone.utc) - timedelta(hours=8)
    return now.date().isoformat()


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeClient:
    def __init__(self, api_key: str, http: httpx.Client | None = None, transport: Any = None) -> None:
        self._key = api_key
        self._http = http or httpx.Client(timeout=20.0, transport=transport)
        self._owns_http = http is None

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._http.get(f"{API_URL}{path}", params=params, headers={"x-goog-api-key": self._key})
        except httpx.HTTPError as exc:
            raise Unavailable("Não consegui falar com o YouTube (verifique a conexão com a internet).") from exc
        if response.status_code == 200:
            return response.json()
        reason = ""
        try:
            errors = (response.json().get("error") or {}).get("errors") or []
            reason = errors[0].get("reason", "") if errors else ""
        except ValueError:
            pass
        if response.status_code == 403 and reason in ("quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded"):
            raise AppError(
                "A cota diária da YouTube Data API acabou. Ela renova à meia-noite (horário do Pacífico).",
                code="youtube_quota", status_code=429,
            )
        if response.status_code in (400, 403):
            raise AppError(
                "O YouTube recusou a chave de API ou a requisição. Confira YOUTUBE_API_KEY no .env e se a "
                "YouTube Data API v3 está habilitada no seu projeto do Google Cloud.",
                code="youtube_auth", status_code=502,
            )
        raise AppError(f"O YouTube respondeu com erro {response.status_code}.", status_code=502)

    def search(
        self, q: str, *, region: str, language: str | None, published_after: str, order: str,
        duration: str, page_token: str | None = None,
    ) -> tuple[list[str], str | None]:
        """One search.list call (own daily bucket: 100 calls by default). Returns (video ids, next page token)."""
        params: dict[str, Any] = {
            "part": "snippet", "type": "video", "q": q, "maxResults": 50, "order": order,
            "regionCode": region, "videoDuration": duration, "publishedAfter": published_after,
        }
        if language:
            params["relevanceLanguage"] = language
        if page_token:
            params["pageToken"] = page_token
        body = self._get("/search", params)
        ids = [item["id"]["videoId"] for item in body.get("items", []) if item.get("id", {}).get("videoId")]
        return ids, body.get("nextPageToken")

    def videos(self, ids: list[str]) -> list[dict[str, Any]]:
        """videos.list (1 unit per call, up to 50 ids). Returns normalized public data."""
        out: list[dict[str, Any]] = []
        for i in range(0, len(ids), 50):
            body = self._get("/videos", {"part": "snippet,contentDetails,statistics", "id": ",".join(ids[i:i + 50])})
            for item in body.get("items", []):
                snippet = item.get("snippet") or {}
                stats = item.get("statistics") or {}
                tags = snippet.get("tags") or []
                out.append({
                    "external_id": item.get("id"),
                    "url": f"https://www.youtube.com/watch?v={item.get('id')}",
                    "title": snippet.get("title"),
                    "channel": snippet.get("channelTitle"),
                    "published_at": snippet.get("publishedAt"),
                    "duration_s": parse_iso_duration((item.get("contentDetails") or {}).get("duration")),
                    "views": _to_int(stats.get("viewCount")),
                    "likes": _to_int(stats.get("likeCount")),
                    "comments": _to_int(stats.get("commentCount")),
                    "language": snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
                    "tags": tags,
                    "hashtags": extract_hashtags(snippet.get("title"), snippet.get("description")),
                })
        return out
