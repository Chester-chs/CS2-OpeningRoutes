import { describe, expect, it } from "vitest";
import { draftPlan } from "../src/CTPatterns";
import {
  areaOptions,
  filterThrows,
  isMisthrow,
  misthrowReason,
  teachingLabels,
} from "../src/data";
import type { Catalog, CTAnalysis, CTPattern, Misthrow } from "../src/types";

// Synthetic library, clearly labelled test data.
const flag = (extra: Partial<Misthrow> = {}): Misthrow => ({
  flagged: true,
  source: "auto",
  auto: { rule: "bounce_back", distance: 132 },
  note: "",
  reviewer: "",
  at: "",
  conflict: false,
  ...extra,
});
const row = (id: string, extra = {}) => ({
  id,
  match_id: "m",
  round_id: "r1",
  map: "de_test",
  kind: "smoke",
  side: "CT",
  player: "Alice",
  team: "A",
  time: 5,
  origin_area: `area-${id}`,
  teaching: {},
  gaps: ["title"],
  ...extra,
});
const catalog = {
  schema_version: 1,
  matches: [{ id: "m", map: "de_test", source: { verified: true, date: "2025-01-01" } }],
  rounds: [],
  plans: [],
  throws: [
    row("good"),
    row("botched", { misthrow: flag() }),
    row("kept", { misthrow: flag({ flagged: false, source: "manual" }) }),
  ],
} as unknown as Catalog;

describe("misthrown grenades", () => {
  it("are hidden from the library unless asked for", () => {
    expect(filterThrows(catalog, {}).map((t) => t.id)).toEqual(["good", "kept"]);
    expect(filterThrows(catalog, { status: "pending" }).map((t) => t.id)).toEqual([
      "good",
      "kept",
    ]);
    expect(filterThrows(catalog, { status: "misthrow" }).map((t) => t.id)).toEqual([
      "botched",
    ]);
    expect(areaOptions(catalog)).toEqual(["area-good", "area-kept"]);
  });
  it("are recognised on full rows and on exported round events", () => {
    expect(isMisthrow({ misthrow: flag() })).toBe(true);
    expect(isMisthrow({ misthrow: flag({ flagged: false }) })).toBe(false);
    expect(isMisthrow({ misthrow: true })).toBe(true);
    expect(isMisthrow({})).toBe(false);
  });
  it("explain why a throw was flagged", () => {
    expect(misthrowReason(flag())).toContain("132");
    expect(
      misthrowReason(
        flag({ auto: { rule: "variant_outlier", distance: 912, variant_id: "v" } }),
      ),
    ).toContain("912");
    expect(
      misthrowReason(flag({ source: "manual", auto: null, note: "撞到门框" })),
    ).toContain("撞到门框");
    expect(teachingLabels.misthrow).toBeTruthy();
  });
  it("are left out of plans drafted from CT research", () => {
    const pattern = {
      name: "B 区加人",
      rationale: "",
      rounds: 1,
      shares: { "15": { B: 1 } },
      setups: [],
      economy: {},
      representative: "r1",
    } as unknown as CTPattern;
    const analysis = { map: "de_test", patterns: [pattern] } as CTAnalysis;
    expect(
      draftPlan(catalog, analysis, pattern)?.steps.map((s) => s.throw_id),
    ).toEqual(["good", "kept"]);
  });
});
