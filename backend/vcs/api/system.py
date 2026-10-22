"""System endpoints: health, capabilities, native file picker, shutdown."""

from __future__ import annotations

import importlib.util
import platform
import subprocess
import sys
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from .. import __version__
from ..analysis.moment_types import MOMENT_TYPES
from ..errors import Unavailable
from ..jobs.procs import run_capture
from ..models import ANALYSIS_LEVELS
from .deps import Ctx

router = APIRouter(prefix="/api", tags=["sistema"])

HARDWARE_ENCODERS = ("libx264", "h264_amf", "h264_nvenc", "h264_qsv")
USEFUL_FILTERS = ("ass", "boxblur", "loudnorm", "scale", "overlay", "select")


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "version": __version__}


@router.get("/system/capabilities")
def capabilities(c: Ctx) -> dict:
    """What this machine can do: FFmpeg features, transcription backends, configured integrations."""
    tools = c.tools
    encoders = tools.encoders()
    filters = tools.filters()
    settings = c.settings.load()
    return {
        "app_version": __version__,
        "platform": platform.platform(),
        "python": platform.python_version(),
        "ffmpeg": {
            "available": bool(tools.ffmpeg and tools.ffprobe),
            "ffmpeg_path": tools.ffmpeg,
            "ffprobe_path": tools.ffprobe,
            "version": tools.version(),
            "encoders": {name: name in encoders for name in HARDWARE_ENCODERS},
            "filters": {name: name in filters for name in USEFUL_FILTERS},
        },
        "transcription": {
            "faster_whisper_installed": importlib.util.find_spec("faster_whisper") is not None,
            "whisper_cpp_configured": bool(settings.whisper_cpp_path and settings.whisper_cpp_model_path),
            "provider": settings.transcription_provider,
            "note": (
                "faster-whisper não usa GPU AMD no Windows; a transcrição roda na CPU. "
                "Uma build do whisper.cpp com Vulkan pode usar GPU AMD (opcional, experimental)."
            ),
        },
        "integrations": c.config.integrations(),
        "paths": {
            "data_dir": str(c.config.data_dir),
            "output_dir": str(c.settings.effective_output_dir()),
        },
        "analysis_levels": list(ANALYSIS_LEVELS),
    }


@router.get("/system/moment-types")
def moment_types() -> dict:
    return {"types": [{"key": key, "label": label} for key, label in MOMENT_TYPES.items()]}


class EncoderTest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    encoder: Literal["libx264", "h264_amf", "h264_nvenc", "h264_qsv"]


@router.post("/system/test-encoder")
def test_encoder(body: EncoderTest, c: Ctx) -> dict:
    """Encode half a second of synthetic video to check the encoder really works here."""
    ok, detail = c.tools.test_encoder(body.encoder)
    return {"encoder": body.encoder, "ok": ok, "detail": detail}


class PickRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["video", "folder"] = "video"


@router.post("/system/pick-file")
def pick_file(body: PickRequest) -> dict:
    """Open the native file/folder dialog on this machine and return the chosen path."""
    try:
        proc = run_capture([sys.executable, "-m", "vcs.tools.pick_file", "--kind", body.kind], timeout=600)
    except subprocess.TimeoutExpired as exc:
        raise Unavailable("Tempo esgotado aguardando a seleção do arquivo.") from exc
    if proc.returncode == 3:
        raise Unavailable(
            "O seletor de arquivos não está disponível neste Python (tkinter ausente). Digite o caminho manualmente."
        )
    if proc.returncode != 0:
        raise Unavailable("Não foi possível abrir o seletor de arquivos. Digite o caminho manualmente.")
    chosen = proc.stdout.strip()
    return {"path": chosen or None}


@router.post("/system/shutdown")
def shutdown(request: Request) -> dict:
    server = getattr(request.app.state, "server", None)
    if server is None:
        raise Unavailable("O encerramento remoto só funciona quando iniciado por 'vcs serve'.")
    server.should_exit = True
    return {"status": "encerrando"}
