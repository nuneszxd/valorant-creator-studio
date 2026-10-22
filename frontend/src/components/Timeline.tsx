import { fmtTime } from "../lib/format";

export interface TimelineMarker {
  id: number;
  start: number;
  end: number;
  score: number;
  status: string;
}

interface Props {
  rms: number[];
  windowS: number;
  duration: number;
  markers: TimelineMarker[];
  scenes?: Array<[number, number]>;
  selectedId?: number | null;
  onSelect?: (id: number) => void;
}

/** Loudness curve of the recording with the suggested cuts highlighted (clickable). */
export function Timeline({ rms, windowS, duration, markers, scenes = [], selectedId, onSelect }: Props) {
  if (rms.length < 2 || duration <= 0) {
    return <div className="muted small">Sem curva de áudio: rode uma análise para ver a linha do tempo.</div>;
  }
  const min = Math.min(...rms);
  const max = Math.max(...rms);
  const span = Math.max(max - min, 1);
  const width = 1000;
  const height = 90;
  const points = rms
    .map((value, i) => {
      const x = ((i * windowS) / duration) * width;
      const y = height - ((value - min) / span) * (height - 6) - 3;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * duration);

  return (
    <div className="timeline">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label="Volume do áudio ao longo da gravação">
        {scenes.map(([t], i) => (
          <line key={`s${i}`} x1={(t / duration) * width} x2={(t / duration) * width} y1={0} y2={height} className="tl-scene" />
        ))}
        {markers.map((marker) => (
          <rect
            key={marker.id}
            x={(marker.start / duration) * width}
            width={Math.max(((marker.end - marker.start) / duration) * width, 3)}
            y={0}
            height={height}
            className={`tl-marker tl-${marker.status} ${selectedId === marker.id ? "tl-selected" : ""}`}
            onClick={() => onSelect?.(marker.id)}
          >
            <title>{`${fmtTime(marker.start)}–${fmtTime(marker.end)} · pontuação ${marker.score.toFixed(0)}`}</title>
          </rect>
        ))}
        <polyline points={points} className="tl-line" />
      </svg>
      <div className="timeline-axis small muted">
        {ticks.map((t) => (
          <span key={t}>{fmtTime(t)}</span>
        ))}
      </div>
    </div>
  );
}
