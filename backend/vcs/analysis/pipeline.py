"""Recording analysis pipeline: audio envelope -> (scenes) -> (transcription) -> scored candidates.

Runs inside a background job. Progress is reported per stage from real information only
(FFmpeg time processed, or windows transcribed / windows total).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import AppError, InvalidInput
from ..jobs.manager import JobCancelled
from ..media.extract import detect_scene_changes, extract_audio_envelope, extract_wav_window
from ..media.transcribe import build_transcriber
from ..security import error_text
from ..utils import dumps, utcnow
from .candidates import (
    CandidateDraft,
    Prefs,
    ScoringContext,
    feedback_adjustments,
    plan_windows,
    score_window,
    suppress_overlaps,
)
from .signals import build_audio_profile

log = logging.getLogger(__name__)

FULL_CHUNK_S = 300.0
WINDOW_PAD_S = 2.0

LEVEL_INFO: dict[str, dict[str, Any]] = {
    "leve": {
        "label": "Leve",
        "description": "Só o áudio. Rápido e sem downloads. Sem transcrição, os títulos e tipos ficam genéricos.",
        "scenes": False,
        "transcription": "off",
        "model": None,
        "warnings": [],
    },
    "padrao": {
        "label": "Padrão (recomendado)",
        "description": "Áudio + transcrição apenas dos trechos candidatos. Equilibra tempo e qualidade em CPU.",
        "scenes": False,
        "transcription": "candidates",
        "model": "base",
        "warnings": [
            "Baixa o modelo de transcrição 'base' (≈145 MB) uma única vez, com a sua confirmação.",
            "A transcrição roda na CPU (GPU AMD não é usada pelo faster-whisper no Windows).",
        ],
    },
    "detalhado": {
        "label": "Detalhado",
        "description": "Áudio + mudanças de cena + transcrição dos candidatos com um modelo maior.",
        "scenes": True,
        "transcription": "candidates",
        "model": "small",
        "warnings": [
            "Baixa o modelo 'small' (≈480 MB) uma única vez, com a sua confirmação.",
            "A detecção de cenas decodifica o vídeo inteiro: em gravações longas pode levar mais tempo que a duração do vídeo.",
        ],
    },
    "completo": {
        "label": "Completo",
        "description": "Transcreve a gravação inteira. Só vale a pena se você precisa do texto de tudo.",
        "scenes": True,
        "transcription": "full",
        "model": "small",
        "warnings": [
            "Transcrever tudo na CPU pode levar várias vezes a duração da gravação.",
            "Usa bastante CPU e memória durante todo o processo.",
        ],
    },
}


@dataclass
class Plan:
    level: str
    scenes: bool
    transcription: str  # off | candidates | full
    model: str | None


def resolve_plan(level: str, scenes: bool | None, transcription: str | None, model: str | None) -> Plan:
    if level not in LEVEL_INFO:
        raise InvalidInput(f"Nível de análise inválido. Use: {', '.join(LEVEL_INFO)}.")
    info = LEVEL_INFO[level]
    plan_transcription = transcription or info["transcription"]
    if plan_transcription not in ("off", "candidates", "full"):
        raise InvalidInput("Modo de transcrição inválido (off, candidates ou full).")
    return Plan(
        level=level,
        scenes=info["scenes"] if scenes is None else scenes,
        transcription=plan_transcription,
        model=model or info["model"],
    )


def merge_ranges(ranges: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def chunk_ranges(duration_s: float, chunk_s: float = FULL_CHUNK_S) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_s:
        out.append((start, min(duration_s, start + chunk_s)))
        start += chunk_s
    return out


def _scoring_context(app: Any) -> ScoringContext:
    settings = app.settings.load()
    profile = app.settings.load_profile()
    rows = app.db.query("SELECT moment_type, status, outcome FROM candidates")
    return ScoringContext(
        weights=settings.scoring_weights.model_dump(),
        keywords=settings.keywords,
        reaction_keywords=settings.reaction_keywords,
        prefs=Prefs(
            preferred_types=profile.preferred_types,
            min_s=profile.preferred_duration_min_s,
            max_s=profile.preferred_duration_max_s,
        ),
        feedback=feedback_adjustments(rows),
    )


def _overlaps_reviewed(draft: CandidateDraft, reviewed: list[dict[str, Any]]) -> bool:
    for row in reviewed:
        overlap = min(draft.end_s, row["end_s"]) - max(draft.start_s, row["start_s"])
        shortest = min(draft.end_s - draft.start_s, row["end_s"] - row["start_s"])
        if overlap > 0 and shortest > 0 and overlap / shortest > 0.5:
            return True
    return False


def run_analysis(
    ctx: Any,
    app: Any,
    recording_id: int,
    plan: Plan,
    *,
    allow_download: bool = False,
) -> dict[str, Any]:
    recording = app.repos.recordings.require(recording_id)
    path = Path(recording["path"])
    if not path.is_file():
        raise AppError(
            "O arquivo desta gravação não foi encontrado no disco (foi movido ou apagado?). "
            "Importe-o novamente pelo novo local.",
            code="file_missing",
        )
    prior_done = app.repos.analyses.count("recording_id = ? AND status = 'done'", (recording_id,)) > 0
    analysis = app.repos.analyses.insert(
        recording_id=recording_id, job_id=ctx.job_id, level=plan.level, status="running",
        options={"scenes": plan.scenes, "transcription": plan.transcription, "model": plan.model},
    )
    app.repos.recordings.update(recording_id, status="analyzing", last_error=None)
    try:
        stats = _execute(ctx, app, recording, path, plan, analysis["id"], allow_download)
    except JobCancelled:
        app.repos.analyses.update(analysis["id"], status="cancelled", finished_at=utcnow())
        app.repos.recordings.update(recording_id, status="analyzed" if prior_done else "imported")
        raise
    except Exception as exc:
        message = error_text(exc, app.config.secrets())
        app.repos.analyses.update(analysis["id"], status="error", error=message, finished_at=utcnow())
        app.repos.recordings.update(
            recording_id, status="analyzed" if prior_done else "imported", last_error=message
        )
        raise
    app.repos.analyses.update(analysis["id"], status="done", stats=stats, finished_at=utcnow())
    app.repos.recordings.update(recording_id, status="analyzed")
    return {"analysis_id": analysis["id"], **stats}


def _execute(ctx: Any, app: Any, recording: dict[str, Any], path: Path, plan: Plan,
             analysis_id: int, allow_download: bool) -> dict[str, Any]:
    settings = app.settings.load()
    opts = settings.analysis
    duration = float(recording["duration_s"] or 0)
    if duration <= 0:
        raise InvalidInput("Duração da gravação desconhecida. Importe o arquivo novamente.")
    audio_streams = int(recording.get("audio_streams") or 0)
    if audio_streams == 0:
        raise InvalidInput("Esta gravação não tem faixa de áudio; a análise automática depende do áudio.")
    stream_index = opts.audio_stream_index
    if stream_index >= audio_streams:
        raise InvalidInput(
            f"A gravação tem {audio_streams} faixa(s) de áudio, mas 'audio_stream_index' está em {stream_index}. "
            "Ajuste em Configurações > Análise."
        )

    stages = ["audio"] + (["scenes"] if plan.scenes else []) + (
        ["transcription"] if plan.transcription != "off" else []) + ["score"]
    names = {
        "audio": "Medindo o volume do áudio",
        "scenes": "Detectando mudanças de cena",
        "transcription": "Transcrevendo",
        "score": "Pontuando candidatos",
    }

    def label(stage: str, extra: str = "") -> str:
        return f"Etapa {stages.index(stage) + 1}/{len(stages)}: {names[stage]}{extra}"

    ctx.check_cancelled()
    rms = extract_audio_envelope(
        app.tools, path, ctx=ctx, window_s=opts.audio_window_s, stream_index=stream_index,
        duration_s=duration, label=label("audio"),
    )
    audio = build_audio_profile(rms, opts.audio_window_s)
    app.db.execute(
        "INSERT OR REPLACE INTO analysis_signals (analysis_id, kind, data) VALUES (?, 'audio', ?)",
        (analysis_id, dumps({
            "window_s": opts.audio_window_s, "rms_db": [round(v, 1) for v in rms],
            "p50": round(audio.p50, 2), "p95": round(audio.p95, 2),
        })),
    )

    scene_events: list[tuple[float, float]] | None = None
    if plan.scenes:
        ctx.check_cancelled()
        scene_events = detect_scene_changes(
            app.tools, path, ctx=ctx, threshold=opts.scene_threshold, duration_s=duration,
            label=label("scenes"),
        )
        app.db.execute(
            "INSERT OR REPLACE INTO analysis_signals (analysis_id, kind, data) VALUES (?, 'scenes', ?)",
            (analysis_id, dumps({"threshold": opts.scene_threshold,
                                 "events": [[round(t, 2), round(s, 3)] for t, s in scene_events]})),
        )
    scene_times = [t for t, _ in scene_events] if scene_events is not None else None

    sctx = _scoring_context(app)
    limit = max(opts.max_candidates * 2, 10)
    windows = plan_windows(audio, duration, opts, limit)

    # -- transcription ------------------------------------------------------------
    transcribed: list[tuple[float, float]] = []
    segments: list[dict[str, Any]] = []
    transcribed_seconds = 0.0
    if plan.transcription != "off":
        if plan.transcription == "full":
            ranges = chunk_ranges(duration)
        else:
            ranges = merge_ranges([
                (max(0.0, w.start - WINDOW_PAD_S), min(duration, w.end + WINDOW_PAD_S)) for w in windows
            ])
        transcriber = build_transcriber(settings, app.config.models_dir, allow_download=allow_download,
                                        model_override=plan.model)
        for i, (a, b) in enumerate(ranges):
            ctx.check_cancelled()
            ctx.set_progress(i / len(ranges), label("transcription", f" ({i + 1}/{len(ranges)})"), force=True)
            wav = ctx.temp_dir / f"win_{i}.wav"
            extract_wav_window(app.tools, path, ctx=ctx, start_s=a, duration_s=b - a,
                               stream_index=stream_index, out_path=wav)
            found = transcriber.transcribe_file(wav, offset_s=a, ctx=ctx)
            wav.unlink(missing_ok=True)
            rows = [dict(s.to_dict(), analysis_id=analysis_id) for s in found]
            app.repos.segments.replace_for_ranges(recording["id"], [(a, b)], rows)
            segments.extend(s.to_dict() for s in found)
            transcribed.append((a, b))
            transcribed_seconds += b - a
        ctx.set_progress(1.0, label("transcription"), force=True)

    # -- scoring ------------------------------------------------------------------
    ctx.set_progress(None, label("score"), force=True)
    drafts: list[CandidateDraft] = []
    # Merge first: in "completo" mode the 5-minute chunks are adjacent, and a window that crosses a
    # chunk boundary is still fully transcribed.
    covered_ranges = merge_ranges(transcribed)
    for window in windows:
        covered = any(a - 0.5 <= window.start and window.end <= b + 0.5 for a, b in covered_ranges)
        window_segments = (
            [s for s in segments if s["end_s"] > window.start and s["start_s"] < window.end]
            if covered else None
        )
        drafts.append(score_window(window, audio, scene_times, window_segments, sctx))
    drafts = suppress_overlaps(drafts)[: opts.max_candidates]

    app.db.execute(
        "DELETE FROM candidates WHERE recording_id = ? AND status = 'pending' AND manual = 0",
        (recording["id"],),
    )
    reviewed = app.repos.candidates.list(
        "recording_id = ? AND (status != 'pending' OR manual = 1)", (recording["id"],)
    )
    created = 0
    for draft in drafts:
        if _overlaps_reviewed(draft, reviewed):
            continue
        app.repos.candidates.insert(
            recording_id=recording["id"], analysis_id=analysis_id, status="pending", manual=0,
            tags=[], **draft.to_row(),
        )
        created += 1

    stats: dict[str, Any] = {
        "audio_windows": len(rms),
        "peaks_considered": len(windows),
        "candidates_created": created,
        "scene_events": len(scene_events) if scene_events is not None else None,
        "transcribed_seconds": round(transcribed_seconds, 1),
        "transcription": plan.transcription,
        "model": plan.model if plan.transcription != "off" else None,
    }
    if not windows:
        stats["hint"] = (
            "Nenhum pico de áudio relevante foi encontrado. Reduza 'min_intensity' em Configurações > Análise "
            "ou crie cortes manualmente."
        )
    return stats
