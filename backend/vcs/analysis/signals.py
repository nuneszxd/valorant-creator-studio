"""Pure signal-processing helpers for the audio loudness envelope. No I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..utils import clamp


def percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile (q in 0..100) of an ascending list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q / 100.0
    low = int(math.floor(pos))
    high = int(math.ceil(pos))
    frac = pos - low
    return sorted_values[low] * (1 - frac) + sorted_values[high] * frac


def moving_average(values: list[float], k: int) -> list[float]:
    """Centered moving average with an odd window k (edges use the available samples)."""
    if k <= 1 or not values:
        return list(values)
    half = k // 2
    prefix = [0.0]
    for v in values:
        prefix.append(prefix[-1] + v)
    out: list[float] = []
    n = len(values)
    for i in range(n):
        lo = max(0, i - half)
        hi = min(n, i + half + 1)
        out.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return out


@dataclass
class AudioProfile:
    window_s: float
    smoothed_db: list[float]
    intensity: list[float]  # 0..1, relative to this recording's own median/p95
    burst: list[float]  # 0..1, rise vs the previous seconds
    p30: float
    p50: float
    p95: float

    def index(self, t: float) -> int:
        return int(clamp(t / self.window_s, 0, max(0, len(self.intensity) - 1)))

    def time_of(self, index: int) -> float:
        return (index + 0.5) * self.window_s


def build_audio_profile(
    rms_db: list[float],
    window_s: float,
    *,
    smooth_s: float = 1.5,
    lookback_s: float = 10.0,
    burst_db: float = 12.0,
) -> AudioProfile:
    k = max(1, int(round(smooth_s / window_s)))
    if k % 2 == 0:
        k += 1
    smoothed = moving_average(rms_db, k)
    ordered = sorted(smoothed)
    p30, p50, p95 = percentile(ordered, 30), percentile(ordered, 50), percentile(ordered, 95)
    span = max(p95 - p50, 3.0)
    intensity = [clamp((v - p50) / span, 0.0, 1.0) for v in smoothed]

    lookback = max(1, int(round(lookback_s / window_s)))
    prefix = [0.0]
    for v in smoothed:
        prefix.append(prefix[-1] + v)
    burst: list[float] = []
    for i, v in enumerate(smoothed):
        lo = max(0, i - lookback)
        if i == lo:
            burst.append(0.0)
            continue
        base = (prefix[i] - prefix[lo]) / (i - lo)
        burst.append(clamp((v - base) / burst_db, 0.0, 1.0))
    return AudioProfile(window_s, smoothed, intensity, burst, p30, p50, p95)


def find_peaks(values: list[float], min_value: float, min_distance: int) -> list[int]:
    """Indices of local maxima >= min_value, at least min_distance apart (highest first wins)."""
    n = len(values)
    candidates: list[int] = []
    for i in range(n):
        v = values[i]
        if v < min_value:
            continue
        left = values[i - 1] if i > 0 else -1.0
        right = values[i + 1] if i < n - 1 else -1.0
        if v >= left and v > right:
            candidates.append(i)
    candidates.sort(key=lambda idx: values[idx], reverse=True)
    accepted: list[int] = []
    for idx in candidates:
        if all(abs(idx - other) >= min_distance for other in accepted):
            accepted.append(idx)
    return sorted(accepted)
