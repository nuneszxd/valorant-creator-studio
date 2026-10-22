"""Start and describe recording analyses."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from fastapi import APIRouter

from ..analysis.pipeline import LEVEL_INFO, resolve_plan, run_analysis
from ..errors import Conflict, InvalidInput
from ..media.transcribe import MODEL_INFO, transcription_available
from ..models import Strict
from .deps import Ctx

router = APIRouter(prefix="/api", tags=["análise"])


class AnalyzeBody(Strict):
    level: Literal["leve", "padrao", "detalhado", "completo"] = "padrao"
    scenes: bool | None = None
    transcription: Literal["off", "candidates", "full"] | None = None
    whisper_model: Literal["tiny", "base", "small", "medium"] | None = None
    allow_model_download: bool = False


@router.get("/analysis/levels")
def levels(c: Ctx) -> dict:
    settings = c.settings.load()
    ready, message = transcription_available(settings)
    return {
        "levels": LEVEL_INFO,
        "models": MODEL_INFO,
        "provider": settings.transcription_provider,
        "provider_ready": ready,
        "provider_message": message,
    }


@router.post("/recordings/{recording_id}/analyze", status_code=202)
def analyze(recording_id: int, body: AnalyzeBody, c: Ctx) -> dict:
    """Queue an analysis job. Nothing heavy runs until this is called."""
    c.tools.require_ffmpeg()
    c.tools.require_ffprobe()
    recording = c.repos.recordings.require(recording_id)
    if not Path(recording["path"]).is_file():
        raise InvalidInput("O arquivo desta gravação não foi encontrado no disco. Importe-o novamente.")
    if c.repos.jobs.count("kind = 'analyze' AND recording_id = ? AND state IN ('queued', 'running')", (recording_id,)):
        raise Conflict("Já existe uma análise em andamento ou na fila para esta gravação.")
    plan = resolve_plan(body.level, body.scenes, body.transcription, body.whisper_model)
    if plan.transcription != "off":
        ready, message = transcription_available(c.settings.load())
        if not ready:
            raise InvalidInput(f"Transcrição indisponível: {message} Use o nível 'Leve' para analisar só pelo áudio.")
    job = c.jobs.submit(
        "analyze",
        f"Analisar {recording['name']} ({LEVEL_INFO[plan.level]['label']})",
        lambda ctx: run_analysis(ctx, c, recording_id, plan, allow_download=body.allow_model_download),
        recording_id=recording_id,
        params=body.model_dump(),
    )
    return job
