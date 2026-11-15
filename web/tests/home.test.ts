import { describe, expect, it } from "vitest";
import { mapRows, recentMatches, teamRows } from "../src/home";
import type { Catalog } from "../src/types";

// Synthetic library, clearly labelled test data.
const match = (
  id: string,
  map: string,
  date: string,
  label: string,
  verified = true,
) => ({
  id,
  map,
  source: { event: "Synthetic Cup", match: label, date, verified },
});
const catalog = {
  schema_version: 1,
  matches: [
    match("m1", "de_mirage", "2026-10-01", "Alpha vs Beta · Mirage"),
    match("m2", "de_ancient", "2026-10-03", "Beta vs Gamma · Ancient", false),
    match("m3", "de_mirage", "2026-09-20", "Alpha vs Gamma"),
  ],
  rounds: [
    { id: "m1-r1", match_id: "m1" },
    { id: "m1-r2", match_id: "m1" },
    { id: "m3-r1", match_id: "m3" },
  ],
  throws: [],
  plans: [],
} as unknown as Catalog;

describe("home tables", () => {
  it("lists maps with counts, using the summary when the desktop studio has it", () => {
    expect(mapRows(catalog)).toEqual([
      { map: "de_mirage", matches: 2, rounds: 3, throws: 0, complete: 0 },
      { map: "de_ancient", matches: 1, rounds: 0, throws: 0, complete: 0 },
    ]);
    const summary = {
      ...catalog,
      maps: [
        { map: "de_dust2", matches: 4, rounds: 80, throws: 900, complete: 1 },
      ],
    } as Catalog;
    expect(mapRows(summary)[0]).toEqual(summary.maps![0]);
  });
  it("lists teams by map games and their latest date", () => {
    expect(teamRows(catalog)).toEqual([
      { team: "Alpha", matches: 2, latest: "2026-10-01" },
      { team: "Beta", matches: 2, latest: "2026-10-03" },
      { team: "Gamma", matches: 2, latest: "2026-10-03" },
    ]);
  });
  it("shows the newest matches first with their teams and source check", () => {
    const rows = recentMatches(catalog, 2);
    expect(rows.map((r) => r.id)).toEqual(["m2", "m1"]);
    expect(rows[0]).toMatchObject({
      teams: "Beta vs Gamma",
      map: "de_ancient",
      verified: false,
    });
    expect(recentMatches({ ...catalog, matches: [] } as Catalog)).toEqual([]);
  });
});
