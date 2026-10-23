"""Local speech-to-text.

* faster-whisper (default): runs on the CPU when the GPU is AMD (CTranslate2 has no AMD backend
  on Windows). Models are downloaded only after explicit consent.
* whisper.cpp (optional, experimental): runs a user-supplied `whisper-cli` binary, which can be a
  Vulkan build that uses AMD GPUs. Segment-level timestamps only; word times are interpolated.

Nothing here sends audio anywhere: everything runs locally.
"""

from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..errors import AppError, Unavailable
from ..models import AppSettings

log = logging.getLogger(__name__)

WHISPER_SAMPLE_RATE = 16000

MODEL_INFO = {
    "tiny": {"approx_download": "≈75 MB", "note": "mais rápido, menos preciso"},
    "base": {"approx_download": "≈145 MB", "note": "bom ponto de partida em CPU"},
    "small": {"approx_download": "≈480 MB", "note": "mais preciso, bem mais lento em CPU"},
    "medium": {"approx_download": "≈1,5 GB", "note": "muito lento em CPU; só se tiver paciência e memória"},
}


@dataclass
class Word:
    start: float
    end: float
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": round(self.start, 3), "end": round(self.end, 3), "text": self.text}


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: list[Word] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_s": round(self.start, 3),
            "end_s": round(self.end, 3),
            "text": self.text,
            "words": [w.to_dict() for w in self.words],
        }


class Transcriber(Protocol):
    name: str

    def transcribe_file(self, wav: Path, *, offset_s: float, ctx: Any) -> list[Segment]: ...


def interpolate_words(text: str, start: float, end: float) -> list[Word]:
    """Spread words evenly over a segment (used when the engine gives no word timestamps)."""
    tokens = text.split()
    if not tokens or end <= start:
        return []
    step = (end - start) / len(tokens)
    return [Word(start + i * step, start + (i + 1) * step, tok) for i, tok in enumerate(tokens)]


def load_wav_samples(wav: Path) -> Any:
    """Read the 16 kHz mono 16-bit WAV written by `extract_wav_window` as float32 samples in [-1, 1].

    faster-whisper decodes a file path with PyAV, and some PyAV/faster-whisper version pairs disagree
    on `av.open` arguments ("open() got an unexpected keyword argument 'metadata_errors'"). We
    control the WAV format, so the model gets the samples directly and PyAV is never involved.
    """
    import wave

    import numpy as np  # installed together with faster-whisper

    try:
        with wave.open(str(wav), "rb") as reader:
            channels, width, rate = reader.getnchannels(), reader.getsampwidth(), reader.getframerate()
            raw = reader.readframes(reader.getnframes())
    except (wave.Error, EOFError, OSError) as exc:
        raise AppError(f"O áudio extraído para a transcrição não pôde ser lido: {exc}") from exc
    if (channels, width, rate) != (1, 2, WHISPER_SAMPLE_RATE):
        raise AppError(
            f"O áudio extraído para a transcrição tem formato inesperado ({channels} canal(is), "
            f"{width * 8} bits, {rate} Hz); era esperado mono, 16 bits, {WHISPER_SAMPLE_RATE} Hz."
        )
    if not raw:
        return np.zeros(0, dtype=np.float32)
    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


class FasterWhisperTranscriber:
    name = "faster-whisper"

    def __init__(self, model: str, models_dir: Path, language: str, beam_size: int,
                 allow_download: bool) -> None:
        self.model_name = model
        self.models_dir = models_dir
        self.language = language
        self.beam_size = beam_size
        self.allow_download = allow_download
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is not None:
            return self._model
        if importlib.util.find_spec("faster_whisper") is None:
            raise Unavailable(
                'faster-whisper não está instalado. Rode: pip install -e "backend[transcribe]" '
                "(veja docs/USAGE.md)."
            )
        from faster_whisper import WhisperModel  # type: ignore[import-not-found]

        self.models_dir.mkdir(parents=True, exist_ok=True)
        try:
            self._model = WhisperModel(
                self.model_name, device="cpu", compute_type="int8",
                download_root=str(self.models_dir), local_files_only=not self.allow_download,
            )
        except Exception as exc:
            if not self.allow_download:
                info = MODEL_INFO.get(self.model_name, {})
                raise AppError(
                    f"O modelo de transcrição '{self.model_name}' ainda não foi baixado "
                    f"({info.get('approx_download', 'tamanho variável')}). Confirme o download na tela de "
                    "análise para baixar uma vez; depois ele roda 100% offline.",
                    code="model_not_downloaded",
                ) from exc
            raise AppError(f"Não foi possível carregar o modelo de transcrição: {exc}") from exc
        return self._model

    def transcribe_file(self, wav: Path, *, offset_s: float, ctx: Any) -> list[Segment]:
        model = self._load()
        audio = load_wav_samples(wav)
        if audio.size == 0:
            return []
        segments_iter, _info = model.transcribe(
            audio, language=self.language, word_timestamps=True, vad_filter=True,
            beam_size=self.beam_size, condition_on_previous_text=False,
        )
        out: list[Segment] = []
        for seg in segments_iter:
            ctx.check_cancelled()
            words = [
                Word(offset_s + w.start, offset_s + w.end, (w.word or "").strip())
                for w in (seg.words or [])
                if (w.word or "").strip()
            ]
            text = (seg.text or "").strip()
            if not text:
                continue
            out.append(Segment(offset_s + seg.start, offset_s + seg.end, text, words))
        return out


class WhisperCppTranscriber:
    """Experimental: shells out to a user-provided whisper.cpp CLI."""

    name = "whisper.cpp"

    def __init__(self, exe: str, model_path: str, language: str) -> None:
        self.exe = exe
        self.model_path = model_path
        self.language = language

    def transcribe_file(self, wav: Path, *, offset_s: float, ctx: Any) -> list[Segment]:
        prefix = wav.with_suffix("")
        result = ctx.run(
            [self.exe, "-m", self.model_path, "-f", str(wav), "-l", self.language, "-oj", "-of", str(prefix), "-np"],
            timeout=3600,
        )
        out_json = prefix.with_name(prefix.name + ".json")
        if result.returncode != 0 or not out_json.is_file():
            tail = " | ".join(result.stderr_tail.splitlines()[-3:])
            raise AppError(f"whisper.cpp falhou: {tail or 'sem detalhes'}", code="whisper_cpp_failed")
        try:
            data = json.loads(out_json.read_text(encoding="utf-8", errors="replace"))
        except ValueError as exc:
            raise AppError("whisper.cpp gerou uma saída que não pôde ser lida.") from exc
        segments: list[Segment] = []
        for item in data.get("transcription", []):
            offsets = item.get("offsets") or {}
            text = (item.get("text") or "").strip()
            if not text:
                continue
            start = offset_s + float(offsets.get("from", 0)) / 1000.0
            end = offset_s + float(offsets.get("to", 0)) / 1000.0
            segments.append(Segment(start, end, text, interpolate_words(text, start, end)))
        out_json.unlink(missing_ok=True)
        return segments


def transcription_available(settings: AppSettings) -> tuple[bool, str]:
    """Whether the configured provider can run, with a user-facing reason if not."""
    if settings.transcription_provider == "whisper.cpp":
        exe, model = settings.whisper_cpp_path, settings.whisper_cpp_model_path
        if not exe or not model:
            return False, "Configure o caminho do whisper-cli e do modelo .bin em Configurações."
        if not Path(exe).is_file() or not Path(model).is_file():
            return False, "O whisper-cli ou o modelo configurado não foi encontrado no disco."
        return True, "ok"
    if importlib.util.find_spec("faster_whisper") is None:
        return False, 'faster-whisper não instalado. Rode: pip install -e "backend[transcribe]".'
    return True, "ok"


def build_transcriber(settings: AppSettings, models_dir: Path, *, allow_download: bool,
                      model_override: str | None = None) -> Transcriber:
    if settings.transcription_provider == "whisper.cpp":
        return WhisperCppTranscriber(
            settings.whisper_cpp_path or "", settings.whisper_cpp_model_path or "", settings.whisper_language
        )
    return FasterWhisperTranscriber(
        model_override or settings.whisper_model, models_dir, settings.whisper_language,
        settings.whisper_beam_size, allow_download,
    )
