import { describe, expect, it } from "vitest";
import {
  areaOptions,
  filterThrows,
  pistolSummary,
  variantPeers,
  visibleRounds,
} from "../src/data";
import type { Catalog } from "../src/types";

const t = (id: string, player: string, extra = {}) => ({
  id,
  match_id: "m",
  round_id: "r1",
  round_number: 1,
  map: "de_test",
  kind: "smoke",
  side: "CT",
  player,
  team: "A",
  time: 5,
  teaching: {},
  gaps: ["reproduction"],
  origin_area: "CT 出生点",
  effect_area: "中路",
  variant_id: "v1",
  ...extra,
});
const data = {
  schema_version: 1,
  matches: [
    { id: "m", map: "de_test", source: { verified: true, date: "2025-01-01" } },
  ],
  throws: [
    t("a", "Alice"),
    t("b", "Bob"),
    t("c", "Carol", {
      variant_id: "v2",
      effect_area: "",
      origin_area: "House",
    }),
  ],
  rounds: [
    {
      id: "r1",
      match_id: "m",
      number: 1,
      is_pistol: true,
      complete: true,
      winner: "T",
      equipment: [{ player: "Alice", side: "CT", team: "A" }],
    },
    {
      id: "r13",
      match_id: "m",
      number: 13,
      is_pistol: false,
      excluded: true,
      complete: true,
      winner: "CT",
      equipment: [{ player: "Alice", side: "CT", team: "A" }],
    },
  ],
  plans: [],
  variants: [
    {
      id: "v1",
      source: "auto",
      members: ["a", "b"],
      players: ["Alice", "Bob"],
      map: "de_test",
      kind: "smoke",
      side: "CT",
      title: "",
      purpose: "",
      reviewed: false,
      reviewer: "",
    },
    {
      id: "v2",
      source: "manual",
      members: ["c"],
      players: ["Carol"],
      map: "de_test",
      kind: "smoke",
      side: "CT",
      title: "",
      purpose: "",
      reviewed: false,
      reviewer: "",
    },
  ],
  places: { de_test: {} },
} as unknown as Catalog;

describe("areas, lineup variants and reviewed rounds", () => {
  it("filters by release or effect area and searches area names", () => {
    expect(filterThrows(data, { area: "中路" }).map((x) => x.id)).toEqual([
      "a",
      "b",
    ]);
    expect(filterThrows(data, { area: "House" }).map((x) => x.id)).toEqual([
      "c",
    ]);
    expect(filterThrows(data, { query: "house" }).map((x) => x.id)).toEqual([
      "c",
    ]);
    expect(areaOptions(data, "de_test")).toEqual([
      "CT 出生点",
      "House",
      "中路",
    ]);
  });
  it("lists other professional examples of the same lineup", () => {
    const peers = variantPeers(data, data.throws[0]);
    expect(peers.variant?.id).toBe("v1");
    expect(peers.others.map((x) => x.player)).toEqual(["Bob"]);
    expect(variantPeers(data, data.throws[2]).others).toEqual([]);
  });
  it("drops curator-excluded rounds from round lists and pistol statistics", () => {
    const all = visibleRounds(data, {}, false);
    expect(all.map((r) => r.number)).toEqual([1]);
    expect(pistolSummary(visibleRounds(data, {}, true)).samples).toBe(1);
  });
});
