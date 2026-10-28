import { describe, expect, it } from "vitest";
import { draftPlan, placeName } from "../src/CTPatterns";
import type { Catalog, CTAnalysis, CTPattern } from "../src/types";

const pattern = {
  id: 0,
  name: "B 区加人 · A1 · 中1 · B3",
  name_en: "B-Heavy",
  paper_name: "B 区重兵",
  paper_name_en: "B-Heavy",
  rationale: "15 秒时 B 区人数占比最高。",
  name_source: "规则草拟（论文阈值），待人工确认",
  rounds: 10,
  ct_wins: 6,
  decided: 10,
  ct_win_rate: 0.6,
  shares: { "15": { A: 0.2, B: 0.6, Mid: 0.2, CT: 0, other: 0 } },
  setups: [{ setup: "A1 · 中1 · B3", rounds: 7 }],
  top_places: [],
  economy: { long_gun: 8, eco: 2 },
  teams: { Alpha: 10 },
  utility_per_round: [],
  representative: "r1",
  round_ids: ["r1"],
} as CTPattern;
const analysis = { map: "de_test", patterns: [pattern] } as CTAnalysis;
const throwRow = (id: string, side: string, time: number, round = "r1") => ({
  id,
  round_id: round,
  side,
  time,
  player: `P-${id}`,
});
const catalog = {
  places: { de_test: { Truck: "警家", BombsiteB: "BombsiteB" } },
  throws: [
    throwRow("late", "CT", 25),
    throwRow("b", "CT", 12),
    throwRow("a", "CT", 3),
    throwRow("t-side", "T", 5),
    throwRow("other-round", "CT", 4, "r2"),
  ],
} as unknown as Catalog;

describe("CT research helpers", () => {
  it("names learned spots with the curated label", () => {
    expect(placeName(catalog, "de_test", "Truck")).toBe("警家（Truck）");
    expect(placeName(catalog, "de_test", "BombsiteB·2")).toBe(
      "BombsiteB 2 号位",
    );
  });
  it("drafts a plan from the representative round's early CT utility", () => {
    const plan = draftPlan(catalog, analysis, pattern)!;
    expect(plan.side).toBe("CT");
    expect(plan.status).toBe("draft");
    expect(plan.area).toBe("B 区");
    expect(plan.steps.map((s) => s.throw_id)).toEqual(["a", "b"]);
    expect(plan.purpose).toContain("r1");
  });
  it("refuses to draft without CT utility", () => {
    expect(draftPlan({ ...catalog, throws: [] }, analysis, pattern)).toBeNull();
  });
});
