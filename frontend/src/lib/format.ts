/** Seconds -> "M:SS" or "H:MM:SS". */
export function fmtTime(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "–";
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, "0");
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${ss}`;
  return `${m}:${ss}`;
}

/** Like fmtTime but keeps one decimal, for precise cut points ("1:05.5"). */
export function fmtPrecise(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "";
  const total = Math.max(0, seconds);
  const m = Math.floor(total / 60);
  const s = total - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

/** "1:02:03", "2:03" or "123" -> seconds (null when invalid). */
export function parseTime(text: string): number | null {
  const clean = text.trim().replace(",", ".");
  if (!clean) return null;
  const parts = clean.split(":");
  if (parts.length > 3) return null;
  let total = 0;
  for (const part of parts) {
    const n = Number(part);
    if (!Number.isFinite(n) || n < 0) return null;
    total = total * 60 + n;
  }
  return total;
}

export function fmtBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined) return "–";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes / 1024;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[i]}`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
}

export function fmtDay(iso: string | null | undefined): string {
  if (!iso) return "–";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("pt-BR");
}

export function fmtNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return "–";
  return value.toLocaleString("pt-BR", { maximumFractionDigits: 1 });
}

export function fmtPercent(fraction: number | null | undefined, digits = 1): string {
  if (fraction === null || fraction === undefined) return "–";
  return `${(fraction * 100).toFixed(digits)}%`;
}

/** "videos_com_o_tema" -> "videos com o tema". */
export function prettyKey(key: string): string {
  return key.replace(/_/g, " ");
}

export function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  return String(error);
}

export function scoreTone(score: number): "ok" | "warn" | "neutral" {
  if (score >= 70) return "ok";
  if (score >= 45) return "warn";
  return "neutral";
}

export function confidenceTone(confidence: string): "ok" | "warn" | "neutral" | "danger" {
  if (confidence === "alta") return "ok";
  if (confidence === "média") return "warn";
  if (confidence === "muito baixa") return "danger";
  return "neutral";
}
