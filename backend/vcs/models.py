"""Pydantic models shared across the API: app settings, render/subtitle config, creator profile."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .analysis.moment_types import MOMENT_TYPES, default_keywords, default_reaction_keywords

HEX_COLOR = r"^#[0-9A-Fa-f]{6}$"
X264_PRESETS = Literal["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower"]
ENCODERS = Literal["libx264", "h264_amf", "h264_nvenc", "h264_qsv"]
LAYOUTS = Literal["blur", "solid", "fill"]
ANALYSIS_LEVELS = ("leve", "padrao", "detalhado", "completo")


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CropRegion(Strict):
    """Normalized region (0..1) of the source frame to keep before fitting to 9:16."""

    x: float = Field(0, ge=0, le=1)
    y: float = Field(0, ge=0, le=1)
    w: float = Field(1, gt=0.04, le=1)
    h: float = Field(1, gt=0.04, le=1)

    @model_validator(mode="after")
    def _inside_frame(self) -> "CropRegion":
        if self.x + self.w > 1.0001 or self.y + self.h > 1.0001:
            raise ValueError("A região de recorte precisa estar dentro do quadro.")
        return self


class RenderConfig(Strict):
    width: int = Field(1080, ge=360, le=2160)
    height: int = Field(1920, ge=640, le=3840)
    layout: LAYOUTS = "blur"
    background_color: str = Field("#101010", pattern=HEX_COLOR)
    focus_x: float = Field(0.5, ge=0, le=1)
    crop: CropRegion | None = None
    encoder: ENCODERS = "libx264"
    preset: X264_PRESETS = "fast"
    crf: int = Field(20, ge=12, le=35)
    bitrate_kbps: int = Field(10000, ge=1000, le=50000)
    fps: int | None = Field(None, ge=15, le=120)
    audio_bitrate_kbps: int = Field(160, ge=64, le=320)
    volume_db: float = Field(0, ge=-30, le=20)
    loudnorm: bool = False
    fade_s: float = Field(0.25, ge=0, le=3)
    subtitles: bool = True

    @model_validator(mode="after")
    def _even_dimensions(self) -> "RenderConfig":
        if self.width % 2 or self.height % 2:
            raise ValueError("Largura e altura precisam ser números pares.")
        return self


class SubtitleStyle(Strict):
    font: str = Field("Arial", pattern=r"^[A-Za-z0-9 ._\-]{1,60}$")
    size_pct: float = Field(4.5, ge=2, le=10)
    text_color: str = Field("#FFFFFF", pattern=HEX_COLOR)
    highlight_color: str = Field("#FFD400", pattern=HEX_COLOR)
    outline_color: str = Field("#000000", pattern=HEX_COLOR)
    outline_px: float = Field(4, ge=0, le=12)
    bold: bool = True
    uppercase: bool = False
    position_pct: float = Field(22, ge=2, le=90)
    max_words_per_line: int = Field(4, ge=1, le=8)
    max_chars_per_line: int = Field(26, ge=10, le=48)
    highlight_words: bool = True


class AnalysisSettings(Strict):
    max_candidates: int = Field(25, ge=1, le=200)
    min_intensity: float = Field(0.55, ge=0.1, le=1.0)
    pre_roll_s: float = Field(18, ge=2, le=120)
    post_roll_s: float = Field(10, ge=2, le=120)
    min_separation_s: float = Field(25, ge=5, le=600)
    scene_threshold: float = Field(0.35, ge=0.05, le=0.95)
    audio_window_s: float = Field(0.5, ge=0.25, le=2.0)
    audio_stream_index: int = Field(0, ge=0, le=16)


class ScoringWeights(Strict):
    audio_intensity: float = Field(0.22, ge=0, le=1)
    audio_burst: float = Field(0.14, ge=0, le=1)
    tension: float = Field(0.08, ge=0, le=1)
    speech: float = Field(0.12, ge=0, le=1)
    reaction: float = Field(0.18, ge=0, le=1)
    scene_activity: float = Field(0.06, ge=0, le=1)
    context: float = Field(0.08, ge=0, le=1)
    story: float = Field(0.04, ge=0, le=1)
    duration_fit: float = Field(0.06, ge=0, le=1)
    creator_pref: float = Field(0.08, ge=0, le=1)


class AppSettings(Strict):
    output_dir: str | None = None
    transcription_provider: Literal["faster-whisper", "whisper.cpp"] = "faster-whisper"
    whisper_model: Literal["tiny", "base", "small", "medium"] = "base"
    whisper_language: str = Field("pt", pattern=r"^[a-z]{2,3}$")
    whisper_beam_size: int = Field(1, ge=1, le=5)
    whisper_cpp_path: str | None = None
    whisper_cpp_model_path: str | None = None
    analysis: AnalysisSettings = Field(default_factory=AnalysisSettings)
    scoring_weights: ScoringWeights = Field(default_factory=ScoringWeights)
    keywords: dict[str, list[str]] = Field(default_factory=default_keywords)
    reaction_keywords: list[str] = Field(default_factory=default_reaction_keywords)
    render: RenderConfig = Field(default_factory=RenderConfig)
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    base_hashtags: list[str] = Field(default_factory=lambda: ["valorant", "valorantbr", "valorantclips"])
    # Default YouTube quota: 100 search.list calls per day (separate bucket from the 10,000 units).
    youtube_search_daily_limit: int = Field(100, ge=1, le=10000)

    @field_validator("keywords")
    @classmethod
    def _keywords_valid(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for key, words in value.items():
            if key not in MOMENT_TYPES:
                raise ValueError(f"Tipo de momento desconhecido: {key}")
            if len(words) > 100 or any(len(w) > 40 for w in words):
                raise ValueError("Listas de palavras-chave: no máximo 100 itens de até 40 caracteres.")
        return value

    @field_validator("reaction_keywords")
    @classmethod
    def _reaction_valid(cls, value: list[str]) -> list[str]:
        if len(value) > 100 or any(len(w) > 40 for w in value):
            raise ValueError("Palavras de reação: no máximo 100 itens de até 40 caracteres.")
        return value

    @field_validator("base_hashtags")
    @classmethod
    def _hashtags_valid(cls, value: list[str]) -> list[str]:
        cleaned = [v.strip().lstrip("#") for v in value if v.strip()]
        for tag in cleaned:
            if not tag.isalnum():
                raise ValueError(f"Hashtag inválida (use letras e números): {tag}")
        return cleaned[:20]


class SocialLinks(Strict):
    twitch: str = Field("", max_length=300)
    tiktok: str = Field("", max_length=300)
    youtube: str = Field("", max_length=300)
    instagram: str = Field("", max_length=300)
    other: list[str] = Field(default_factory=list, max_length=10)


class CreatorProfile(Strict):
    channel_name: str = Field("", max_length=120)
    links: SocialLinks = Field(default_factory=SocialLinks)
    rank_current: str = Field("", max_length=40)
    rank_target: str = Field("", max_length=40)
    agents: list[str] = Field(default_factory=list, max_length=20)
    content_style: list[str] = Field(default_factory=list, max_length=20)
    publishing_frequency_per_week: float | None = Field(None, ge=0, le=100)
    target_audience: str = Field("", max_length=300)
    formats_to_try: list[str] = Field(default_factory=list, max_length=20)
    preferred_types: list[str] = Field(default_factory=list)
    editing_preferences: str = Field("", max_length=600)
    preferred_duration_min_s: int = Field(20, ge=5, le=180)
    preferred_duration_max_s: int = Field(45, ge=5, le=180)
    series_name: str = Field("", max_length=120)
    past_results_notes: str = Field("", max_length=2000)

    @field_validator("preferred_types")
    @classmethod
    def _types_valid(cls, value: list[str]) -> list[str]:
        for item in value:
            if item not in MOMENT_TYPES:
                raise ValueError(f"Tipo de momento desconhecido: {item}")
        return value

    @model_validator(mode="after")
    def _duration_order(self) -> "CreatorProfile":
        if self.preferred_duration_min_s > self.preferred_duration_max_s:
            raise ValueError("A duração mínima não pode ser maior que a máxima.")
        return self
