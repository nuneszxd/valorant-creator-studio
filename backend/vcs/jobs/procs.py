"""Subprocess helpers. Commands are always argument lists (never a shell string)."""

from __future__ import annotations

import subprocess
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class ProcResult:
    returncode: int
    stderr_tail: str
    timed_out: bool = False


def terminate_process(proc: subprocess.Popen, grace_s: float = 5.0) -> None:
    """Ask the process to stop, then kill it if it ignores us."""
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except OSError:
        return

    def _kill_later() -> None:
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    timer = threading.Timer(grace_s, _kill_later)
    timer.daemon = True
    timer.start()


def run_streaming(
    args: Sequence[Any],
    *,
    cwd: Path | None = None,
    ctx: Any = None,
    on_line: Callable[[str], None] | None = None,
    timeout: float | None = None,
) -> ProcResult:
    """Run a command, streaming stdout line by line. stderr is captured (last 200 lines).

    `ctx` is an optional job context providing register_process/unregister_process/check_cancelled.
    """
    proc = subprocess.Popen(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        creationflags=_NO_WINDOW,
    )
    stderr_lines: deque[str] = deque(maxlen=200)

    def _drain() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())

    drainer = threading.Thread(target=_drain, daemon=True)
    drainer.start()
    if ctx is not None:
        ctx.register_process(proc)
    timed_out = threading.Event()
    timer: threading.Timer | None = None
    if timeout:
        def _on_timeout() -> None:
            timed_out.set()
            terminate_process(proc)

        timer = threading.Timer(timeout, _on_timeout)
        timer.daemon = True
        timer.start()
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if on_line is not None:
                on_line(line.rstrip("\r\n"))
        returncode = proc.wait()
    finally:
        if timer is not None:
            timer.cancel()
        if ctx is not None:
            ctx.unregister_process(proc)
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass
            proc.wait()
        drainer.join(timeout=2)
    if ctx is not None:
        ctx.check_cancelled()
    return ProcResult(returncode=returncode, stderr_tail="\n".join(stderr_lines), timed_out=timed_out.is_set())


def run_capture(args: Sequence[Any], *, timeout: float = 60, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run a short command and capture its output."""
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=_NO_WINDOW,
    )
