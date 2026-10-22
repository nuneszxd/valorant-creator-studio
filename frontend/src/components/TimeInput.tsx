import { useEffect, useState } from "react";

import { fmtPrecise, parseTime } from "../lib/format";

/** Text input for a time position: accepts "1:05.5", "65" or "1:02:03"; commits on blur/Enter. */
export function TimeInput(props: { value: number; onChange: (seconds: number) => void; max?: number; ariaLabel?: string }) {
  const [text, setText] = useState(fmtPrecise(props.value));

  useEffect(() => {
    setText(fmtPrecise(props.value));
  }, [props.value]);

  function commit() {
    const parsed = parseTime(text);
    if (parsed === null) {
      setText(fmtPrecise(props.value));
      return;
    }
    const bounded = props.max !== undefined ? Math.min(parsed, props.max) : parsed;
    // Only report a real change: re-typing the same position must not mark the form as edited.
    if (Math.abs(bounded - props.value) >= 0.05) props.onChange(bounded);
    else setText(fmtPrecise(props.value));
  }

  return (
    <input
      className="input"
      value={text}
      aria-label={props.ariaLabel}
      onChange={(event) => setText(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") commit();
      }}
      inputMode="decimal"
    />
  );
}
