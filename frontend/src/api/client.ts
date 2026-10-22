export class ApiError extends Error {
  status: number;
  code: string;
  details: unknown;

  constructor(message: string, status: number, code = "error", details: unknown = null) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

interface ValidationItem {
  loc?: Array<string | number>;
  msg?: string;
}

/** Turn either the app's {error:{message}} or FastAPI's {detail:[...]} into one readable message. */
export function messageFromBody(body: unknown, fallback: string): { message: string; code: string; details: unknown } {
  if (body && typeof body === "object") {
    const record = body as Record<string, unknown>;
    const error = record.error as { message?: string; code?: string; details?: unknown } | undefined;
    if (error && typeof error.message === "string") {
      return { message: error.message, code: error.code ?? "error", details: error.details ?? null };
    }
    const detail = record.detail;
    if (Array.isArray(detail)) {
      const parts = (detail as ValidationItem[]).map((item) => {
        const where = (item.loc ?? []).filter((p) => p !== "body").join(".");
        return where ? `${where}: ${item.msg ?? "valor inválido"}` : (item.msg ?? "valor inválido");
      });
      return { message: parts.join("; ") || fallback, code: "validation", details: detail };
    }
    if (typeof detail === "string") {
      return { message: detail, code: "error", details: null };
    }
  }
  return { message: fallback, code: "error", details: null };
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const hasBody = body !== undefined;
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers: hasBody ? { "Content-Type": "application/json" } : undefined,
      body: hasBody ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("Não consegui falar com o aplicativo. Ele ainda está rodando?", 0, "network");
  }
  if (!response.ok) {
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      parsed = null;
    }
    const info = messageFromBody(parsed, `Erro ${response.status}`);
    throw new ApiError(info.message, response.status, info.code, info.details);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>("PUT", path, body),
  patch: <T>(path: string, body: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
};

/** Build a query string, skipping empty values. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}
