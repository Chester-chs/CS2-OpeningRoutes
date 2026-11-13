import { isMisthrow, kindNames } from "./data";
import type { Plan, Side, Throw } from "./types";

export type LearningSelection = {
  kind?: string;
  subject?: string;
  map?: string;
  side?: Side;
  area?: string;
  profile?: string;
  pistol?: boolean;
};
export type LearningCounts = {
  rounds: number;
  matches: number;
  players: number;
  pistols: number;
};
export type Habit = {
  label: string;
  rounds: number;
  share: number;
  interval: [number, number] | null;
};
export type LearningStats = {
  counts: LearningCounts;
  confidence: { status: "exploratory" | "descriptive"; method: string };
  habits: Habit[];
  routes: Habit[];
  sequences: Habit[];
  utility_timing: {
    kind: string;
    count: number;
    median: number;
    p25: number;
    p75: number;
  }[];
  wins: number;
  missing_fraction: number;
};
export type ProfileSummary = {
  id: string;
  kind: "player" | "team" | "role";
  subject_id: string;
  name: string;
  aliases: string[];
  map: string;
  // The map era id when games are pooled across patches, otherwise the exact patch.
  version: string;
  era?: MapEra | null;
  patches?: Record<string, { rounds: number; matches: number }>;
  side: Side;
  area: string;
  area_label: string;
  team: string;
  members: string[];
  counts: LearningCounts;
  confidence: LearningStats["confidence"];
  date_from: string;
  date_to: string;
};
export type MapEra = { id: string; label: string; from: string; to: string };
export type ObservedUtility = {
  id: string;
  tick: number;
  time: number;
  kind: string;
  side: Side;
  player_id: string;
  player: string;
  origin_place: string | null;
  effect_place: string | null;
  effect_place_basis?: { method: string; distance: number } | null;
};
export type LearningContact = {
  tick: number;
  attacker_id: string;
  victim_id: string;
  attacker_place?: string;
  victim_place?: string;
  victim_position?: number[];
};
export type LearningSample = {
  id: string;
  round_id: string;
  match_id: string;
  number: number;
  player_ids: string[];
  team: string;
  side: Side;
  pistol: boolean;
  winner: string | null;
  economy: string;
  score: string;
  date: string;
  game_version?: string | null;
  source: { event: string; match: string; date: string; url: string };
  routes: Record<
    string,
    { place: string; start: number; end: number; position: number[] }[]
  >;
  utility: ObservedUtility[];
  opponent_utility: ObservedUtility[];
  first_contact: LearningContact | null;
  first_kill: LearningContact | null;
  control: {
    points: [number, number, number, string][];
    end_state: string;
    missing_fraction: number;
    basis: string;
  };
  practice: string[];
};
export type LearningProfile = ProfileSummary &
  LearningStats & {
    area_places: string[];
    place_labels: Record<string, string>;
    contexts: Record<string, LearningStats>;
    samples: LearningSample[];
  };
export type LearningGroup = {
  kind: "region" | "role";
  map: string;
  label: string;
  places?: string[];
  players?: string[];
  side?: Side;
  area?: string;
  team?: string;
  confirmed?: boolean;
  date_from?: string | null;
  date_to?: string | null;
};
export type LearningIndex = {
  schema_version: number;
  state: "ready" | "building" | "error" | "unavailable";
  profiles: ProfileSummary[];
  coverage: {
    library_rounds?: number;
    eligible_rounds?: number;
    analyzed_rounds?: number;
    missing_rounds?: number;
  };
  regions: Record<string, Record<string, { label: string; places: string[] }>>;
  groups: Record<string, LearningGroup>;
};
export const EMPTY_LEARNING: LearningIndex = {
  schema_version: 1,
  state: "unavailable",
  profiles: [],
  coverage: {},
  regions: {},
  groups: {},
};
export const economyNames: Record<string, string> = {
  pistol: "手枪局",
  eco: "低经济",
  half_buy: "半起",
  long_gun: "长枪",
  unknown: "装备未知",
};
export const scoreNames: Record<string, string> = {
  leading: "领先",
  tied: "平分",
  trailing: "落后",
  unknown: "比分未知",
};
export const controlNames: Record<string, string> = {
  CT: "CT 持续占位",
  T: "T 持续占位",
  contested: "双方在场",
  empty: "无人",
  transit: "短暂停留",
  unknown: "资料缺失",
};

export function periodLabel(p: Pick<ProfileSummary, "era" | "version">) {
  return p.era ? `地图时期 ${p.era.label}` : `版本 ${p.version}`;
}

/** Patches behind a pooled profile, most rounds first; old packs fall back to the version. */
export function patchSplit(
  p: Pick<ProfileSummary, "era" | "version" | "patches">,
) {
  const rows = Object.entries(p.patches || {}).sort(
    (a, b) => b[1].rounds - a[1].rounds,
  );
  if (!rows.length) return periodLabel(p);
  return `补丁 ${rows.map(([k, v]) => `${k} · ${v.rounds} 局 / ${v.matches} 场`).join("；")}`;
}

export function sampleMatchesContext(s: LearningSample, context: string) {
  if (context === "pistol") return s.pistol;
  if (context === "non_pistol") return !s.pistol;
  if (context.startsWith("economy:")) return s.economy === context.slice(8);
  if (context.startsWith("score:")) return s.score === context.slice(6);
  return true;
}

export function draftLearningPlan(
  profile: LearningProfile,
  sample: LearningSample,
  throws: Throw[],
): Plan | null {
  const ids = new Set(sample.utility.map((t) => t.id));
  const rows = throws
    .filter(
      (t) =>
        ids.has(t.id) &&
        t.round_id === sample.round_id &&
        t.side === profile.side &&
        sample.player_ids.includes(t.player_id) &&
        t.time >= 0 &&
        t.time <= 30 &&
        !isMisthrow(t),
    )
    .sort((a, b) => a.time - b.time);
  if (!rows.length) return null;
  return {
    id: crypto.randomUUID(),
    title: `${profile.name} · ${profile.map.replace("de_", "")} ${profile.side} ${profile.area_label} · R${sample.number}`,
    area: profile.area_label,
    side: profile.side,
    status: "draft",
    source_round_id: sample.round_id,
    source_players: sample.player_ids,
    learning_profile_id: profile.id,
    purpose: `比赛观察：${sample.source.match}，回合 ${sample.number}。战术目的与反制因果待人工核对。`,
    conditions: `${sample.source.date}；${sample.game_version ? `补丁 ${sample.game_version}` : periodLabel(profile)}；${economyNames[sample.economy] || sample.economy}；${scoreNames[sample.score] || sample.score}。冻结结束为 0 秒。`,
    steps: rows.map((t) => ({
      throw_id: t.id,
      role: t.player,
      time: t.time,
      followup: (sample.routes[t.player_id] || [])
        .filter((s) => s.end > t.time)
        .map((s) => `${s.start}–${s.end}s ${s.place}`)
        .join(" → "),
    })),
    counter_ids: [],
    counter_explanation: "对手同期动作可在来源回合核对；尚未确认反制关系。",
  };
}

export type Practice = {
  id: string;
  profile_id: string;
  title: string;
  round_id: string;
  map: string;
  steps: string[];
  checked: number[];
  note: string;
};
export function practiceFromSample(
  profile: LearningProfile,
  sample: LearningSample,
): Practice {
  return {
    id: `${profile.id}:${sample.round_id}`,
    profile_id: profile.id,
    title: `${profile.name} · ${profile.map.replace("de_", "")} ${profile.side} ${profile.area_label} · R${sample.number}`,
    round_id: sample.round_id,
    map: profile.map,
    steps: [
      ...sample.practice.slice(0, 1),
      ...Object.entries(sample.routes).map(
        ([pid, segments]) =>
          `${sample.utility.find((t) => t.player_id === pid)?.player || pid}：${segments.map((s) => `${s.start}–${s.end}s ${profile.place_labels?.[s.place] || s.place}`).join(" → ")}`,
      ),
      ...sample.utility.map(
        (t) =>
          `${t.time}s · ${t.player} · ${kindNames[t.kind] || t.kind}；先核对原回合，再使用已有验证教学练习`,
      ),
      ...sample.practice.slice(1),
    ],
    checked: [],
    note: "",
  };
}
export function loadPractice(): Practice[] {
  try {
    const rows = JSON.parse(localStorage.getItem("or-practice") || "[]");
    return Array.isArray(rows)
      ? rows.filter(
          (p) =>
            typeof p?.id === "string" &&
            typeof p.title === "string" &&
            typeof p.round_id === "string" &&
            Array.isArray(p.steps) &&
            p.steps.every((s: unknown) => typeof s === "string") &&
            Array.isArray(p.checked) &&
            typeof p.note === "string",
        )
      : [];
  } catch {
    return [];
  }
}
export function savePractice(entry: Practice) {
  const rows = loadPractice();
  const old = rows.find((r) => r.id === entry.id);
  localStorage.setItem(
    "or-practice",
    JSON.stringify([old || entry, ...rows.filter((r) => r.id !== entry.id)]),
  );
}
