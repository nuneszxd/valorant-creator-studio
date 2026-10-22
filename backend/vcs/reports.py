"""Publication reports. Descriptive comparisons only - never claims causation.

Every group carries its sample size and caveats (small sample, very recent videos, one video
dominating). Medians are used instead of means so one outlier doesn't define a group.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .utils import median

DURATION_BUCKETS = [(0, 15, "até 15 s"), (15, 30, "15–30 s"), (30, 45, "30–45 s"), (45, 60, "45–60 s"),
                    (60, 90, "60–90 s"), (90, 10**9, "mais de 90 s")]
GROUP_FIELDS = ("format", "theme", "hook", "platform", "duration")
MIN_SAMPLE = 5
RECENT_HOURS = 48
NO_VALUE = "(sem valor informado)"

READING_NOTE = (
    "Comparação descritiva entre os seus próprios vídeos. Um formato aparecer acima ou abaixo da mediana "
    "não prova que ele causou o resultado: horário, tema do momento, algoritmo e sorte também pesam."
)


def duration_bucket(seconds: float | None) -> str:
    if seconds is None:
        return NO_VALUE
    for low, high, label in DURATION_BUCKETS:
        if low <= seconds < high:
            return label
    return NO_VALUE


def _parse(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def engagement_rate(row: dict[str, Any]) -> float | None:
    views = row.get("views")
    if not views:
        return None
    parts = [row.get("likes"), row.get("comments"), row.get("shares")]
    if all(p is None for p in parts):
        return None
    return sum(p or 0 for p in parts) / views


def _group_key(row: dict[str, Any], group_by: str) -> str:
    if group_by == "duration":
        return duration_bucket(row.get("duration_s"))
    value = row.get(group_by)
    return str(value).strip() if value and str(value).strip() else NO_VALUE


def build_report(rows: list[dict[str, Any]], group_by: str, now: datetime | None = None) -> dict[str, Any]:
    if group_by not in GROUP_FIELDS:
        raise ValueError(f"group_by inválido: {group_by}")
    now = now or datetime.now(timezone.utc)
    published = [r for r in rows if r.get("status") == "published"]
    measured = [r for r in published if r.get("views") is not None]
    overall = {
        "published": len(published),
        "with_views": len(measured),
        "median_views": median(r["views"] for r in measured),
        "median_engagement_rate": median(e for e in (engagement_rate(r) for r in measured) if e is not None),
    }
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in measured:
        groups.setdefault(_group_key(row, group_by), []).append(row)

    out_groups = []
    for key, items in groups.items():
        views = [r["views"] for r in items]
        median_views = median(views)
        warnings: list[str] = []
        if len(items) < MIN_SAMPLE:
            warnings.append(f"Amostra pequena (n={len(items)}): não tire conclusões.")
        ages = [(now - d).total_seconds() / 3600 for d in (_parse(r.get("published_at")) for r in items) if d]
        if any(a < RECENT_HOURS for a in ages):
            warnings.append(f"Inclui vídeos publicados há menos de {RECENT_HOURS} h: o desempenho ainda está se formando.")
        if len(items) >= 3 and median_views and max(views) > 5 * median_views:
            warnings.append("Um único vídeo concentra boa parte das visualizações deste grupo.")
        retention = [r["avg_watch_s"] for r in items if r.get("avg_watch_s") is not None]
        best = max(items, key=lambda r: r["views"])
        overall_median = overall["median_views"]
        out_groups.append({
            "group": key,
            "n": len(items),
            "median_views": median_views,
            "median_engagement_rate": median(e for e in (engagement_rate(r) for r in items) if e is not None),
            "median_avg_watch_s": median(retention),
            "vs_overall_median": (round(median_views / overall_median, 2)
                                  if median_views is not None and overall_median else None),
            "best_example": {"id": best["id"], "url": best.get("url"), "views": best["views"],
                             "hook": best.get("hook")},
            "warnings": warnings,
        })
    out_groups.sort(key=lambda g: (g["n"] >= MIN_SAMPLE, g["median_views"] or 0), reverse=True)
    return {"group_by": group_by, "overall": overall, "groups": out_groups, "reading_note": READING_NOTE,
            "min_sample": MIN_SAMPLE}
