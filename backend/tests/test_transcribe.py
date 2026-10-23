"""The transcriber hands faster-whisper decoded samples, so PyAV (`av.open`) is never asked to read the WAV."""

from __future__ import annotations

import math
import subprocess
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from vcs.errors import AppError  # noqa: E402
from vcs.media.transcribe import FasterWhisperTranscriber, load_wav_samples  # noqa: E402


def write_wav(path: Path, *, seconds: float = 1.0, rate: int = 16000, channels: int = 1, amplitude: int = 16384) -> Path:
    frames = b"".join(
        int(amplitude * math.sin(2 * math.pi * 440 * i / rate)).to_bytes(2, "little", signed=True) * channels
        for i in range(int(seconds * rate))
    )
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(channels)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(frames)
    return path


class FakeModel:
    """Stands in for WhisperModel: records what `transcribe` receives."""

    def __init__(self, segments):
        self.segments = segments
        self.received = None

    def transcribe(self, audio, **kwargs):
        self.received = (audio, kwargs)
        return iter(self.segments), SimpleNamespace()


class Ctx:
    def check_cancelled(self):
        return None


def make_transcriber(model):
    transcriber = FasterWhisperTranscriber("tiny", Path("."), "pt", 1, allow_download=False)
    transcriber._model = model
    return transcriber


def test_load_wav_samples_returns_float32_in_range(tmp_path):
    samples = load_wav_samples(write_wav(tmp_path / "a.wav", seconds=0.5))
    assert samples.dtype == np.float32 and samples.shape == (8000,)
    assert 0.45 < float(np.max(samples)) <= 0.5
    assert float(np.min(samples)) >= -0.5


@pytest.mark.parametrize("kwargs", [{"rate": 44100}, {"channels": 2}])
def test_load_wav_samples_refuses_an_unexpected_format(tmp_path, kwargs):
    with pytest.raises(AppError, match="formato inesperado"):
        load_wav_samples(write_wav(tmp_path / "a.wav", seconds=0.1, **kwargs))


def test_load_wav_samples_refuses_a_file_that_is_not_a_wav(tmp_path):
    bad = tmp_path / "a.wav"
    bad.write_bytes(b"not a wav file at all")
    with pytest.raises(AppError, match="não pôde ser lido"):
        load_wav_samples(bad)


def test_transcriber_passes_samples_not_a_path_and_applies_the_offset(tmp_path):
    word = SimpleNamespace(start=0.2, end=0.5, word=" fez ")
    blank = SimpleNamespace(start=0.5, end=0.6, word="   ")
    model = FakeModel([
        SimpleNamespace(start=0.1, end=0.9, text=" ace no site ", words=[word, blank]),
        SimpleNamespace(start=1.0, end=1.5, text="   ", words=[]),
    ])
    out = make_transcriber(model).transcribe_file(write_wav(tmp_path / "w.wav"), offset_s=100.0, ctx=Ctx())

    audio, kwargs = model.received
    assert isinstance(audio, np.ndarray) and audio.dtype == np.float32 and audio.size == 16000
    assert kwargs["language"] == "pt" and kwargs["word_timestamps"] is True
    assert len(out) == 1
    assert out[0].text == "ace no site"
    assert (out[0].start, out[0].end) == (pytest.approx(100.1), pytest.approx(100.9))
    assert [w.text for w in out[0].words] == ["fez"]
    assert (out[0].words[0].start, out[0].words[0].end) == (pytest.approx(100.2), pytest.approx(100.5))


def test_transcriber_skips_the_model_for_an_empty_audio_window(tmp_path):
    model = FakeModel([])
    assert make_transcriber(model).transcribe_file(write_wav(tmp_path / "w.wav", seconds=0), offset_s=0, ctx=Ctx()) == []
    assert model.received is None


@pytest.mark.requires_ffmpeg
def test_wav_written_by_ffmpeg_is_readable(tmp_path):
    """FFmpeg may add a LIST chunk to the header; `wave` has to skip it."""
    out = tmp_path / "ffmpeg.wav"
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
         "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(out)],
        check=True, capture_output=True, timeout=60,
    )
    samples = load_wav_samples(out)
    assert samples.shape[0] == pytest.approx(32000, abs=64)
    assert float(np.max(np.abs(samples))) > 0.1
