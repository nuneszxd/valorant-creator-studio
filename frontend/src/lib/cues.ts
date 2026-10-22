import type { Cue } from "../api/types";

const round = (n: number) => Math.round(n * 1000) / 1000;

/**
 * Keep subtitles attached to the same moments of the recording when the cut changes.
 * Cue times are relative to the clip start, so moving the start by +5 s moves every cue by -5 s.
 * Cues (and words) that fall outside the new range are dropped or clamped.
 */
export function retimeCues(cues: Cue[], oldStart: number, newStart: number, newEnd: number): Cue[] {
  const shift = oldStart - newStart;
  const duration = Math.max(newEnd - newStart, 0);
  const out: Cue[] = [];
  for (const cue of cues) {
    const start = cue.start + shift;
    const end = cue.end + shift;
    if (end <= 0 || start >= duration) continue;
    const words = cue.words
      ? cue.words
          .map((w) => ({ ...w, start: w.start + shift, end: w.end + shift }))
          .filter((w) => w.end > 0 && w.start < duration)
          .map((w) => ({ ...w, start: round(Math.max(w.start, 0)), end: round(Math.min(w.end, duration)) }))
      : cue.words;
    const next: Cue = { ...cue, start: round(Math.max(start, 0)), end: round(Math.min(end, duration)), words };
    if (next.end - next.start >= 0.05) out.push(next);
  }
  return out;
}
