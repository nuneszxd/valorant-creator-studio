"""Subtitle (ASS) generation and FFmpeg command construction - pure, no ffmpeg needed."""

from __future__ import annotations

from pathlib import Path

from vcs.media.render import audio_graph, build_plan, encoder_args, video_graph
from vcs.media.subtitles import (
    ass_color,
    ass_time,
    build_ass,
    chunk_words,
    cues_from_segments,
    inline_color,
    words_for_cue,
)
from vcs.models import CropRegion, RenderConfig, SubtitleStyle


def test_ass_helpers():
    assert ass_color("#FFD400") == "&H0000D4FF"
    assert inline_color("#FFD400") == "&H00D4FF&"
    assert ass_time(3661.456) == "1:01:01.46"
    assert ass_time(-1) == "0:00:00.00"


def test_cues_from_segments_shifts_and_clips_to_clip_range():
    segments = [
        {"start_s": 100.0, "end_s": 104.0, "text": "oi mundo",
         "words": [{"start": 100.0, "end": 101.0, "text": "oi"}, {"start": 102.0, "end": 103.0, "text": "mundo"}]},
        {"start_s": 200.0, "end_s": 205.0, "text": "fora", "words": []},
    ]
    cues = cues_from_segments(segments, 101.0, 110.0)
    assert len(cues) == 1
    cue = cues[0]
    assert cue["text"] == "mundo"
    assert cue["start"] == 1.0 and cue["end"] == 2.0


def test_words_for_cue_uses_timings_or_spreads_edited_text():
    cue = {"start": 0.0, "end": 2.0, "text": "olha esse clutch",
           "words": [{"start": 0.0, "end": 0.5, "text": "olha"}, {"start": 0.5, "end": 1.0, "text": "esse"},
                     {"start": 1.0, "end": 2.0, "text": "clutch"}]}
    assert words_for_cue(cue)[2]["start"] == 1.0
    edited = dict(cue, text="olha esse CLUTCH insano")
    spread = words_for_cue(edited)
    assert len(spread) == 4 and spread[0]["start"] == 0.0 and spread[-1]["end"] == 2.0


def test_chunk_words_limits_words_and_chars():
    words = [{"start": i, "end": i + 1, "text": t} for i, t in enumerate(["um", "dois", "três", "quatro", "cinco"])]
    chunks = chunk_words(words, max_words=2, max_chars=50)
    assert [len(c) for c in chunks] == [2, 2, 1]
    assert [len(c) for c in chunk_words(words, max_words=10, max_chars=8)] == [2, 1, 1, 1] or len(chunk_words(words, 10, 8)) > 1


def test_build_ass_highlights_current_word_and_sanitizes():
    cues = [{"start": 0.0, "end": 1.5, "text": "olha {isso} \\n aqui", "words": []}]
    style = SubtitleStyle(font="Arial", highlight_words=True, max_words_per_line=3)
    ass = build_ass(cues, style, 1080, 1920)
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    assert "Style: Default,Arial,86," in ass  # 4.5% of 1920
    dialogue = [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]
    assert len(dialogue) >= 3
    assert any("{\\c&H00D4FF&}" in ln for ln in dialogue)
    body = "\n".join(dialogue)
    assert "{isso}" not in body and "\\n" not in body.replace("{\\c", "").replace("{\\r}", "")


def test_build_ass_without_highlight_uses_single_event_per_chunk():
    cues = [{"start": 0.0, "end": 2.0, "text": "uma frase curta", "words": []}]
    style = SubtitleStyle(highlight_words=False, uppercase=True)
    ass = build_ass(cues, style, 720, 1280)
    dialogue = [ln for ln in ass.splitlines() if ln.startswith("Dialogue:")]
    assert len(dialogue) == 1 and "UMA FRASE CURTA" in dialogue[0]


def test_video_graph_layouts():
    blur = video_graph(RenderConfig(), 1920, 1080, 1080, 1920)
    assert "split=2" in blur and "boxblur" in blur and "overlay=(W-w)/2:(H-h)/2" in blur and blur.endswith("[vbase]")
    solid = video_graph(RenderConfig(layout="solid", background_color="#112233"), 1920, 1080, 1080, 1920)
    assert "pad=1080:1920" in solid and "0x112233" in solid and "boxblur" not in solid
    fill = video_graph(RenderConfig(layout="fill", focus_x=0.25), 1920, 1080, 1080, 1920)
    assert "force_original_aspect_ratio=increase" in fill and "0.2500" in fill


def test_video_graph_crop_and_fps_are_even_and_inside_frame():
    cfg = RenderConfig(crop=CropRegion(x=0.1, y=0.0, w=0.5, h=1.0), fps=30)
    graph = video_graph(cfg, 1920, 1080, 1080, 1920)
    assert graph.startswith("[0:v:0]fps=30,crop=960:1080:192:0,")


def test_audio_graph_options():
    plain = audio_graph(RenderConfig(fade_s=0), 0, 20)
    assert plain == "[0:a:0]anull[aout]"
    full = audio_graph(RenderConfig(volume_db=3, loudnorm=True, fade_s=0.5), 1, 20)
    assert full.startswith("[0:a:1]anull,volume=3.0dB,loudnorm=") and "aresample=48000" in full
    assert "afade=t=in" in full and "afade=t=out:st=19.500" in full


def test_encoder_args():
    assert encoder_args(RenderConfig(), preview=False)[:2] == ["-c:v", "libx264"]
    amf = encoder_args(RenderConfig(encoder="h264_amf", bitrate_kbps=8000), preview=False)
    assert "h264_amf" in amf and "8000k" in amf and "vbr_peak" in amf
    assert "ultrafast" in encoder_args(RenderConfig(encoder="h264_amf"), preview=True)


def _plan(**overrides):
    kwargs = dict(
        ffmpeg="ffmpeg", src=Path("/videos/live.mp4"), start_s=10.0, end_s=40.0, cfg=RenderConfig(),
        style=SubtitleStyle(), cues=[{"start": 0.0, "end": 2.0, "text": "oi", "words": []}], src_w=1920,
        src_h=1080, has_audio=True, audio_stream_index=0, out_path=Path("/out/x.mp4.part"), preview=False,
        ass_filter_available=True,
    )
    kwargs.update(overrides)
    return build_plan(**kwargs)


def test_build_plan_command_structure():
    plan = _plan()
    args = plan.args
    assert args[0] == "ffmpeg" and "-nostdin" in args and "-filter_complex" in args
    assert args[args.index("-ss") + 1] == "10.000" and args[args.index("-t") + 1] == "30.000"
    assert args[args.index("-i") + 1] == str(Path("/videos/live.mp4"))
    assert args[-3:-1] == ["-f", "mp4"] and args[-1] == str(Path("/out/x.mp4.part"))
    assert "[vout]" in args and "[aout]" in args
    assert "ass=filename=subs.ass[vout]" in plan.graph and plan.ass_text
    assert (plan.out_w, plan.out_h) == (1080, 1920)


def test_build_plan_preview_without_audio_or_ass_filter():
    plan = _plan(preview=True, has_audio=False, ass_filter_available=False)
    assert (plan.out_w, plan.out_h) == (540, 960)
    assert "-an" in plan.args and "[aout]" not in plan.args
    assert plan.ass_text is None and plan.notes and "ass" in plan.notes[0]
    assert ";[vbase]null[vout]" in plan.graph
