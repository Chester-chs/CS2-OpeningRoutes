import { afterEach, describe, expect, it, vi } from "vitest";
import {
  DataClient,
  EMPTY,
  filterThrows,
  mediaUrl,
  pistolSummary,
  visibleRounds,
} from "../src/data";
import type { Catalog } from "../src/types";

afterEach(() => vi.unstubAllGlobals());
const response = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
const digest = async (value: string) =>
  [
    ...new Uint8Array(
      await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value)),
    ),
  ]
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");

describe("desktop and static content adapters", () => {
  it("loads the local session and sends its write token", async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(response({ token: "test-token" }))
      .mockResolvedValueOnce(response(EMPTY))
      .mockResolvedValueOnce(response({ ok: true }));
    vi.stubGlobal("fetch", fetcher);
    const c = new DataClient();
    expect(await c.init()).toEqual(EMPTY);
    expect(c.mode).toBe("desktop");
    await c.write("export", "POST", {});
    expect(fetcher.mock.calls[2][1].headers["X-Session-Token"]).toBe(
      "test-token",
    );
  });
  it("loads and verifies static content and per-round routes", async () => {
    const payload = JSON.stringify(EMPTY),
      timeline = JSON.stringify({ players: {} });
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response({}, 404))
        .mockResolvedValueOnce(
          response({
            schema_version: 1,
            content_version: "test",
            channel: "local-preview",
            files: {
              "catalog.json": await digest(payload),
              "timelines/r.json": await digest(timeline),
            },
          }),
        )
        .mockResolvedValueOnce(new Response(payload))
        .mockResolvedValueOnce(new Response(timeline)),
    );
    const c = new DataClient();
    expect(await c.init()).toEqual(EMPTY);
    expect(c.isPreview).toBe(true);
    expect(await c.timeline("r")).toEqual({ players: {} });
    await expect(c.write("export", "POST", {})).rejects.toThrow("仅在桌面端");
  });
  it("rejects corrupted exports and missing checksums", async () => {
    const c = new DataClient();
    c.files = { "catalog.json": "wrong" };
    vi.stubGlobal("fetch", vi.fn().mockImplementation(()=>Promise.resolve(response(EMPTY))));
    await expect(c.catalog()).rejects.toThrow("校验失败");
    c.files = {};
    await expect(c.catalog()).rejects.toThrow("缺少文件校验");
  });
  it("reports missing or incompatible publication manifests", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, 404)));
    await expect(new DataClient().init()).rejects.toThrow("尚未加载内容包");
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce(response({}, 404))
        .mockResolvedValueOnce(response({ schema_version: 9 })),
    );
    await expect(new DataClient().init()).rejects.toThrow("版本暂不受支持");
  });
  it("reports query and media failures rather than returning false empty data", async () => {
    const c = new DataClient();
    c.mode = "desktop";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, 404)));
    await expect(c.catalog()).rejects.toThrow("读取学习资料失败");
    await expect(c.timeline("r")).rejects.toThrow("尚无可用路线");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ schema_version: 99 })),
    );
    await expect(c.catalog()).rejects.toThrow("格式不兼容");
  });
  it("preserves useful validation errors and handles media form submissions", async () => {
    const c = new DataClient();
    c.mode = "desktop";
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({ detail: { gaps: ["pro_video", "aim"] } }, 422),
        ),
    );
    await expect(c.saveTeaching("t", { status: "published" })).rejects.toThrow(
      "职业比赛原片",
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ detail: "Specific message" }, 422)),
    );
    await expect(c.write("media", "POST", new FormData())).rejects.toThrow(
      "Specific message",
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ detail: [] }, 422)),
    );
    await expect(c.write("media", "POST", new FormData())).rejects.toThrow(
      "检查输入",
    );
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(response({ url: "media/a.png" })),
    );
    expect(await c.write("media", "POST", new FormData())).toEqual({
      url: "media/a.png",
    });
  });
});

describe("filter combinations and unknown outcomes", () => {
  const c = {
    schema_version: 1,
    matches: [
      {
        id: "m",
        map: "de_test",
        source: { verified: true, date: "2025-01-01" },
      },
    ],
    throws: [
      {
        id: "t",
        match_id: "m",
        map: "de_test",
        side: "T",
        kind: "flash",
        player: "A",
        team: "Team",
        teaching: { area: "Mid" },
        gaps: [],
      },
    ],
    rounds: [
      {
        id: "r",
        match_id: "m",
        number: 1,
        is_pistol: true,
        complete: true,
        winner: "T",
        review: { description: "Mid control" },
        equipment: [{ side: "T", player: "A", team: "Team" }],
      },
    ],
    plans: [],
  } as unknown as Catalog;
  it("applies map, date, team, player, teaching-state and purpose filters together", () => {
    expect(
      filterThrows(c, {
        map: "de_test",
        match: "m",
        side: "T",
        kind: "flash",
        player: "A",
        team: "Team",
        status: "complete",
        dateFrom: "2024-01-01",
        dateTo: "2025-12-01",
        query: "mid",
      }),
    ).toHaveLength(1);
    for (const f of [
      { dateFrom: "2026-01-01" },
      { dateTo: "2024-01-01" },
      { team: "Other" },
      { player: "Other" },
      { map: "de_other" },
      { match: "other" },
      { kind: "smoke" },
      { status: "pending" },
    ])
      expect(filterThrows(c, f)).toHaveLength(0);
  });
  it("counts losing and winning views without discarding failed examples", () => {
    expect(
      visibleRounds(c, { side: "T", result: "win", query: "control" }, true),
    ).toHaveLength(1);
    expect(visibleRounds(c, { side: "T", result: "loss" }, true)).toHaveLength(
      0,
    );
    expect(
      visibleRounds(c, { result: "T", team: "Team", player: "A" }, true),
    ).toHaveLength(1);
    expect(pistolSummary(c.rounds)).toMatchObject({
      wins: null,
      ctWins: 0,
      tWins: 1,
    });
    expect(
      pistolSummary([{ ...c.rounds[0], winner: null }], "T"),
    ).toMatchObject({ wins: 0, losses: 0, complete: 0 });
  });
  it("restricts media URLs even if catalog metadata is untrusted", () => {
    for (const v of [
      null,
      0,
      "x\u0000y",
      "media/../private",
      "media\\private",
      "https://user:pass@example.org/x",
      "file:///C:/bad",
    ])
      expect(mediaUrl(v, "web")).toBe("");
    expect(mediaUrl("media/a.mp4", "desktop")).toBe("/media/a.mp4");
    expect(mediaUrl("https://example.org/video", "web")).toBeTruthy();
  });
});
