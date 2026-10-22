import { useEffect, useRef, useState } from "react";

import { fmtTime } from "../lib/format";
import { Button } from "./ui";

interface Props {
  src: string;
  start: number;
  end: number;
  /** Called with the current playback position when the user marks a new start/end. */
  onMark?: (kind: "start" | "end", seconds: number) => void;
  playable?: boolean;
}

/** Plays only the [start, end] range of a (possibly very long) recording served with HTTP Range. */
export function RangePlayer({ src, start, end, onMark, playable = true }: Props) {
  const ref = useRef<HTMLVideoElement>(null);
  const [now, setNow] = useState(start);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const video = ref.current;
    if (video && video.readyState >= 1) {
      video.currentTime = start;
      setNow(start);
    }
  }, [src, start, end]);

  function onLoaded() {
    const video = ref.current;
    if (video) {
      video.currentTime = start;
      setNow(start);
    }
  }

  function onTime() {
    const video = ref.current;
    if (!video) return;
    setNow(video.currentTime);
    if (video.currentTime >= end) {
      video.pause();
      video.currentTime = start;
    }
  }

  function playRange() {
    const video = ref.current;
    if (!video) return;
    video.currentTime = start;
    void video.play();
  }

  function seekBy(delta: number) {
    const video = ref.current;
    if (video) video.currentTime = Math.max(0, video.currentTime + delta);
  }

  if (!playable || failed) {
    return (
      <div className="notice notice-warn small">
        O navegador não consegue reproduzir este formato de vídeo (comum com HEVC/MKV). Use o ajuste numérico dos tempos e
        confira o resultado na prévia renderizada do Editor.
      </div>
    );
  }

  return (
    <div className="player">
      <video
        ref={ref}
        src={src}
        controls
        preload="metadata"
        onLoadedMetadata={onLoaded}
        onTimeUpdate={onTime}
        onError={() => setFailed(true)}
      />
      <div className="row wrap">
        <Button onClick={playRange}>▶ Assistir trecho ({fmtTime(start)}–{fmtTime(end)})</Button>
        <Button variant="ghost" onClick={() => seekBy(-2)}>−2 s</Button>
        <Button variant="ghost" onClick={() => seekBy(2)}>+2 s</Button>
        {onMark && (
          <>
            <Button variant="ghost" onClick={() => onMark("start", now)}>Início = {fmtTime(now)}</Button>
            <Button variant="ghost" onClick={() => onMark("end", now)}>Fim = {fmtTime(now)}</Button>
          </>
        )}
      </div>
    </div>
  );
}
