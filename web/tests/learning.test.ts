import { afterEach, describe, expect, it, vi } from "vitest";
import { DataClient } from "../src/data";
import {
  draftLearningPlan,
  patchSplit,
  periodLabel,
  practiceFromSample,
  sampleMatchesContext,
} from "../src/learning";
import type { LearningProfile, LearningSample } from "../src/learning";
import type { Throw } from "../src/types";

afterEach(() => vi.unstubAllGlobals());
const profile = {
  id: "a".repeat(24),
  name: "Player",
  map: "de_mirage",
  side: "CT",
  area_label: "A 区",
  version: "test",
  counts: { rounds: 2, matches: 1 },
  team: "Alpha",
} as LearningProfile;
const sample = {
  round_id: "m-r1",
  number: 1,
  player_ids: ["111"],
  pistol: true,
  economy: "pistol",
  score: "tied",
  side: "CT",
  source: { date: "2026-01-01", match: "A vs B" },
  utility: [{ id: "good" }, { id: "foreign" }, { id: "bad" }],
  routes: { "111": [{ place: "BombsiteA", start: 3, end: 20 }] },
  practice: ["核对装备", "对照开局移动"],
} as unknown as LearningSample;

describe("player-area learning workflow", () => {
  it("drafts only same-round, same-side observed throws and retains provenance", () => {
    const base = {
      player_id: "111",
      side: "CT",
      time: 2,
      player: "Player",
      round_id: "m-r1",
    };
    const throws = [
      { ...base, id: "good" },
      { ...base, id: "foreign", round_id: "m-r2" },
      { ...base, id: "bad", misthrow: { flagged: true } },
    ] as Throw[];
    const plan = draftLearningPlan(profile, sample, throws)!;
    expect(plan.status).toBe("draft");
    expect(plan.steps.map((s) => s.throw_id)).toEqual(["good"]);
    expect(plan.source_round_id).toBe("m-r1");
    expect(plan.source_players).toEqual(["111"]);
    expect(plan.learning_profile_id).toBe(profile.id);
  });
  it("keeps a pistol movement checklist even when there is no utility", () => {
    const empty = { ...sample, utility: [] };
    expect(draftLearningPlan(profile, empty, [])).toBeNull();
    expect(practiceFromSample(profile, empty).steps).toContain("对照开局移动");
    expect(sampleMatchesContext(sample, "pistol")).toBe(true);
    expect(sampleMatchesContext(sample, "non_pistol")).toBe(false);
    expect(sampleMatchesContext(sample, "economy:pistol")).toBe(true);
  });
  it("personalizes practice with the sample's actual movement and throw times", () => {
    const actual = {
      ...sample,
      utility: [
        {
          id: "good",
          player_id: "111",
          player: "Player",
          time: 4.25,
          kind: "smoke",
        },
      ],
    } as LearningSample;
    const steps = practiceFromSample(profile, actual).steps.join("\n");
    expect(steps).toContain("3–20s BombsiteA");
    expect(steps).toContain("4.25s");
    expect(steps).toContain("烟雾弹");
  });
  it("old static v1 bundles have an honest empty learning entry without a network failure", async () => {
    const client = new DataClient();
    const fetcher = vi.fn();
    vi.stubGlobal("fetch", fetcher);
    const result = await client.learningIndex();
    expect(result.state).toBe("unavailable");
    expect(fetcher).not.toHaveBeenCalled();
  });
  it("checks static profile integrity and rejects unsafe profile identifiers", async () => {
    const client = new DataClient();
    client.files = { [`learning/profiles/${profile.id}.json`]: "incorrect" };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify(profile))),
    );
    await expect(client.learningProfile(profile.id)).rejects.toThrow(
      "校验失败",
    );
    await expect(client.learningProfile("../other")).rejects.toThrow(
      "档案编号",
    );
  });
});

describe("map eras", () => {
  const pooled = {
    ...profile,
    version: "de_mirage:2026-09/10",
    era: {
      id: "de_mirage:2026-09/10",
      label: "2026-09/10",
      from: "2026-09-01",
      to: "2026-10-31",
    },
    patches: {
      "14190": { rounds: 52, matches: 3 },
      "14188": { rounds: 31, matches: 2 },
    },
  } as LearningProfile;
  it("names the pooled period and lists the patches by share", () => {
    expect(periodLabel(pooled)).toBe("地图时期 2026-09/10");
    expect(patchSplit(pooled)).toBe(
      "补丁 14190 · 52 局 / 3 场；14188 · 31 局 / 2 场",
    );
  });
  it("falls back to the exact patch for profiles outside an era or old packs", () => {
    expect(periodLabel(profile)).toBe("版本 test");
    expect(patchSplit(profile)).toBe("版本 test");
  });
  it("writes each sample's own patch into a plan draft", () => {
    const own = { ...sample, game_version: "14188" } as LearningSample;
    const draft = draftLearningPlan(pooled, own, [
      {
        id: "good",
        player_id: "111",
        side: "CT",
        round_id: "m-r1",
        time: 3,
        kind: "smoke",
      } as unknown as Throw,
    ]);
    expect(draft?.conditions).toContain("补丁 14188");
  });
});
