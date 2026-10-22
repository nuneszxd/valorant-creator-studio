"""FFmpeg / ffprobe discovery and media probing.

Imported files are untrusted input: probing runs with a timeout and only through ffprobe.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any

from ..errors import InvalidInput, Unavailable
from ..jobs.procs import run_capture
from ..utils import loads

_FLAGS = re.compile(r"^[A-Za-z.]{2,8}$")


@dataclass
class MediaInfo:
    duration_s: float | None
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    audio_streams: int
    size_bytes: int | None
    container: str | None
    bit_rate: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_fps(value: Any) -> float | None:
    if not value or value in ("0/0", "N/A"):
        return None
    try:
        fps = float(Fraction(str(value)))
    except (ValueError, ZeroDivisionError):
        return None
    return round(fps, 3) if fps > 0 else None


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def parse_probe(data: dict[str, Any], size_bytes: int | None = None) -> MediaInfo:
    streams = data.get("streams") or []
    fmt = data.get("format") or {}
    videos = [
        s for s in streams
        if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")
    ]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    if not videos:
        raise InvalidInput("O arquivo não contém uma faixa de vídeo.")
    video = videos[0]
    duration = _to_float(fmt.get("duration")) or _to_float(video.get("duration"))
    return MediaInfo(
        duration_s=duration,
        width=_to_int(video.get("width")),
        height=_to_int(video.get("height")),
        fps=parse_fps(video.get("avg_frame_rate")) or parse_fps(video.get("r_frame_rate")),
        video_codec=video.get("codec_name"),
        audio_codec=audios[0].get("codec_name") if audios else None,
        audio_streams=len(audios),
        size_bytes=_to_int(fmt.get("size")) or size_bytes,
        container=fmt.get("format_name"),
        bit_rate=_to_int(fmt.get("bit_rate")),
    )


def parse_ffmpeg_list(output: str) -> set[str]:
    """Parse `ffmpeg -encoders` / `-filters` output into a set of names."""
    names: set[str] = set()
    in_table = False
    for line in output.splitlines():
        stripped = line.strip()
        if stripped.startswith("------"):
            in_table = True
            continue
        if not in_table or not stripped:
            continue
        parts = stripped.split(None, 2)
        if len(parts) >= 2 and _FLAGS.match(parts[0]):
            names.add(parts[1])
    return names


class FFmpegTools:
    def __init__(self, ffmpeg: str | None, ffprobe: str | None) -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self._cache: dict[str, Any] = {}

    @classmethod
    def discover(cls, ffmpeg_path: str | None = None, ffprobe_path: str | None = None) -> "FFmpegTools":
        ffmpeg = None
        if ffmpeg_path:
            ffmpeg = ffmpeg_path if Path(ffmpeg_path).is_file() else None
        else:
            ffmpeg = shutil.which("ffmpeg")
        ffprobe = None
        if ffprobe_path:
            ffprobe = ffprobe_path if Path(ffprobe_path).is_file() else None
        else:
            if ffmpeg:
                sibling = Path(ffmpeg).with_name("ffprobe" + Path(ffmpeg).suffix)
                if sibling.is_file():
                    ffprobe = str(sibling)
            ffprobe = ffprobe or shutil.which("ffprobe")
        return cls(ffmpeg, ffprobe)

    # -- availability -------------------------------------------------------------
    def require_ffmpeg(self) -> str:
        if not self.ffmpeg:
            raise Unavailable(
                "FFmpeg não encontrado. Instale o FFmpeg (veja docs/USAGE.md) ou defina VCS_FFMPEG_PATH no .env."
            )
        return self.ffmpeg

    def require_ffprobe(self) -> str:
        if not self.ffprobe:
            raise Unavailable(
                "ffprobe não encontrado. Ele acompanha o FFmpeg; instale-o ou defina VCS_FFPROBE_PATH no .env."
            )
        return self.ffprobe

    def version(self) -> str | None:
        if not self.ffmpeg:
            return None
        if "version" not in self._cache:
            try:
                proc = run_capture([self.ffmpeg, "-hide_banner", "-version"], timeout=15)
                self._cache["version"] = (proc.stdout.splitlines() or [None])[0]
            except (OSError, subprocess.TimeoutExpired):
                self._cache["version"] = None
        return self._cache["version"]

    def _listing(self, flag: str) -> set[str]:
        key = f"list:{flag}"
        if key not in self._cache:
            names: set[str] = set()
            if self.ffmpeg:
                try:
                    proc = run_capture([self.ffmpeg, "-hide_banner", flag], timeout=30)
                    names = parse_ffmpeg_list(proc.stdout)
                except (OSError, subprocess.TimeoutExpired):
                    names = set()
            self._cache[key] = names
        return self._cache[key]

    def encoders(self) -> set[str]:
        return self._listing("-encoders")

    def filters(self) -> set[str]:
        return self._listing("-filters")

    def test_encoder(self, name: str) -> tuple[bool, str]:
        """Encode ~0.5s of synthetic video to check that an encoder really works on this machine."""
        ffmpeg = self.require_ffmpeg()
        args = [
            ffmpeg, "-hide_banner", "-v", "error", "-f", "lavfi",
            "-i", "color=c=black:s=640x360:r=30:d=1", "-frames:v", "15",
            "-c:v", name, "-pix_fmt", "yuv420p", "-f", "null", "-",
        ]
        try:
            proc = run_capture(args, timeout=45)
        except subprocess.TimeoutExpired:
            return False, "Tempo esgotado ao testar o encoder."
        if proc.returncode == 0:
            return True, "ok"
        return False, (proc.stderr.strip() or "falhou sem mensagem")[-500:]

    # -- probing ------------------------------------------------------------------
    def probe(self, path: Path) -> MediaInfo:
        ffprobe = self.require_ffprobe()
        try:
            proc = run_capture(
                [ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", "-i", str(path)],
                timeout=60,
            )
        except subprocess.TimeoutExpired as exc:
            raise InvalidInput("Tempo esgotado ao ler o arquivo de vídeo.") from exc
        if proc.returncode != 0:
            detail = (proc.stderr.strip().splitlines() or ["erro desconhecido"])[-1]
            raise InvalidInput(f"Não foi possível ler o arquivo como vídeo: {detail}")
        data = loads(proc.stdout, {})
        try:
            size = path.stat().st_size
        except OSError:
            size = None
        return parse_probe(data, size)
