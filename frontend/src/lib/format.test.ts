import { describe, expect, it } from "vitest";

import { confidenceTone, fmtBytes, fmtPercent, fmtPrecise, fmtTime, parseTime, prettyKey, scoreTone } from "./format";

describe("fmtTime", () => {
  it("formats minutes and hours", () => {
    expect(fmtTime(0)).toBe("0:00");
    expect(fmtTime(65)).toBe("1:05");
    expect(fmtTime(3661)).toBe("1:01:01");
  });
  it("handles missing values", () => {
    expect(fmtTime(null)).toBe("–");
    expect(fmtTime(undefined)).toBe("–");
  });
});

describe("parseTime", () => {
  it("accepts m:ss, h:mm:ss, plain and decimal seconds", () => {
    expect(parseTime("1:05")).toBe(65);
    expect(parseTime("1:01:01")).toBe(3661);
    expect(parseTime("90")).toBe(90);
    expect(parseTime("1:05,5")).toBe(65.5);
  });
  it("rejects garbage", () => {
    expect(parseTime("")).toBeNull();
    expect(parseTime("abc")).toBeNull();
    expect(parseTime("1:2:3:4")).toBeNull();
    expect(parseTime("-5")).toBeNull();
  });
  it("round-trips with fmtPrecise", () => {
    expect(fmtPrecise(65.5)).toBe("1:05.5");
    expect(parseTime(fmtPrecise(125.4))).toBeCloseTo(125.4, 1);
  });
});

describe("misc formatting", () => {
  it("formats bytes", () => {
    expect(fmtBytes(512)).toBe("512 B");
    expect(fmtBytes(1536)).toBe("1.5 KB");
    expect(fmtBytes(null)).toBe("–");
  });
  it("formats percentages and keys", () => {
    expect(fmtPercent(0.1234)).toBe("12.3%");
    expect(fmtPercent(null)).toBe("–");
    expect(prettyKey("videos_com_o_tema")).toBe("videos com o tema");
  });
  it("maps tones", () => {
    expect(scoreTone(80)).toBe("ok");
    expect(scoreTone(50)).toBe("warn");
    expect(scoreTone(10)).toBe("neutral");
    expect(confidenceTone("média")).toBe("warn");
    expect(confidenceTone("muito baixa")).toBe("danger");
  });
});
