import type {
  Catalog,
  Filters,
  MapSlice,
  Misthrow,
  Mode,
  Round,
  Teaching,
  Throw,
  Timeline,
  Variant,
} from "./types";

export const EMPTY: Catalog = {
  schema_version: 1,
  matches: [],
  rounds: [],
  throws: [],
  plans: [],
  variants: [],
  places: {},
};
export const kindNames: Record<string, string> = {
  smoke: "烟雾弹",
  flash: "闪光弹",
  molotov: "燃烧瓶",
  incendiary: "燃烧弹",
  he: "高爆手雷",
  decoy: "诱饵弹",
};
export const teachingLabels: Record<string, string> = {
  title: "教学名称",
  area: "目标区域",
  purpose: "战术用途",
  prerequisites: "装备、出生位与前置条件",
  stance: "站位步骤",
  aim: "瞄点说明",
  operation: "按键与投掷动作",
  timing: "出手时机",
  effect: "落点与预期效果",
  coordination: "队友配合与后续行动",
  failures: "常见失败与修正",
  counterplay: "对手反制与应对",
  stance_image: "站位图",
  aim_image: "瞄点图",
  pro_video: "职业比赛原片",
  recreation_video: "教学复现视频",
  verified_by: "复现核验人",
  verified_on: "核验日期",
  map_version: "验证的游戏 / 地图版本",
  reproduction: "游戏内复现",
  misthrow: "先恢复失误标记",
};

/** Full rows carry the state; exported round events only a marker. */
export function isMisthrow(t: { misthrow?: Misthrow | boolean }) {
  return typeof t.misthrow === "object"
    ? t.misthrow.flagged
    : Boolean(t.misthrow);
}

export function misthrowReason(m: Misthrow) {
  const auto = !m.auto
    ? ""
    : m.auto.rule === "bounce_back"
      ? `落点离出手点只有 ${m.auto.distance} 单位（撞墙弹回或掉在脚下）`
      : `与同一出手点、同一瞄点的成熟投法相比，落点偏离 ${m.auto.distance} 单位`;
  if (m.source === "auto") return `自动判定：${auto}`;
  const decided = m.flagged ? "人工标为失误" : "人工确认不是失误";
  return [decided, m.note, auto && `自动规则：${auto}`]
    .filter(Boolean)
    .join(" · ");
}

function matchIds(c: Catalog, f: Filters) {
  return new Set(
    c.matches
      .filter(
        (m) =>
          (!f.map || m.map === f.map) &&
          (!f.match || m.id === f.match) &&
          (!f.dateFrom || m.source.date >= f.dateFrom) &&
          (!f.dateTo || m.source.date <= f.dateTo),
      )
      .map((m) => m.id),
  );
}

export function filterThrows(c: Catalog, f: Filters) {
  const ids = matchIds(c, f);
  const q = f.query?.trim().toLowerCase() || "";
  return c.throws.filter(
    (t) =>
      ids.has(t.match_id) &&
      (!f.side || t.side === f.side) &&
      (!f.kind || t.kind === f.kind) &&
      (!f.player || t.player === f.player) &&
      (!f.team || t.team === f.team) &&
      (!f.area ||
        t.origin_area === f.area ||
        t.effect_area === f.area ||
        t.teaching.area === f.area) &&
      // Misthrows only show when asked for; the other statuses never include them.
      (f.status === "misthrow"
        ? isMisthrow(t)
        : !isMisthrow(t) &&
          (!f.status ||
            (f.status === "complete"
              ? t.gaps.length === 0
              : t.gaps.length > 0))) &&
      (!q ||
        [
          t.player,
          t.team,
          t.map,
          kindNames[t.kind],
          t.origin_area,
          t.effect_area,
          t.origin_place,
          t.effect_place,
          ...Object.values(t.teaching),
        ]
          .join(" ")
          .toLowerCase()
          .includes(q)),
  );
}

export function visibleRounds(c: Catalog, f: Filters, pistolOnly: boolean) {
  const verified = new Set(
    c.matches.filter((m) => m.source.verified).map((m) => m.id),
  );
  const ids = matchIds(c, f);
  const q = f.query?.toLowerCase().trim() || "";
  return c.rounds.filter(
    (r) =>
      ids.has(r.match_id) &&
      verified.has(r.match_id) &&
      !r.excluded &&
      (!pistolOnly || r.is_pistol) &&
      (!f.result ||
        (f.side
          ? f.result === "win"
            ? r.winner === f.side
            : r.winner !== f.side
          : r.winner === f.result)) &&
      r.equipment.some(
        (e) =>
          (!f.side || e.side === f.side) &&
          (!f.player || e.player === f.player) &&
          (!f.team || e.team === f.team),
      ) &&
      (!q ||
        [
          String(r.number),
          r.review?.description,
          ...r.equipment.map((e) => `${e.player} ${e.team}`),
        ]
          .join(" ")
          .toLowerCase()
          .includes(q)),
  );
}

export function areaOptions(c: Catalog, map?: string) {
  const names = new Set<string>();
  for (const t of c.throws)
    if ((!map || t.map === map) && !isMisthrow(t))
      for (const value of [t.origin_area, t.effect_area, t.teaching.area])
        if (typeof value === "string" && value) names.add(value);
  return [...names].sort();
}

export function variantPeers(
  c: Catalog,
  row: Throw,
): { variant: Variant | undefined; others: Throw[] } {
  const variant = c.variants?.find((v) => v.id === row.variant_id);
  if (!variant) return { variant, others: [] };
  const members = new Set(variant.members);
  const others = c.throws.filter((t) => t.id !== row.id && members.has(t.id));
  return { variant, others };
}

/** Replace one map's throws, rounds, variants and CT analysis; other maps stay as they are. */
export function mergeSlice(c: Catalog, s: MapSlice): Catalog {
  const order = new Map(c.matches.map((m, i) => [m.id, i]));
  const rounds = new Map(s.rounds.map((r) => [r.id, r]));
  const ct = { ...(c.ct_patterns || {}) };
  delete ct[s.map];
  return {
    ...c,
    throws: [...c.throws.filter((t) => t.map !== s.map), ...s.throws].sort(
      (a, b) => (order.get(a.match_id) ?? 0) - (order.get(b.match_id) ?? 0),
    ),
    rounds: c.rounds.map((r) => rounds.get(r.id) || r),
    // Ordered by map, so the result does not depend on which map loaded first.
    variants: [
      ...(c.variants || []).filter((v) => v.map !== s.map),
      ...s.variants,
    ].sort((a, b) => (a.map < b.map ? -1 : a.map > b.map ? 1 : 0)),
    ct_patterns: { ...ct, ...s.ct_patterns },
    loaded: [...new Set([...(c.loaded || []), s.map])],
  };
}

/** A loaded map taken back out of the catalog, to keep it across a summary refresh. */
export function sliceOf(c: Catalog, map: string): MapSlice {
  const ids = new Set(c.matches.filter((m) => m.map === map).map((m) => m.id));
  const ct = c.ct_patterns?.[map];
  return {
    map,
    throws: c.throws.filter((t) => t.map === map),
    rounds: c.rounds.filter((r) => ids.has(r.match_id)),
    variants: (c.variants || []).filter((v) => v.map === map),
    ct_patterns: ct ? { [map]: ct } : {},
  };
}

export function mapOfThrow(c: Catalog, id: string) {
  const matchId = id.split("-t")[0];
  return c.matches.find((m) => m.id === matchId)?.map;
}

export function trajectoryPoints(
  t: Pick<Throw, "trajectory" | "trajectory_preview">,
) {
  return t.trajectory || t.trajectory_preview || [];
}

export function pistolSummary(rounds: Round[], side?: string) {
  const complete = rounds.filter((r) => r.complete && r.winner);
  const wins = side ? complete.filter((r) => r.winner === side).length : null;
  return {
    samples: rounds.length,
    complete: complete.length,
    wins,
    losses: wins === null ? null : complete.length - wins,
    ctWins: complete.filter((r) => r.winner === "CT").length,
    tWins: complete.filter((r) => r.winner === "T").length,
  };
}

export function mediaUrl(value: unknown, mode: Mode) {
  if (
    typeof value !== "string" ||
    value.includes("\\") ||
    [...value].some((c) => c.charCodeAt(0) < 32)
  )
    return "";
  if (/^media\/[a-zA-Z0-9_.-]+$/.test(value) && !value.includes(".."))
    return mode === "web" ? `./content/${value}` : `/${value}`;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password
      ? url.href
      : "";
  } catch {
    return "";
  }
}

export class DataClient {
  mode: Mode = "web";
  token = "";
  version = "";
  isPreview = false;
  files: Record<string, string> = {};
  async init() {
    if (import.meta.env.VITE_PUBLIC_MODE !== "static") {
      const response = await fetch("/api/session");
      if (
        response.ok &&
        response.headers.get("content-type")?.includes("application/json")
      ) {
        const session = await response.json();
        this.mode = "desktop";
        this.token = session.token;
        return this.summary();
      }
    }
    this.mode = "web";
    const response = await fetch("./content/manifest.json");
    if (!response.ok)
      throw new Error(
        "尚未加载内容包。请将桌面端导出的已审核内容放入 content 目录。",
      );
    const manifest = await response.json();
    if (manifest.schema_version !== 1)
      throw new Error("此内容包版本暂不受支持，请更新应用。");
    this.version = manifest.content_version;
    this.isPreview = manifest.channel === "local-preview";
    this.files = manifest.files || {};
    return this.catalog();
  }
  async catalog(): Promise<Catalog> {
    const response = await fetch(
      this.mode === "desktop" ? "/api/catalog" : "./content/catalog.json",
    );
    if (!response.ok)
      throw new Error("读取学习资料失败，请检查本地服务或内容包。");
    const bytes = await response.arrayBuffer();
    await this.verify("catalog.json", bytes);
    const data = JSON.parse(new TextDecoder().decode(bytes));
    if (data.schema_version !== 1) throw new Error("内容格式不兼容。");
    return data;
  }
  /** Desktop studio: everything but throws, variants and formations. */
  async summary(): Promise<Catalog> {
    const response = await fetch("/api/catalog/summary");
    if (!response.ok)
      throw new Error("读取学习资料失败，请检查本地服务或内容包。");
    const data = await response.json();
    if (data.schema_version !== 1) throw new Error("内容格式不兼容。");
    return data;
  }
  async loadMap(map: string): Promise<MapSlice> {
    const response = await fetch(
      `/api/catalog/maps/${encodeURIComponent(map)}`,
    );
    if (!response.ok) throw new Error(`读取地图 ${map} 的资料失败。`);
    return response.json();
  }
  /** The full row with its trajectory; the static site already has it. */
  async throwDetail(id: string): Promise<Throw | null> {
    if (this.mode !== "desktop") return null;
    const response = await fetch(`/api/throws/${encodeURIComponent(id)}`);
    if (!response.ok) throw new Error("读取投掷详情失败。");
    return response.json();
  }
  async timeline(id: string): Promise<Timeline> {
    const path =
      this.mode === "desktop"
        ? `/api/timelines/${encodeURIComponent(id)}`
        : `./content/timelines/${encodeURIComponent(id)}.json`;
    const response = await fetch(path);
    if (!response.ok) throw new Error("此回合尚无可用路线数据。");
    const bytes = await response.arrayBuffer();
    await this.verify(`timelines/${id}.json`, bytes);
    return JSON.parse(new TextDecoder().decode(bytes));
  }
  async verify(name: string, bytes: ArrayBuffer) {
    if (this.mode !== "web") return;
    if (!this.files[name])
      throw new Error("内容包缺少文件校验信息，请重新导出。");
    const digest = await crypto.subtle.digest("SHA-256", bytes);
    const actual = [...new Uint8Array(digest)]
      .map((x) => x.toString(16).padStart(2, "0"))
      .join("");
    if (actual !== this.files[name])
      throw new Error("内容包校验失败，请重新导出或部署。");
  }
  async write(path: string, method: string, body: unknown) {
    if (this.mode !== "desktop") throw new Error("内容整理仅在桌面端提供。");
    const form = body instanceof FormData;
    const response = await fetch(`/api/${path}`, {
      method,
      headers: {
        "X-Session-Token": this.token,
        ...(!form ? { "Content-Type": "application/json" } : {}),
      },
      body: form ? body : JSON.stringify(body),
    });
    const result = await response.json();
    if (!response.ok) {
      if (result.detail?.gaps)
        throw new Error(
          `暂不能发布，还需要：${result.detail.gaps.map((k: string) => teachingLabels[k] || k).join("、")}`,
        );
      throw new Error(
        typeof result.detail === "string" ? result.detail : "请检查输入内容。",
      );
    }
    return result;
  }
  saveTeaching(id: string, t: Teaching) {
    return this.write(`teachings/${id}`, "PUT", t);
  }
}
