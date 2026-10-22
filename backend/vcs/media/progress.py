"""Turn FFmpeg `-progress pipe:1` output into real job progress."""

from __future__ import annotations

from typing import Any


class FfmpegProgress:
    """Feed it stdout lines; it reports out_time / total as real progress (or nothing)."""

    def __init__(self, ctx: Any, total_s: float | None, label: str) -> None:
        self.ctx = ctx
        self.total_s = total_s if total_s and total_s > 0 else None
        self.label = label
        self.last_seconds: float | None = None

    def feed(self, line: str) -> None:
        if line.startswith("out_time_us=") or line.startswith("out_time_ms="):
            raw = line.split("=", 1)[1].strip()
            try:
                micros = int(raw)
            except ValueError:
                return
            if micros < 0:
                return
            self.last_seconds = micros / 1_000_000
            if self.total_s:
                self.ctx.set_progress(min(self.last_seconds / self.total_s, 1.0), self.label)
        elif line.strip() == "progress=end" and self.total_s:
            self.ctx.set_progress(1.0, self.label, force=True)

    def start(self) -> None:
        """Announce the stage; progress stays indeterminate until FFmpeg reports real numbers."""
        self.ctx.set_progress(None, self.label, force=True)
