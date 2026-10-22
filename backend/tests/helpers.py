"""Test helpers. Media fixtures are generated on the fly with FFmpeg - no real video is ever committed."""

from __future__ import annotations

import subprocess
from pathlib import Path


def make_test_video(
    path: Path,
    seconds: int = 8,
    *,
    burst: tuple[float, float] | None = None,
    with_audio: bool = True,
    size: str = "640x360",
    fps: int = 30,
) -> Path:
    """Generate a synthetic MP4. `burst=(start, end)` makes the audio loud only in that range."""
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-v", "error", "-y",
            "-f", "lavfi", "-i", f"testsrc=size={size}:rate={fps}"]
    if with_audio:
        if burst:
            audio = (
                "sine=frequency=440:sample_rate=16000,"
                f"volume='if(between(t,{burst[0]},{burst[1]}),1.0,0.02)':eval=frame"
            )
        else:
            audio = "sine=frequency=440:sample_rate=16000,volume=0.1"
        args += ["-f", "lavfi", "-i", audio]
    args += ["-t", str(seconds), "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast"]
    if with_audio:
        args += ["-c:a", "aac"]
    args.append(str(path))
    subprocess.run(args, check=True, capture_output=True, timeout=120)
    return path
