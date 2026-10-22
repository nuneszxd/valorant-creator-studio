"""Pure-function tests for signal processing, scoring and parsing (no ffmpeg, no I/O)."""

from __future__ import annotations

import pytest

from vcs.analysis.candidates import (
    CandidateDraft,
    Prefs,
    ScoringContext,
    classify_moment,
    duration_fit,
    feedback_adjustments,
    plan_windows,
    score_window,
    snap_boundaries,
    suppress_overlaps,
    words_in_range,
)
from vcs.analysis.moment_types import count_keyword_hits, default_keywords, default_reaction_keywords, normalize_text
from vcs.analysis.pipeline import chunk_ranges, merge_ranges, resolve_plan
from vcs.analysis.signals import build_audio_profile, find_peaks, moving_average, percentile
from vcs.errors import InvalidInput
from vcs.media.extract import parse_astats_metadata, parse_scene_metadata
from vcs.models import AnalysisSettings, ScoringWeights


def synthetic_rms(n=120, base=-40.0, burst=(60, 64), burst_db=-12.0):
    return [burst_db if burst[0] <= i < burst[1] else base + (i % 3) * 0.5 for i in range(n)]


def scoring_ctx(**kwargs):
    return ScoringContext(
        weights=ScoringWeights().model_dump(), keywords=default_keywords(),
        reaction_keywords=default_reaction_keywords(), **kwargs,
    )


def test_percentile_and_moving_average():
    data = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert percentile(data, 50) == 3.0
    assert percentile(data, 0) == 1.0 and percentile(data, 100) == 5.0
    assert percentile([], 50) == 0.0
    assert moving_average([0, 0, 9, 0, 0], 3) == [0, 3, 3, 3, 0]
    assert moving_average([1, 2], 1) == [1, 2]


def test_find_peaks_respects_distance_and_threshold():
    values = [0, 0.2, 0.9, 0.2, 0.7, 0.1, 0, 0.8, 0.1]
    assert find_peaks(values, 0.5, 1) == [2, 4, 7]
    assert find_peaks(values, 0.5, 3) == [2, 7]
    assert find_peaks(values, 0.95, 1) == []


def test_audio_profile_flags_only_the_burst():
    audio = build_audio_profile(synthetic_rms(), 0.5)
    peaks = find_peaks(audio.intensity, 0.55, 20)
    assert peaks, "the loud burst must be found"
    assert all(abs(audio.time_of(i) - 31) < 3 for i in peaks)
    assert max(audio.intensity[:50]) < 0.5  # quiet baseline stays low
    assert max(audio.burst) > 0.5  # sudden rise detected


def test_plan_windows_surrounds_the_peak():
    audio = build_audio_profile(synthetic_rms(), 0.5)
    windows = plan_windows(audio, 60.0, AnalysisSettings(), limit=10)
    assert len(windows) == 1
    w = windows[0]
    assert w.start <= w.peak <= w.end
    assert w.end - w.start >= 8


def test_flat_audio_produces_no_windows():
    audio = build_audio_profile([-40.0] * 200, 0.5)
    assert plan_windows(audio, 100.0, AnalysisSettings(), limit=10) == []


def test_score_without_transcript_is_explained_and_generic():
    audio = build_audio_profile(synthetic_rms(), 0.5)
    window = plan_windows(audio, 60.0, AnalysisSettings(), limit=5)[0]
    draft = score_window(window, audio, None, None, scoring_ctx())
    assert draft.moment_type == "pico_audio"
    assert 0 < draft.score <= 100
    keys = {r["key"]: r for r in draft.reasons}
    assert keys["audio_intensity"]["value"] == pytest.approx(1.0, abs=0.01)
    assert keys["speech"]["value"] is None and "sem transcrição" in keys["speech"]["detail"]
    assert keys["scene_activity"]["value"] is None
    assert draft.confidence in ("baixa", "média", "alta")
    # contributions of available features add up to the score (no feedback adjustment here)
    assert sum(r["points"] for r in draft.reasons) == pytest.approx(draft.score, abs=0.6)


def test_score_with_transcript_classifies_clutch_and_boosts_reaction():
    audio = build_audio_profile(synthetic_rms(), 0.5)
    window = plan_windows(audio, 60.0, AnalysisSettings(), limit=5)[0]
    segments = [
        {"start_s": window.start, "end_s": window.peak - 1, "text": "ok sobrou só eu aqui calma calma",
         "words": []},
        {"start_s": window.peak - 1, "end_s": window.end, "text": "meu deus é um clutch um contra três caramba",
         "words": []},
    ]
    plain = score_window(window, audio, None, None, scoring_ctx())
    rich = score_window(window, audio, [window.peak], segments, scoring_ctx())
    assert rich.moment_type == "clutch"
    assert "Clutch" in rich.title
    assert {r["key"]: r for r in rich.reasons}["reaction"]["value"] > 0.5
    assert rich.excerpt
    assert rich.confidence in ("média", "alta")
    assert plain.moment_type == "pico_audio"


def test_creator_preference_and_feedback_adjust_score():
    audio = build_audio_profile(synthetic_rms(), 0.5)
    window = plan_windows(audio, 60.0, AnalysisSettings(), limit=5)[0]
    segments = [{"start_s": window.start, "end_s": window.end, "text": "um clutch um contra três", "words": []}]
    base = score_window(window, audio, None, segments, scoring_ctx())
    liked = score_window(window, audio, None, segments, scoring_ctx(prefs=Prefs(preferred_types=["clutch"])))
    penalized = score_window(window, audio, None, segments, scoring_ctx(feedback={"clutch": -8.0}))
    assert liked.score > base.score
    assert penalized.score < base.score
    assert any(r["key"] == "feedback" for r in penalized.reasons)


def test_classify_moment_priority_and_fallbacks():
    assert classify_moment({"clutch": 2}, 0, False) == "clutch"
    assert classify_moment({"clutch": 1, "ace_multikill": 1}, 0, False) == "ace_multikill"
    assert classify_moment({}, 2, False) == "reacao"
    assert classify_moment({}, 0, True) == "reacao"
    assert classify_moment({}, 0, False) == "jogada"


def test_keyword_matching_is_accent_and_boundary_aware():
    norm = normalize_text("Não acredito! Foi um CLUTCH, 1v3 no Ascent")
    assert count_keyword_hits(norm, ["nao acredito"]) == 1
    assert count_keyword_hits(norm, ["clutch", "1v3"]) == 2
    assert count_keyword_hits(normalize_text("a face da jogada"), ["ace"]) == 0


def test_words_in_range_with_and_without_word_times():
    segs = [
        {"start_s": 0, "end_s": 10, "text": "a b c d e f g h i j", "words": []},
        {"start_s": 10, "end_s": 12, "text": "x y",
         "words": [{"start": 10.0, "end": 10.5, "text": "x"}, {"start": 11.0, "end": 11.5, "text": "y"}]},
    ]
    assert words_in_range(segs, 0, 5) == pytest.approx(5.0)
    assert words_in_range(segs, 10, 11) == 1  # only "x" starts inside [10, 11)
    assert words_in_range(segs, 20, 30) == 0


def test_snap_boundaries_only_within_tolerance():
    segs = [{"start_s": 8.0, "end_s": 14.0, "text": "x", "words": []}]
    assert snap_boundaries(10.0, 30.0, segs) == (8.0, 30.0)
    assert snap_boundaries(10.0, 30.0, segs, tolerance=1.0) == (10.0, 30.0)


def test_duration_fit():
    prefs = Prefs(min_s=20, max_s=45)
    assert duration_fit(30, prefs) == 1.0
    assert duration_fit(10, prefs) == pytest.approx(0.5)
    assert duration_fit(90, prefs) == pytest.approx(0.0)


def make_draft(start, end, score):
    return CandidateDraft(start, end, (start + end) / 2, "t", "pico_audio", score, "baixa", [], "")


def test_suppress_overlaps_keeps_best():
    drafts = [make_draft(0, 30, 50), make_draft(5, 35, 80), make_draft(100, 130, 40)]
    kept = suppress_overlaps(drafts)
    assert [d.score for d in kept] == [80, 40]


def test_feedback_adjustments_are_bounded_and_signed():
    rows = [{"moment_type": "clutch", "status": "approved", "outcome": "good"}] * 3 + [
        {"moment_type": "clutch", "status": "rejected", "outcome": None},
        {"moment_type": "tilt", "status": "rejected", "outcome": "bad"},
    ]
    adj = feedback_adjustments(rows)
    assert 0 < adj["clutch"] <= 10
    assert -10 <= adj["tilt"] < 0
    assert feedback_adjustments([]) == {}


def test_ranges_helpers_and_plan_resolution():
    assert merge_ranges([(0, 5), (4, 9), (20, 25)]) == [(0, 9), (20, 25)]
    assert chunk_ranges(650, 300) == [(0.0, 300.0), (300.0, 600.0), (600.0, 650)]
    plan = resolve_plan("padrao", None, None, None)
    assert (plan.scenes, plan.transcription, plan.model) == (False, "candidates", "base")
    assert resolve_plan("leve", True, None, None).scenes is True
    with pytest.raises(InvalidInput):
        resolve_plan("inexistente", None, None, None)
    with pytest.raises(InvalidInput):
        resolve_plan("leve", None, "tudo", None)


ASTATS_SAMPLE = """frame:0    pts:0       pts_time:0
lavfi.astats.Overall.RMS_level=-35.250
frame:1    pts:8000    pts_time:0.5
lavfi.astats.Overall.RMS_level=-inf
frame:2    pts:16000   pts_time:1
lavfi.astats.Overall.RMS_level=-12.500
frame:4    pts:32000   pts_time:2
lavfi.astats.Overall.RMS_level=-20.000
"""


def test_parse_astats_metadata():
    values = parse_astats_metadata(ASTATS_SAMPLE, 0.5)
    assert values[0] == -35.25
    assert values[1] == -90.0  # -inf becomes the silence floor
    assert values[2] == -12.5
    assert values[3] == -90.0  # missing frame filled with silence
    assert values[4] == -20.0
    assert parse_astats_metadata("", 0.5) == []
    assert len(parse_astats_metadata(ASTATS_SAMPLE, 0.5, expected=10)) == 10


def test_parse_scene_metadata():
    sample = "frame:0 pts:10 pts_time:12.5\nlavfi.scene_score=0.512\nframe:1 pts:20 pts_time:13\nlavfi.scene_score=0.01\n"
    assert parse_scene_metadata(sample) == [(12.5, 0.512), (13.0, 0.01)]
