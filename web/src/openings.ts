// Opening defaults (first 30 s): T defaults x CT setups per map era. Utility is shown as our own
// facts plus a link to nades.ai's map-level page; lineups themselves live there.

export type Gated = {
  status: "ok" | "insufficient";
  rounds: number;
  matches: number;
  rate: number | null;
  interval: number[] | null;
};
export type TDefault = {
  id: number;
  name: string;
  rounds: number;
  matches: number;
  decided: number;
  t_wins: number;
  status: "ok" | "insufficient";
  t_win_rate: number | null;
  shares: Record<string, Record<string, number>>;
  setups: { setup: string; rounds: number }[];
  utility_timing: {
    kind: string;
    area: string;
    count: number;
    median: number;
  }[];
  representative: string;
};
export type Matchup = {
  t: number | null;
  ct: number | null;
  rounds: number;
  matches: number;
  decided: number;
  t_wins: number;
  status: "ok" | "insufficient";
  t_win_rate: number | null;
  interval: number[] | null;
  plants: Record<string, number>;
  contact: { place: string; share: number; median_second: number } | null;
};
export type ScoutDefault = {
  label: number | null;
  rounds: number;
  matches: number;
  decided: number;
  wins: number;
  status: "ok" | "insufficient";
  win_rate: number | null;
  interval: number[] | null;
  examples: string[];
};
export type SideScout = {
  rounds: number;
  matches: number;
  defaults: ScoutDefault[];
  opponents: Record<string, number>;
  by_month: Record<string, Record<string, number>>;
};
export type OpeningBucket = {
  id: string;
  era: { id: string; label: string } | null;
  label: string;
  rounds: number;
  matches: number;
  patches: Record<string, { rounds: number; matches: number }>;
  t: {
    patterns: TDefault[];
    warnings: string[];
    stability_ari?: number | null;
  };
  ct: {
    patterns: { id: number; name: string | null; rounds: number }[];
    unlabelled: number;
  };
  matchups: Matchup[];
  teams: Record<string, { T: SideScout; CT: SideScout }>;
};
export type Openings = {
  schema_version: number;
  map: string;
  version: number;
  buckets: OpeningBucket[];
};

// Checked by hand on 2026-11-15: these pages exist on nades.ai. Never build lineup-level URLs
// from our place names; their naming differs and a guess would be a broken link.
const NADES_MAPS: Record<string, string> = {
  de_mirage: "mirage",
  de_ancient: "ancient",
  de_dust2: "dust2",
  de_inferno: "inferno",
  de_nuke: "nuke",
  de_anubis: "anubis",
  de_cache: "cache",
};
const NADES_KINDS: Record<string, string> = {
  smoke: "smokes",
  flash: "flashbangs",
  he: "he-grenades",
  molotov: "molotovs",
  incendiary: "molotovs",
};

export function nadesLink(map: string, kind: string): string | null {
  const m = NADES_MAPS[map];
  const k = NADES_KINDS[kind];
  return m && k ? `https://nades.ai/zh/${m}/${k}` : null;
}

const pct = (n: number) => `${Math.round(n * 100)}%`;

export function rateText(g: Gated): string {
  const size = `${g.rounds} 回合 / ${g.matches} 场`;
  if (g.status !== "ok" || g.rate === null) return `样本不足 · ${size}`;
  const range = g.interval
    ? `（${pct(g.interval[0])}–${pct(g.interval[1])}）`
    : "";
  return `${pct(g.rate)}${range}· ${size}`;
}
