from __future__ import annotations

import pytest

from vcs.errors import InvalidInput
from vcs.media.ffmpeg import FFmpegTools, parse_ffmpeg_list, parse_fps, parse_probe

from .helpers import make_test_video

ENCODERS_SAMPLE = """Encoders:
 V..... = Video
 A..... = Audio
 ------
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
 V....D h264_amf             AMD AMF H.264 Encoder (codec h264)
 A....D aac                  AAC (Advanced Audio Coding)
"""

# `ffmpeg -filters` has NO separator line (unlike `-encoders`). Lines below are taken from real FFmpeg 8.0.1
# (gyan.dev essentials build, Windows) output pasted from the user's PC, plus the older 3-flag style.
FILTERS_SAMPLE = """Filters:
  T.. = Timeline support
  .S. = Slice threading
  ..C = Command support
  A = Audio input/output
  V = Video input/output
  N = Dynamic number and/or type of input/output
  | = Source or sink filter
 TS allpass           A->A       Apply a two-pole all-pass filter.
 .. anull             A->A       Pass the source unchanged to the output.
 .. ass               V->V       Render ASS subtitles onto input video using the libass library.
 T. virtualbass       A->A       Audio Virtual Bass.
 .. sinc              |->A       Generate a sinc kaiser-windowed low-pass, high-pass, band-pass, or band-reject FIR coefficients.
 .. select            V->N       Select video frames to pass in output.
 ... boxblur          V->V       Blur the input.
 T.C loudnorm         A->A       EBU R128 loudness normalization
 TSC overlay          VV->V      Overlay a video source on top of the input.
 .S. amix             N->A       Audio mixing.
"""

REAL_ENCODERS_FFMPEG8 = """Encoders:
 V..... = Video
 A..... = Audio
 S..... = Subtitle
 .F.... = Frame-level multithreading
 ..S... = Slice-level multithreading
 ...X.. = Codec is experimental
 ....B. = Supports draw_horiz_band
 .....D = Supports direct rendering method 1
 ------
 V....D libx264              libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 (codec h264)
 V....D libx264rgb           libx264 H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10 RGB (codec h264)
 V....D h264_amf             AMD AMF H.264 Encoder (codec h264)
"""


def test_parse_ffmpeg_list():
    assert {"libx264", "h264_amf", "aac"} <= parse_ffmpeg_list(ENCODERS_SAMPLE)
    assert {"ass", "boxblur", "loudnorm"} <= parse_ffmpeg_list(FILTERS_SAMPLE)
    assert parse_ffmpeg_list("") == set()


def test_parse_ffmpeg_list_real_ffmpeg8_output_has_no_separator_for_filters():
    filters = parse_ffmpeg_list(FILTERS_SAMPLE)
    assert {"allpass", "anull", "ass", "virtualbass", "sinc", "select", "overlay", "amix"} <= filters
    assert "=" not in filters and "Timeline" not in filters  # legend lines are not filters
    encoders = parse_ffmpeg_list(REAL_ENCODERS_FFMPEG8)
    assert encoders == {"libx264", "libx264rgb", "h264_amf"}  # legend lines ("V..... = Video") are skipped
    assert parse_ffmpeg_list("Filters:\n  T.. = Timeline support\n  | = Source or sink filter\n") == set()


def test_parse_fps():
    assert parse_fps("60/1") == 60.0
    assert parse_fps("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert parse_fps("0/0") is None
    assert parse_fps(None) is None
    assert parse_fps("abc") is None


def test_parse_probe():
    data = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
             "avg_frame_rate": "60/1", "disposition": {"attached_pic": 0}},
            {"codec_type": "audio", "codec_name": "aac"},
            {"codec_type": "audio", "codec_name": "aac"},
        ],
        "format": {"duration": "123.45", "size": "1000", "format_name": "mov,mp4", "bit_rate": "5000"},
    }
    info = parse_probe(data)
    assert (info.width, info.height, info.fps, info.audio_streams) == (1920, 1080, 60.0, 2)
    assert info.duration_s == pytest.approx(123.45)
    assert info.video_codec == "h264" and info.audio_codec == "aac"


def test_parse_probe_without_video_is_rejected():
    with pytest.raises(InvalidInput):
        parse_probe({"streams": [{"codec_type": "audio"}], "format": {}})
    cover_only = {"streams": [{"codec_type": "video", "disposition": {"attached_pic": 1}}], "format": {}}
    with pytest.raises(InvalidInput):
        parse_probe(cover_only)


def test_discover_with_missing_configured_paths():
    tools = FFmpegTools.discover("/definitely/not/here/ffmpeg", "/definitely/not/here/ffprobe")
    assert tools.ffmpeg is None and tools.ffprobe is None
    assert tools.encoders() == set()
    assert tools.version() is None


@pytest.mark.requires_ffmpeg
def test_real_ffmpeg_filter_and_encoder_listings_are_parsed():
    """Guards against the parser silently returning nothing on the installed FFmpeg (it once did)."""
    import sys

    tools = FFmpegTools.discover()
    filters = tools.filters()
    assert {"scale", "overlay", "split", "null", "select", "anull"} <= filters, sorted(filters)[:20]
    assert {"libx264", "aac"} <= tools.encoders()
    if sys.platform.startswith("linux"):
        # Debian/Ubuntu builds include libass: the subtitle filter must be detected there.
        assert "ass" in filters


@pytest.mark.requires_ffmpeg
def test_probe_synthetic_video(tmp_path):
    video = make_test_video(tmp_path / "t.mp4", seconds=3)
    tools = FFmpegTools.discover()
    info = tools.probe(video)
    assert (info.width, info.height) == (640, 360)
    assert info.duration_s == pytest.approx(3, abs=0.5)
    assert info.audio_streams == 1
    assert "libx264" in tools.encoders()


@pytest.mark.requires_ffmpeg
def test_probe_rejects_non_video(tmp_path):
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"this is not a video")
    with pytest.raises(InvalidInput):
        FFmpegTools.discover().probe(fake)
