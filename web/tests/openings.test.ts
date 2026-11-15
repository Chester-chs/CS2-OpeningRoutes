import { afterEach, describe, expect, it, vi } from "vitest";
import { DataClient } from "../src/data";
import { nadesLink, rateText } from "../src/openings";

afterEach(() => vi.unstubAllGlobals());

describe("nades.ai links", () => {
  it("links only map-level grenade pages checked by hand", () => {
    expect(nadesLink("de_mirage", "smoke")).toBe(
      "https://nades.ai/zh/mirage/smokes",
    );
    expect(nadesLink("de_ancient", "incendiary")).toBe(
      "https://nades.ai/zh/ancient/molotovs",
    );
    expect(nadesLink("de_dust2", "he")).toBe(
      "https://nades.ai/zh/dust2/he-grenades",
    );
    expect(nadesLink("de_mirage", "flash")).toBe(
      "https://nades.ai/zh/mirage/flashbangs",
    );
  });
  it("never builds a link for unknown maps or grenades", () => {
    expect(nadesLink("de_train", "smoke")).toBeNull();
    expect(nadesLink("de_mirage", "decoy")).toBeNull();
    expect(nadesLink("de_mirage", "SnipersNest")).toBeNull();
  });
});

describe("gated rates", () => {
  it("shows a rate and interval only when the sample is large enough", () => {
    expect(
      rateText({
        status: "ok",
        rounds: 12,
        matches: 4,
        rate: 0.75,
        interval: [0.5, 0.9],
      }),
    ).toBe("75%（50%–90%）· 12 回合 / 4 场");
    expect(
      rateText({
        status: "insufficient",
        rounds: 9,
        matches: 2,
        rate: null,
        interval: null,
      }),
    ).toBe("样本不足 · 9 回合 / 2 场");
  });
});

describe("desktop openings request", () => {
  it("reads one map from the local API", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ map: "de_mirage", buckets: [] }), {
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetcher);
    const c = new DataClient();
    c.mode = "desktop";
    expect((await c.openings("de_mirage")).map).toBe("de_mirage");
    expect(fetcher.mock.calls[0][0]).toBe("/api/openings/de_mirage");
  });
});
