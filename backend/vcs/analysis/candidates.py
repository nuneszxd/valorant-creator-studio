"""Candidate generation and explainable scoring. Pure functions, no I/O.

The score is a weighted sum of observable signals (audio, speech, scene changes, ...). It is a
prioritisation aid for the creator's review - NOT a probability of virality - and every point can
be traced to a reason shown in the UI.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any

from ..models import AnalysisSettings
from ..utils import clamp, fmt_hms
from .moment_types import MOMENT_TYPES, count_keyword_hits, normalize_text
from .signals import AudioProfile, find_peaks

MIN_GAIN_DB = 4.0  # a peak must stand this far above the recording's median loudness
TYPE_PRIORITY = ["ace_multikill", "clutch", "decisao", "tilt", "erro", "engracado", "jogada"]

FEATURE_LABELS = {
    "audio_intensity": "Intensidade do áudio",
    "audio_burst": "Subida brusca de volume",
    "tension": "Tensão (calmaria antes do pico)",
    "speech": "Presença de fala",
    "reaction": "Palavras de evento/reação",
    "scene_activity": "Mudanças de cena",
    "context": "Contexto falado antes do pico",
    "story": "Início → desfecho (pequena história)",
    "duration_fit": "Adequação à duração desejada",
    "creator_pref": "Preferência do criador",
}


@dataclass
class Prefs:
    preferred_types: list[str] = field(default_factory=list)
    min_s: int = 20
    max_s: int = 45


@dataclass
class ScoringContext:
    weights: dict[str, float]
    keywords: dict[str, list[str]]
    reaction_keywords: list[str]
    prefs: Prefs = field(default_factory=Prefs)
    feedback: dict[str, float] = field(default_factory=dict)  # moment_type -> points


@dataclass
class Window:
    start: float
    end: float
    peak: float


@dataclass
class CandidateDraft:
    start_s: float
    end_s: float
    peak_s: float
    title: str
    moment_type: str
    score: float
    confidence: str
    reasons: list[dict[str, Any]]
    excerpt: str

    def to_row(self) -> dict[str, Any]:
        return {
            "start_s": round(self.start_s, 2),
            "end_s": round(self.end_s, 2),
            "title": self.title,
            "moment_type": self.moment_type,
            "score": round(self.score, 1),
            "confidence": self.confidence,
            "reasons": self.reasons,
            "excerpt": self.excerpt,
        }


# --------------------------------------------------------------------------- helpers


def _slice(series: list[float], window_s: float, a: float, b: float) -> list[float]:
    i0 = max(0, int(a / window_s))
    i1 = min(len(series), int(math.ceil(b / window_s)))
    return series[i0:i1] if i1 > i0 else []


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def words_in_range(segments: list[dict[str, Any]], a: float, b: float) -> float:
    """Number of spoken words between a and b (prorated when a segment has no word timestamps)."""
    total = 0.0
    for seg in segments:
        if seg["end_s"] <= a or seg["start_s"] >= b:
            continue
        words = seg.get("words") or []
        if words:
            total += sum(1 for w in words if a <= (w["start"] + w["end"]) / 2 < b)
        else:
            length = max(seg["end_s"] - seg["start_s"], 0.001)
            overlap = min(seg["end_s"], b) - max(seg["start_s"], a)
            total += len(seg["text"].split()) * clamp(overlap / length, 0, 1)
    return total


def text_in_range(segments: list[dict[str, Any]], a: float, b: float) -> str:
    return " ".join(s["text"].strip() for s in segments if s["end_s"] > a and s["start_s"] < b).strip()


def duration_fit(duration: float, prefs: Prefs) -> float:
    if prefs.min_s <= duration <= prefs.max_s:
        return 1.0
    if duration < prefs.min_s:
        return clamp(1 - (prefs.min_s - duration) / max(prefs.min_s, 1), 0, 1)
    return clamp(1 - (duration - prefs.max_s) / max(prefs.max_s, 1), 0, 1)


def classify_moment(type_hits: dict[str, int], reaction_hits: int, speech_high: bool) -> str:
    best = None
    best_hits = 0
    for key in TYPE_PRIORITY:
        hits = type_hits.get(key, 0)
        if hits > best_hits:
            best, best_hits = key, hits
    if best:
        return best
    if reaction_hits > 0 or speech_high:
        return "reacao"
    return "jogada"


def snap_boundaries(start: float, end: float, segments: list[dict[str, Any]], tolerance: float = 4.0) -> tuple[float, float]:
    """Move the cut to sentence boundaries when one is within `tolerance` seconds."""
    new_start, new_end = start, end
    for seg in segments:
        if seg["start_s"] <= start < seg["end_s"] and start - seg["start_s"] <= tolerance:
            new_start = seg["start_s"]
        if seg["start_s"] < end <= seg["end_s"] and seg["end_s"] - end <= tolerance:
            new_end = seg["end_s"]
    if new_end - new_start < 5:
        return start, end
    return new_start, new_end


# --------------------------------------------------------------------------- planning


def plan_windows(
    audio: AudioProfile, duration_s: float, opts: AnalysisSettings, limit: int
) -> list[Window]:
    """Pick candidate windows around loudness peaks (the audio is a clue to investigate, nothing more)."""
    min_distance = max(1, int(opts.min_separation_s / audio.window_s))
    peaks = find_peaks(audio.intensity, opts.min_intensity, min_distance)
    peaks = [i for i in peaks if audio.smoothed_db[i] - audio.p50 >= MIN_GAIN_DB]
    peaks.sort(key=lambda i: audio.intensity[i] + 0.5 * audio.burst[i], reverse=True)
    windows: list[Window] = []
    for i in peaks[:limit]:
        t = audio.time_of(i)
        start = max(0.0, t - opts.pre_roll_s)
        end = min(duration_s, t + opts.post_roll_s)
        if end - start < 8:
            end = min(duration_s, start + 8)
            start = max(0.0, end - 8)
        windows.append(Window(start, end, t))
    return sorted(windows, key=lambda w: w.start)


# --------------------------------------------------------------------------- scoring


def score_window(
    window: Window,
    audio: AudioProfile,
    scene_times: list[float] | None,
    segments: list[dict[str, Any]] | None,
    ctx: ScoringContext,
) -> CandidateDraft:
    """Score one window. `segments=None` means no transcript was produced for it."""
    ws = audio.window_s
    peak = window.peak
    start, end = window.start, window.end
    transcribed = segments is not None
    segs = segments or []

    if transcribed:
        start, end = snap_boundaries(start, end, segs)
    duration = end - start

    near = _slice(audio.intensity, ws, peak - 2, peak + 2)
    f_intensity = max(near) if near else 0.0
    burst_near = _slice(audio.burst, ws, peak - 3, peak + 1)
    f_burst = max(burst_near) if burst_near else 0.0
    lead = _slice(audio.intensity, ws, peak - 8, peak - 2)
    f_tension = clamp((0.5 - _mean(lead)) / 0.5, 0, 1) * f_intensity if lead else None
    post = _slice(audio.intensity, ws, peak, peak + 8)

    features: dict[str, float | None] = {
        "audio_intensity": f_intensity,
        "audio_burst": f_burst,
        "tension": f_tension,
    }
    details: dict[str, str] = {}
    db_peak = audio.smoothed_db[audio.index(peak)] if audio.smoothed_db else 0.0
    details["audio_intensity"] = f"pico ≈ {db_peak:.0f} dB, {db_peak - audio.p50:+.0f} dB sobre a mediana da gravação"
    details["audio_burst"] = "subida de volume em relação aos 10 s anteriores"
    details["tension"] = (
        "silêncio/volume baixo logo antes do pico" if f_tension is not None
        else "sem trecho anterior suficiente"
    )

    type_hits: dict[str, int] = {}
    reaction_hits = 0
    f_speech = f_reaction = f_context = None
    excerpt = ""
    if transcribed:
        norm = normalize_text(text_in_range(segs, start, end))
        type_hits = {t: count_keyword_hits(norm, kws) for t, kws in ctx.keywords.items()}
        reaction_hits = count_keyword_hits(norm, ctx.reaction_keywords)
        weighted = sum(type_hits.values()) + 0.5 * reaction_hits
        words_total = words_in_range(segs, start, end)
        rate = words_total / max(duration, 1.0)
        f_speech = clamp(rate / 2.5, 0, 1)
        f_reaction = clamp(weighted / 3.0, 0, 1)
        before = words_in_range(segs, start, peak - 1)
        f_context = clamp(before / 8.0, 0, 1)
        features["speech"] = f_speech
        features["reaction"] = f_reaction
        features["context"] = f_context
        details["speech"] = f"{words_total:.0f} palavras em {duration:.0f} s ({rate:.1f}/s)"
        details["reaction"] = (
            f"{sum(type_hits.values())} termo(s) de evento e {reaction_hits} de reação encontrados na fala"
        )
        details["context"] = f"{before:.0f} palavras antes do pico"
        excerpt = text_in_range(segs, peak - 12, peak + 8)[:300]
    else:
        for key in ("speech", "reaction", "context"):
            features[key] = None
            details[key] = "sem transcrição neste nível de análise"

    if transcribed:
        after = words_in_range(segs, peak, end)
        payoff = clamp(after / 6.0, 0, 1)
        setup = max(f_context or 0.0, f_tension or 0.0)
        features["story"] = math.sqrt(setup * payoff)
        details["story"] = f"preparação {setup:.2f} × desfecho falado {payoff:.2f}"
    elif f_tension is not None and post:
        features["story"] = math.sqrt(f_tension * _mean(post))
        details["story"] = "calmaria antes do pico × volume sustentado depois"
    else:
        features["story"] = None
        details["story"] = "informação insuficiente"

    if scene_times is not None:
        events = [t for t in scene_times if start <= t <= end]
        features["scene_activity"] = clamp(len(events) / 3.0, 0, 1)
        details["scene_activity"] = f"{len(events)} mudança(s) de cena no trecho"
    else:
        features["scene_activity"] = None
        details["scene_activity"] = "detecção de cenas não executada neste nível"

    features["duration_fit"] = duration_fit(duration, ctx.prefs)
    details["duration_fit"] = (
        f"{duration:.0f} s (desejado {ctx.prefs.min_s}–{ctx.prefs.max_s} s)"
    )

    if transcribed:
        speech_high = (f_speech or 0) >= 0.6 and f_intensity >= 0.6
        moment_type = classify_moment(type_hits, reaction_hits, speech_high)
    else:
        moment_type = "pico_audio"

    if ctx.prefs.preferred_types:
        features["creator_pref"] = 1.0 if moment_type in ctx.prefs.preferred_types else 0.3
        details["creator_pref"] = (
            "tipo está entre os que você prioriza" if moment_type in ctx.prefs.preferred_types
            else "tipo não está entre os que você prioriza"
        )
    else:
        features["creator_pref"] = None
        details["creator_pref"] = "defina tipos prioritários no Perfil"

    available = {k: v for k, v in features.items() if v is not None and ctx.weights.get(k, 0) > 0}
    weight_sum = sum(ctx.weights[k] for k in available) or 1.0
    reasons: list[dict[str, Any]] = []
    score = 0.0
    for key, value in features.items():
        weight = ctx.weights.get(key, 0.0)
        if value is None or weight <= 0:
            reasons.append({
                "key": key, "label": FEATURE_LABELS[key], "value": None, "weight": weight,
                "points": 0.0, "detail": details.get(key, ""),
            })
            continue
        points = 100.0 * weight * value / weight_sum
        score += points
        reasons.append({
            "key": key, "label": FEATURE_LABELS[key], "value": round(value, 3), "weight": weight,
            "points": round(points, 1), "detail": details.get(key, ""),
        })
    reasons.sort(key=lambda r: r["points"], reverse=True)

    adjustment = ctx.feedback.get(moment_type, 0.0)
    if adjustment:
        score += adjustment
        reasons.append({
            "key": "feedback", "label": "Seu feedback anterior neste tipo", "value": None, "weight": 0,
            "points": round(adjustment, 1),
            "detail": "ajuste pelas aprovações/rejeições e resultados que você já marcou",
        })
    score = clamp(score, 0, 100)

    strong = sum(
        1 for key, threshold in (("audio_intensity", 0.6), ("audio_burst", 0.5), ("speech", 0.4),
                                 ("reaction", 0.3), ("scene_activity", 0.3))
        if (features.get(key) or 0) >= threshold
    )
    if any(count > 0 for count in type_hits.values()):
        strong += 1
    confidence = "alta" if strong >= 4 else "média" if strong >= 2 else "baixa"

    label = MOMENT_TYPES[moment_type]
    snippet = ""
    if transcribed:
        words = text_in_range(segs, peak - 3, peak + 3).split()
        snippet = " ".join(words[:8])
    title = f"{label} · {fmt_hms(peak)}"
    if snippet:
        title += f" — “{snippet}”"
    return CandidateDraft(
        start_s=start, end_s=end, peak_s=peak, title=title[:120], moment_type=moment_type,
        score=score, confidence=confidence, reasons=reasons, excerpt=excerpt,
    )


def suppress_overlaps(drafts: list[CandidateDraft], max_overlap: float = 0.5) -> list[CandidateDraft]:
    """Keep the best-scoring candidate when several overlap more than `max_overlap`."""
    kept: list[CandidateDraft] = []
    for draft in sorted(drafts, key=lambda d: d.score, reverse=True):
        clash = False
        for other in kept:
            overlap = min(draft.end_s, other.end_s) - max(draft.start_s, other.start_s)
            shortest = min(draft.end_s - draft.start_s, other.end_s - other.start_s)
            if overlap > 0 and shortest > 0 and overlap / shortest > max_overlap:
                clash = True
                break
        if not clash:
            kept.append(draft)
    return kept


def feedback_adjustments(rows: list[dict[str, Any]]) -> dict[str, float]:
    """Turn past review decisions into small per-type score nudges (max ±10 points).

    `rows`: dicts with moment_type, status ('approved'|'rejected'|'pending') and outcome ('good'|'bad'|None).
    """
    tally: dict[str, list[float]] = {}
    for row in rows:
        votes = tally.setdefault(row["moment_type"], [0.0, 0.0])
        if row["status"] == "approved":
            votes[0] += 1
        elif row["status"] == "rejected":
            votes[1] += 1
        if row.get("outcome") == "good":
            votes[0] += 1
        elif row.get("outcome") == "bad":
            votes[1] += 1
    adjustments: dict[str, float] = {}
    for moment_type, (positive, negative) in tally.items():
        total = positive + negative
        if total <= 0:
            continue
        adjustments[moment_type] = clamp((positive - negative) / (total + 3.0) * 10.0, -10.0, 10.0)
    return adjustments


_WS = re.compile(r"\s+")


def clean_text(text: str) -> str:
    return _WS.sub(" ", text).strip()
