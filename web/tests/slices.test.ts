import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DataClient,
  EMPTY,
  filterThrows,
  mapOfThrow,
  mergeSlice,
  sliceOf,
  trajectoryPoints,
} from "../src/data";
import type { Catalog, MapSlice } from "../src/types";

afterEach(() => vi.unstubAllGlobals());
const json = (data: unknown) =>
  new Response(JSON.stringify(data), {
    headers: { "Content-Type": "application/json" },
  });

// Synthetic two-map library, clearly labelled test data.
const match = (id: string, map: string) => ({
  id,
  map,
  source: {
    verified: true,
    event: "Synthetic",
    match: "A v B",
    date: "2025-01-01",
  },
});
const round = (id: string, match_id: string, extra = {}) => ({
  id,
  match_id,
  number: 1,
  is_pistol: true,
  equipment: [],
  ...extra,
});
const row = (id: string, match_id: string, map: string) => ({
  id,
  match_id,
  map,
  round_id: `${match_id}-r1`,
  kind: "smoke",
  side: "CT",
  player: "Alice",
  team: "A",
  teaching: {},
  gaps: ["title"],
});
const summary = {
  ...EMPTY,
  matches: [match("a1", "de_a"), match("b1", "de_b")],
  rounds: [round("a1-r1", "a1"), round("b1-r1", "b1")],
  maps: [
    { map: "de_a", matches: 1, rounds: 1, throws: 1, complete: 0 },
    { map: "de_b", matches: 1, rounds: 1, throws: 1, complete: 0 },
  ],
} as unknown as Catalog;
const slice = (map: string, matchId: string, label = "") =>
  ({
    map,
    throws: [row(`${matchId}-t64-x${label}`, matchId, map)],
    rounds: [
      round(`${matchId}-r1`, matchId, {
        formation: { snapshots: [] },
        ct_pattern: 1,
      }),
    ],
    variants: [
      { id: `v-${map}${label}`, map, members: [`${matchId}-t64-x${label}`] },
    ],
    ct_patterns: { [map]: { map, patterns: [] } },
  }) as unknown as MapSlice;

describe("per-map studio slices", () => {
  it("merges one map at a time and keeps the others", () => {
    const a = mergeSlice(summary, slice("de_a", "a1"));
    const both = mergeSlice(a, slice("de_b", "b1"));
    expect(both.loaded).toEqual(["de_a", "de_b"]);
    expect(both.throws.map((t) => t.map)).toEqual(["de_a", "de_b"]);
    expect(both.rounds.map((r) => r.id)).toEqual(["a1-r1", "b1-r1"]);
    expect(both.rounds[0].formation).toBeDefined();
    expect(Object.keys(both.ct_patterns || {})).toEqual(["de_a", "de_b"]);
    const again = mergeSlice(both, slice("de_a", "a1", "new"));
    expect(again.throws.map((t) => t.id)).toEqual(["a1-t64-xnew", "b1-t64-x"]);
    expect(again.variants?.map((v) => v.id)).toEqual(["v-de_anew", "v-de_b"]);
    expect(filterThrows(again, { map: "de_b" })).toHaveLength(1);
  });
  it("drops a map's CT analysis when the new slice has none", () => {
    const a = mergeSlice(summary, slice("de_a", "a1"));
    const none = { ...slice("de_a", "a1"), ct_patterns: {} };
    expect(mergeSlice(a, none).ct_patterns).toEqual({});
  });
  it("extracts a loaded map so a refresh can keep it", () => {
    const both = mergeSlice(
      mergeSlice(summary, slice("de_a", "a1")),
      slice("de_b", "b1"),
    );
    const kept = mergeSlice(summary, sliceOf(both, "de_b"));
    expect(kept.throws).toEqual(both.throws.filter((t) => t.map === "de_b"));
    expect(kept.rounds.find((r) => r.id === "b1-r1")?.formation).toBeDefined();
    expect(kept.loaded).toEqual(["de_b"]);
  });
  it("finds a throw's map from its match id", () => {
    expect(mapOfThrow(summary, "b1-t64-x")).toBe("de_b");
    expect(mapOfThrow(summary, "t1")).toBeUndefined();
  });
  it("draws cards from the preview and detail from the full path", () => {
    expect(trajectoryPoints({ trajectory_preview: [[1, 2, 3, 4]] })).toEqual([
      [1, 2, 3, 4],
    ]);
    expect(
      trajectoryPoints({
        trajectory: [[5, 6, 7, 8]],
        trajectory_preview: [[1, 2, 3, 4]],
      }),
    ).toEqual([[5, 6, 7, 8]]);
    expect(trajectoryPoints({})).toEqual([]);
  });
});

describe("desktop slice requests", () => {
  it("opens with the summary, then fetches maps and throws by id", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(json({ token: "t" }))
      .mockResolvedValueOnce(json(summary))
      .mockResolvedValueOnce(json(slice("de_a", "a1")))
      .mockResolvedValueOnce(
        json({ ...row("a1-t64-x", "a1", "de_a"), trajectory: [[1, 2, 3, 4]] }),
      );
    vi.stubGlobal("fetch", fetcher);
    const c = new DataClient();
    expect((await c.init()).maps).toHaveLength(2);
    expect((await c.loadMap("de_a")).map).toBe("de_a");
    expect((await c.throwDetail("a1-t64-x"))?.trajectory).toEqual([
      [1, 2, 3, 4],
    ]);
    expect(fetcher.mock.calls.map((x) => x[0])).toEqual([
      "/api/session",
      "/api/catalog/summary",
      "/api/catalog/maps/de_a",
      "/api/throws/a1-t64-x",
    ]);
  });
  it("needs no extra requests for the static site", async () => {
    const c = new DataClient();
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    expect(await c.throwDetail("x")).toBeNull();
    expect(fetcher).not.toHaveBeenCalled();
  });
});
