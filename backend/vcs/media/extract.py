"""Signal extraction with FFmpeg: audio loudness envelope, scene changes, audio windows for ASR."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..errors import AppError, InvalidInput
from .ffmpeg import FFmpegTools
from .progress import FfmpegProgress

SILENCE_DB = -90.0
_PTS = re.compile(r"pts_time:([0-9.]+)")


def _ffmpeg_error(prefix: str, stderr_tail: str) -> AppError:
    detail = [line for line in stderr_tail.splitlines() if line.strip()][-3:]
    return AppError(f"{prefix}: {' | '.join(detail) or 'erro desconhecido do FFmpeg'}", code="ffmpeg_failed")


def parse_astats_metadata(text: str, window_s: float, expected: int | None = None) -> list[float]:
    """Parse `ametadata=print` output (RMS level per audio frame) into one dB value per window."""
    values: dict[int, float] = {}
    current_index: int | None = None
    for line in text.splitlines():
        if line.startswith("frame:"):
            match = _PTS.search(line)
            current_index = int(round(float(match.group(1)) / window_s)) if match else None
        elif "Overall.RMS_level=" in line and current_index is not None:
            raw = line.split("=", 1)[1].strip()
            try:
                db = float(raw)
            except ValueError:
                db = SILENCE_DB
            if db != db or db < SILENCE_DB:  # NaN or -inf
                db = SILENCE_DB
            values[current_index] = db
    if not values:
        return []
    size = max(values) + 1
    if expected is not None:
        size = max(size, expected)
    return [values.get(i, SILENCE_DB) for i in range(size)]


def parse_scene_metadata(text: str) -> list[tuple[float, float]]:
    """Parse `metadata=print:key=lavfi.scene_score` output into (time_s, score) pairs."""
    out: list[tuple[float, float]] = []
    current: float | None = None
    for line in text.splitlines():
        if line.startswith("frame:"):
            match = _PTS.search(line)
            current = float(match.group(1)) if match else None
        elif "lavfi.scene_score=" in line and current is not None:
            try:
                out.append((current, float(line.split("=", 1)[1].strip())))
            except ValueError:
                continue
    return out


def extract_audio_envelope(
    tools: FFmpegTools,
    path: Path,
    *,
    ctx: Any,
    window_s: float,
    stream_index: int,
    duration_s: float | None,
    label: str = "Medindo o volume do áudio",
) -> list[float]:
    """Loudness (RMS, dB) per `window_s` seconds of audio. Real progress from FFmpeg."""
    ffmpeg = tools.require_ffmpeg()
    samples = max(1, int(16000 * window_s))
    out_name = "audio_rms.txt"
    af = (
        f"aresample=16000,asetnsamples=n={samples}:p=0,astats=metadata=1:reset=1,"
        f"ametadata=mode=print:key=lavfi.astats.Overall.RMS_level:file={out_name}"
    )
    progress = FfmpegProgress(ctx, duration_s, label)
    progress.start()
    result = ctx.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-progress", "pipe:1", "-nostats",
         "-protocol_whitelist", "file", "-i", str(path), "-map", f"0:a:{stream_index}", "-vn", "-af", af,
         "-f", "null", "-"],
        on_line=progress.feed, cwd=ctx.temp_dir,
    )
    if result.returncode != 0:
        raise _ffmpeg_error("Falha ao analisar o áudio", result.stderr_tail)
    output = ctx.temp_dir / out_name
    if not output.is_file():
        raise InvalidInput("Não foi possível extrair o volume do áudio desta gravação.")
    expected = int(duration_s / window_s) if duration_s else None
    values = parse_astats_metadata(output.read_text(encoding="utf-8", errors="replace"), window_s, expected)
    output.unlink(missing_ok=True)
    if not values:
        raise InvalidInput("O áudio da gravação parece vazio: nada para analisar.")
    return values


def detect_scene_changes(
    tools: FFmpegTools,
    path: Path,
    *,
    ctx: Any,
    threshold: float,
    duration_s: float | None,
    label: str = "Detectando mudanças de cena",
) -> list[tuple[float, float]]:
    """Scene-change events (time_s, score >= threshold). Video is analysed at 2 fps, 320 px wide."""
    ffmpeg = tools.require_ffmpeg()
    out_name = "scenes.txt"
    vf = (
        "fps=2,scale=320:-2,"
        f"select='gt(scene,{threshold:.3f})+not(mod(n,2))',"
        f"metadata=mode=print:key=lavfi.scene_score:file={out_name}"
    )
    progress = FfmpegProgress(ctx, duration_s, label)
    progress.start()
    result = ctx.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-progress", "pipe:1", "-nostats",
         "-protocol_whitelist", "file", "-i", str(path), "-an", "-sn", "-vf", vf, "-f", "null", "-"],
        on_line=progress.feed, cwd=ctx.temp_dir,
    )
    if result.returncode != 0:
        raise _ffmpeg_error("Falha ao detectar cenas", result.stderr_tail)
    output = ctx.temp_dir / out_name
    if not output.is_file():
        return []
    samples = parse_scene_metadata(output.read_text(encoding="utf-8", errors="replace"))
    output.unlink(missing_ok=True)
    return [(t, s) for t, s in samples if s >= threshold]


def extract_wav_window(
    tools: FFmpegTools,
    path: Path,
    *,
    ctx: Any,
    start_s: float,
    duration_s: float,
    stream_index: int,
    out_path: Path,
) -> Path:
    """Cut [start, start+duration) of the audio into a 16 kHz mono WAV (for speech recognition)."""
    ffmpeg = tools.require_ffmpeg()
    result = ctx.run(
        [ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-y", "-ss", f"{max(0.0, start_s):.3f}",
         "-t", f"{duration_s:.3f}", "-protocol_whitelist", "file", "-i", str(path), "-map", f"0:a:{stream_index}", "-vn",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out_path)],
    )
    if result.returncode != 0 or not out_path.is_file():
        raise _ffmpeg_error("Falha ao extrair o trecho de áudio", result.stderr_tail)
    return out_path
