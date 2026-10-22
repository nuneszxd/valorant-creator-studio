import { describe, expect, it } from "vitest";

import { retimeCues } from "./cues";

const cues = [
  { start: 2, end: 5, text: "primeira", words: [{ start: 2, end: 3, text: "pri" }, { start: 3, end: 5, text: "meira" }] },
  { start: 10, end: 14, text: "segunda" },
];

describe("retimeCues", () => {
  it("moves cues earlier when the start moves later, so they stay on the same moment", () => {
    const out = retimeCues(cues, 100, 104, 120); // start +4 s
    expect(out).toHaveLength(2);
    expect(out[1]).toMatchObject({ start: 6, end: 10 });
    expect(out[0].start).toBe(0); // clamped: it began before the new start
    expect(out[0].end).toBe(1);
    expect(out[0].words).toEqual([{ start: 0, end: 1, text: "meira" }]);
  });

  it("moves cues later when the start moves earlier", () => {
    const out = retimeCues(cues, 100, 98, 120);
    expect(out[0]).toMatchObject({ start: 4, end: 7 });
  });

  it("drops cues outside the new end and clamps the last one", () => {
    const out = retimeCues(cues, 100, 100, 112); // duration 12
    expect(out).toHaveLength(2);
    expect(out[1].end).toBe(12);
    const shorter = retimeCues(cues, 100, 100, 108); // new end at 108 s => duration 8 s
    expect(shorter).toHaveLength(1);
    expect(shorter[0].text).toBe("primeira");
  });

  it("returns an empty list when nothing is left", () => {
    expect(retimeCues(cues, 100, 200, 210)).toEqual([]);
  });
});
