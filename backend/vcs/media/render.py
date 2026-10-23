"""Vertical (9:16) clip rendering with FFmpeg, plus on-demand subtitle transcription for a clip.

Rendering only ever happens when the user asks for it (a job). Commands are argument lists built
from validated settings - the UI cannot inject arbitrary FFmpeg arguments.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import AppError, InvalidInput, NotFound
from ..jobs.manager import JobCancelled
from ..models import RenderConfig, SubtitleStyle
from ..security import error_text, safe_filename
from ..utils import utcnow
from .extract import extract_wav_window
from .progress import FfmpegProgress
from .subtitles import build_ass, cues_from_segments
from .transcribe import build_transcriber

PREVIEW_WIDTH = 540
_FONT_WARNING = re.compile(r"fontselect|fontconfig|Parsed_ass|libass", re.IGNORECASE)


def _even(value: float) -> int:
    return max(2, int(value) // 2 * 2)


def _hex_for_ffmpeg(color: str) -> str:
    return "0x" + color.lstrip("#").upper()


def video_graph(cfg: RenderConfig, src_w: int, src_h: int, out_w: int, out_h: int) -> str:
    """Filter chain producing the label [vbase] (before subtitles)."""
    pre: list[str] = []
    if cfg.fps:
        pre.append(f"fps={cfg.fps}")
    if cfg.crop:
        cw = _even(cfg.crop.w * src_w)
        ch = _even(cfg.crop.h * src_h)
        cx = min(_even(cfg.crop.x * src_w), max(0, src_w - cw))
        cy = min(_even(cfg.crop.y * src_h), max(0, src_h - ch))
        pre.append(f"crop={cw}:{ch}:{cx}:{cy}")
    head = "[0:v:0]" + (",".join(pre) + "," if pre else "")

    if cfg.layout == "solid":
        return (
            f"{head}scale={out_w}:{out_h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1,"
            f"pad={out_w}:{out_h}:(ow-iw)/2:(oh-ih)/2:color={_hex_for_ffmpeg(cfg.background_color)},"
            "format=yuv420p[vbase]"
        )
    if cfg.layout == "fill":
        return (
            f"{head}scale={out_w}:{out_h}:force_original_aspect_ratio=increase,"
            f"crop={out_w}:{out_h}:(iw-ow)*{cfg.focus_x:.4f}:(ih-oh)/2,setsar=1,format=yuv420p[vbase]"
        )
    bw, bh = _even(out_w / 4), _even(out_h / 4)
    return (
        f"{head}split=2[bgsrc][fgsrc];"
        f"[bgsrc]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},boxblur=10:2,"
        f"scale={out_w}:{out_h},setsar=1[bg];"
        f"[fgsrc]scale={out_w}:{out_h}:force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1[fg];"
        "[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p[vbase]"
    )


def audio_graph(cfg: RenderConfig, stream_index: int, duration: float) -> str:
    parts = ["anull"]
    if cfg.volume_db:
        parts.append(f"volume={cfg.volume_db:.1f}dB")
    if cfg.loudnorm:
        parts += ["loudnorm=I=-14:TP=-1.5:LRA=11", "aresample=48000"]
    if cfg.fade_s > 0 and duration > cfg.fade_s * 2 + 0.1:
        parts.append(f"afade=t=in:st=0:d={cfg.fade_s:.2f}")
        parts.append(f"afade=t=out:st={duration - cfg.fade_s:.3f}:d={cfg.fade_s:.2f}")
    return f"[0:a:{stream_index}]" + ",".join(parts) + "[aout]"


def encoder_args(cfg: RenderConfig, preview: bool) -> list[str]:
    if preview:
        return ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p"]
    if cfg.encoder == "h264_amf":
        return ["-c:v", "h264_amf", "-quality", "quality", "-rc", "vbr_peak", "-b:v", f"{cfg.bitrate_kbps}k",
                "-maxrate", f"{int(cfg.bitrate_kbps * 1.5)}k", "-pix_fmt", "yuv420p"]
    if cfg.encoder == "h264_nvenc":
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", str(cfg.crf), "-b:v", "0",
                "-pix_fmt", "yuv420p"]
    if cfg.encoder == "h264_qsv":
        return ["-c:v", "h264_qsv", "-global_quality", str(cfg.crf), "-pix_fmt", "nv12"]
    return ["-c:v", "libx264", "-preset", cfg.preset, "-crf", str(cfg.crf), "-profile:v", "high",
            "-pix_fmt", "yuv420p"]


@dataclass
class RenderPlan:
    args: list[str]
    graph: str
    ass_text: str | None
    out_w: int
    out_h: int
    duration: float
    notes: list[str]


def build_plan(
    *,
    ffmpeg: str,
    src: Path,
    start_s: float,
    end_s: float,
    cfg: RenderConfig,
    style: SubtitleStyle,
    cues: list[dict[str, Any]],
    src_w: int,
    src_h: int,
    has_audio: bool,
    audio_stream_index: int,
    out_path: Path,
    preview: bool,
    ass_filter_available: bool,
) -> RenderPlan:
    duration = end_s - start_s
    if preview:
        out_w = _even(PREVIEW_WIDTH)
        out_h = _even(cfg.height * PREVIEW_WIDTH / cfg.width)
    else:
        out_w, out_h = cfg.width, cfg.height
    notes: list[str] = []

    graph = video_graph(cfg, src_w, src_h, out_w, out_h)
    ass_text: str | None = None
    if cfg.subtitles and cues:
        if ass_filter_available:
            ass_text = build_ass(cues, style, out_w, out_h)
        else:
            notes.append("Legendas não aplicadas: esta build do FFmpeg não tem o filtro 'ass' (use uma build com libass, como a 'essentials' ou a 'full' da gyan.dev).")
    graph += ";[vbase]ass=filename=subs.ass[vout]" if ass_text else ";[vbase]null[vout]"
    if has_audio:
        graph += ";" + audio_graph(cfg, audio_stream_index, duration)

    args = [
        # "warning" (not "error") so libass/font problems reach stderr and can be shown to the user.
        ffmpeg, "-nostdin", "-hide_banner", "-v", "warning", "-y", "-progress", "pipe:1", "-nostats",
        "-ss", f"{start_s:.3f}", "-t", f"{duration:.3f}", "-protocol_whitelist", "file", "-i", str(src),
        "-filter_complex", graph, "-map", "[vout]",
    ]
    args += ["-map", "[aout]"] if has_audio else ["-an"]
    args += encoder_args(cfg, preview)
    if has_audio:
        args += ["-c:a", "aac", "-b:a", f"{96 if preview else cfg.audio_bitrate_kbps}k", "-ar", "48000"]
    args += ["-movflags", "+faststart", "-f", "mp4", str(out_path)]
    return RenderPlan(args, graph, ass_text, out_w, out_h, duration, notes)


def _unique_output(out_dir: Path, base: str, current: str | None) -> Path:
    candidate = out_dir / f"{base}.mp4"
    n = 2
    while candidate.exists() and str(candidate) != (current or ""):
        candidate = out_dir / f"{base}_{n}.mp4"
        n += 1
    return candidate


def load_clip_context(app: Any, clip_id: int) -> tuple[dict, dict, RenderConfig, SubtitleStyle]:
    clip = app.repos.clips.require(clip_id)
    recording = app.repos.recordings.require(clip["recording_id"])
    settings = app.settings.load()
    cfg = RenderConfig.model_validate(clip["render_config"] or settings.render.model_dump())
    style = SubtitleStyle.model_validate(clip["subtitle_style"] or settings.subtitle_style.model_dump())
    return clip, recording, cfg, style


def plan_for_clip(app: Any, clip_id: int, mode: str, out_path: Path) -> tuple[RenderPlan, dict, dict]:
    clip, recording, cfg, style = load_clip_context(app, clip_id)
    src = Path(recording["path"])
    ffmpeg = app.tools.require_ffmpeg()
    if not recording.get("width") or not recording.get("height"):
        raise InvalidInput("Resolução da gravação desconhecida. Importe o arquivo novamente.")
    if clip["end_s"] - clip["start_s"] < 1:
        raise InvalidInput("O corte precisa ter pelo menos 1 segundo.")
    has_audio = int(recording.get("audio_streams") or 0) > 0
    plan = build_plan(
        ffmpeg=ffmpeg, src=src, start_s=clip["start_s"], end_s=clip["end_s"], cfg=cfg, style=style,
        cues=clip["subtitles"] or [], src_w=recording["width"], src_h=recording["height"],
        has_audio=has_audio, audio_stream_index=app.settings.load().analysis.audio_stream_index,
        out_path=out_path, preview=(mode == "preview"),
        ass_filter_available="ass" in app.tools.filters(),
    )
    return plan, clip, recording


def render_clip(ctx: Any, app: Any, clip_id: int, mode: str) -> dict[str, Any]:
    if mode not in ("final", "preview"):
        raise InvalidInput("Modo de renderização inválido (final ou preview).")
    clip, recording, cfg, _style = load_clip_context(app, clip_id)
    src = Path(recording["path"])
    if not src.is_file():
        raise AppError("O arquivo da gravação original não foi encontrado (foi movido ou apagado?).",
                       code="file_missing")
    preview = mode == "preview"
    try:
        if preview:
            app.config.previews_dir.mkdir(parents=True, exist_ok=True)
            final_path = app.config.previews_dir / f"clip_{clip_id}.mp4"
        else:
            out_dir = app.settings.effective_output_dir(create=True)
            base = safe_filename(f"{src.stem}_c{clip_id}_{int(clip['start_s'])}-{int(clip['end_s'])}")
            final_path = _unique_output(out_dir, base, clip.get("output_path"))
    except OSError as exc:
        raise AppError(
            f"Não foi possível usar a pasta de saída ({exc.strerror or exc}). Escolha outra em Configurações > Pastas e integrações.",
            code="output_dir_unavailable",
        ) from exc
    tmp_path = final_path.with_name(final_path.name + ".part")

    plan, clip, recording = plan_for_clip(app, clip_id, mode, tmp_path)
    if plan.ass_text:
        (ctx.temp_dir / "subs.ass").write_text(plan.ass_text, encoding="utf-8")
    if plan.notes:
        ctx.set_message(" ".join(plan.notes))

    secrets = app.config.secrets()
    if not preview:
        app.repos.clips.update(clip_id, status="rendering", last_error=None)
    # The in-progress file is registered so the cleanup tool can find leftovers of an interrupted render
    # (and so it never has to guess which *.part files belong to this app).
    app.repos.artifacts.register("temp", str(tmp_path), None, recording_id=recording["id"], clip_id=clip_id)
    progress = FfmpegProgress(ctx, plan.duration, "Renderizando prévia" if preview else "Renderizando corte")
    progress.start()
    try:
        result = ctx.run(plan.args, on_line=progress.feed, cwd=ctx.temp_dir)
        if result.returncode != 0:
            detail = " | ".join([ln for ln in result.stderr_tail.splitlines() if ln.strip()][-3:])
            hint = ""
            if cfg.encoder != "libx264" and not preview:
                hint = f" Dica: teste o encoder '{cfg.encoder}' em Configurações ou volte para libx264 (CPU)."
            raise AppError(f"O FFmpeg falhou ao renderizar: {detail or 'erro desconhecido'}.{hint}",
                           code="ffmpeg_failed")
        try:
            os.replace(tmp_path, final_path)
        except PermissionError as exc:
            raise AppError("Não foi possível salvar o arquivo: feche o vídeo se ele estiver aberto em outro programa.") from exc
    except BaseException as exc:
        tmp_path.unlink(missing_ok=True)
        _forget_temp(app, tmp_path)
        if not preview:
            message = None if isinstance(exc, JobCancelled) else error_text(exc, secrets)
            try:
                app.repos.clips.update(clip_id, status="ready" if clip.get("output_path") else "draft",
                                       last_error=message)
            except NotFound:
                pass  # the clip was deleted while rendering
        raise
    _forget_temp(app, tmp_path)
    notes = list(plan.notes)
    if plan.ass_text:
        font_lines = [ln.strip() for ln in result.stderr_tail.splitlines() if _FONT_WARNING.search(ln)]
        if font_lines:
            notes.append(
                "O FFmpeg avisou sobre as fontes das legendas (elas podem não aparecer): " + " | ".join(font_lines[:3])
            )
            ctx.set_message(" ".join(notes))
    size = final_path.stat().st_size
    try:
        if preview:
            app.repos.clips.update(clip_id, preview_path=str(final_path))
        else:
            app.repos.clips.update(clip_id, status="ready", output_path=str(final_path), output_size=size,
                                   rendered_at=utcnow(), last_error=None)
    except NotFound as exc:
        final_path.unlink(missing_ok=True)
        raise AppError("O corte foi excluído durante a renderização; o arquivo gerado foi descartado.") from exc
    app.repos.artifacts.register("preview" if preview else "export", str(final_path), size,
                                 recording_id=recording["id"], clip_id=clip_id)
    return {"output_path": str(final_path), "size_bytes": size, "mode": mode, "notes": notes}


def _forget_temp(app: Any, tmp_path: Path) -> None:
    app.db.execute("DELETE FROM artifacts WHERE path = ? AND kind = 'temp'", (str(tmp_path),))


def transcribe_clip(ctx: Any, app: Any, clip_id: int, *, allow_download: bool) -> dict[str, Any]:
    """Transcribe only the clip's time range and fill its subtitle cues."""
    clip = app.repos.clips.require(clip_id)
    recording = app.repos.recordings.require(clip["recording_id"])
    src = Path(recording["path"])
    if not src.is_file():
        raise AppError("O arquivo da gravação original não foi encontrado.", code="file_missing")
    if int(recording.get("audio_streams") or 0) == 0:
        raise InvalidInput("A gravação não tem áudio para transcrever.")
    settings = app.settings.load()
    start, end = clip["start_s"], clip["end_s"]
    ctx.set_progress(None, "Preparando o áudio do corte", force=True)
    wav = ctx.temp_dir / "clip.wav"
    extract_wav_window(app.tools, src, ctx=ctx, start_s=start, duration_s=end - start,
                       stream_index=settings.analysis.audio_stream_index, out_path=wav)
    ctx.set_progress(None, "Transcrevendo o corte (sem estimativa de progresso)", force=True)
    transcriber = build_transcriber(settings, app.config.models_dir, allow_download=allow_download)
    found = transcriber.transcribe_file(wav, offset_s=start, ctx=ctx)
    rows = [s.to_dict() for s in found]
    app.repos.segments.replace_for_ranges(recording["id"], [(start, end)], rows)
    cues = cues_from_segments(rows, start, end)
    app.repos.clips.update(clip_id, subtitles=cues)
    return {"cues": len(cues)}
