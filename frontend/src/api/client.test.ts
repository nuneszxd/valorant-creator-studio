import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, api, messageFromBody, qs } from "./client";

describe("messageFromBody", () => {
  it("reads the app error envelope", () => {
    const info = messageFromBody({ error: { code: "not_found", message: "Gravação 3 não encontrada." } }, "x");
    expect(info.message).toBe("Gravação 3 não encontrada.");
    expect(info.code).toBe("not_found");
  });
  it("reads FastAPI validation errors", () => {
    const info = messageFromBody({ detail: [{ loc: ["body", "render", "width"], msg: "deve ser par" }] }, "x");
    expect(info.message).toBe("render.width: deve ser par");
  });
  it("falls back", () => {
    expect(messageFromBody(null, "Erro 500").message).toBe("Erro 500");
    expect(messageFromBody({ detail: "texto" }, "x").message).toBe("texto");
  });
});

describe("qs", () => {
  it("skips empty values", () => {
    expect(qs({ a: 1, b: "", c: null, d: undefined, e: "x y", f: false })).toBe("?a=1&e=x+y&f=false");
    expect(qs({})).toBe("");
  });
});

describe("api", () => {
  afterEach(() => vi.restoreAllMocks());

  it("sends JSON and parses the response", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    const result = await api.post<{ ok: boolean }>("/api/x", { a: 1 });
    expect(result.ok).toBe(true);
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    expect(init.body).toBe('{"a":1}');
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("throws ApiError with the server message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify({ error: { code: "invalid_input", message: "Caminho inválido." } }), { status: 422 })),
      ),
    );
    await expect(api.get("/api/y")).rejects.toMatchObject({ message: "Caminho inválido.", status: 422 });
    await expect(api.get("/api/y")).rejects.toBeInstanceOf(ApiError);
  });

  it("explains network failures", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("failed")));
    await expect(api.get("/api/z")).rejects.toMatchObject({ code: "network" });
  });
});
