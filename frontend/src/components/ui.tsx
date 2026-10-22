import { useEffect, useRef, useState } from "react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

import { errorMessage } from "../lib/format";

export type Tone = "neutral" | "ok" | "warn" | "danger" | "info";

export function Card(props: { title?: ReactNode; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${props.className ?? ""}`}>
      {(props.title || props.actions) && (
        <header className="card-head">
          <h3>{props.title}</h3>
          <div className="row">{props.actions}</div>
        </header>
      )}
      {props.children}
    </section>
  );
}

export function Button(
  props: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "default" | "primary" | "danger" | "ghost"; busy?: boolean },
) {
  const { variant = "default", busy, children, className, disabled, ...rest } = props;
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      className={`btn btn-${variant} ${className ?? ""}`}
    >
      {busy ? "Aguarde…" : children}
    </button>
  );
}

export function Badge(props: { tone?: Tone; children: ReactNode; title?: string }) {
  return (
    <span className={`badge badge-${props.tone ?? "neutral"}`} title={props.title}>
      {props.children}
    </span>
  );
}

export function Field(props: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`field ${props.className ?? ""}`}>
      <span className="field-label">{props.label}</span>
      {props.children}
      {props.hint && <span className="field-hint">{props.hint}</span>}
    </label>
  );
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input type="text" {...props} className={`input ${props.className ?? ""}`} />;
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} className={`input ${props.className ?? ""}`} />;
}

function numberText(value: number | null): string {
  return value === null || Number.isNaN(value) ? "" : String(value);
}

/**
 * Numeric field that keeps what you type (including "-" or an empty box) while focused, and only
 * applies defaults/clamping when you leave the field. Valid numbers are reported while typing.
 */
export function NumberInput(props: {
  value: number | null;
  onChange: (value: number | null) => void;
  min?: number;
  max?: number;
  step?: number;
  placeholder?: string;
  disabled?: boolean;
}) {
  const [text, setText] = useState(numberText(props.value));
  const focused = useRef(false);

  useEffect(() => {
    if (!focused.current) setText(numberText(props.value));
  }, [props.value]);

  return (
    <input
      type="text"
      inputMode="decimal"
      className="input"
      value={text}
      placeholder={props.placeholder}
      disabled={props.disabled}
      aria-valuemin={props.min}
      aria-valuemax={props.max}
      onFocus={() => {
        focused.current = true;
      }}
      onChange={(event) => {
        const raw = event.target.value;
        setText(raw);
        const parsed = Number(raw.trim().replace(",", "."));
        if (raw.trim() !== "" && Number.isFinite(parsed)) props.onChange(parsed);
      }}
      onBlur={() => {
        focused.current = false;
        const raw = text.trim().replace(",", ".");
        if (raw === "") {
          props.onChange(null);
          setText(numberText(props.value));
          return;
        }
        const parsed = Number(raw);
        if (!Number.isFinite(parsed)) {
          setText(numberText(props.value));
          return;
        }
        let bounded = parsed;
        if (props.min !== undefined) bounded = Math.max(bounded, props.min);
        if (props.max !== undefined) bounded = Math.min(bounded, props.max);
        if (bounded !== parsed) props.onChange(bounded);
        setText(String(bounded));
      }}
    />
  );
}

export function Select(
  props: Omit<SelectHTMLAttributes<HTMLSelectElement>, "onChange"> & {
    value: string;
    onChange: (value: string) => void;
    options: Array<{ value: string; label: string }>;
  },
) {
  const { options, onChange, className, ...rest } = props;
  return (
    <select {...rest} className={`input ${className ?? ""}`} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  );
}

export function Checkbox(props: { checked: boolean; onChange: (checked: boolean) => void; label: ReactNode; disabled?: boolean }) {
  return (
    <label className="check">
      <input
        type="checkbox"
        checked={props.checked}
        disabled={props.disabled}
        onChange={(event) => props.onChange(event.target.checked)}
      />
      <span>{props.label}</span>
    </label>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="notice notice-danger" role="alert">
      {errorMessage(error)}
    </div>
  );
}

export function Notice(props: { tone?: Tone; children: ReactNode }) {
  return <div className={`notice notice-${props.tone ?? "info"}`}>{props.children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="empty">{children}</div>;
}

export function Loading({ what = "Carregando…" }: { what?: string }) {
  return <div className="muted">{what}</div>;
}

export function Tabs(props: { tabs: Array<{ key: string; label: string }>; active: string; onChange: (key: string) => void }) {
  return (
    <div className="tabs" role="tablist">
      {props.tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={props.active === tab.key}
          className={`tab ${props.active === tab.key ? "tab-active" : ""}`}
          onClick={() => props.onChange(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function PageHeader(props: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div>
        <h1>{props.title}</h1>
        {props.subtitle && <p className="muted">{props.subtitle}</p>}
      </div>
      <div className="row">{props.actions}</div>
    </div>
  );
}

export function Stat(props: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="stat">
      <div className="stat-value">{props.value}</div>
      <div className="stat-label">{props.label}</div>
      {props.hint && <div className="muted small">{props.hint}</div>}
    </div>
  );
}
