import type { Catalog, MapSummary } from "./types";

// Home page tables: the library at a glance, newest first, no decoration.

/** "Alpha vs Beta · Mirage" -> "Alpha vs Beta" (the map is its own column). */
export function teamsOf(label: string) {
  return label.split(" · ")[0].trim();
}

// Plain code-point order: source dates are ISO "YYYY-MM-DD", and it does not depend on locale.
const byText = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
const byMatches = (a: MapSummary, b: MapSummary) =>
  b.matches - a.matches || byText(a.map, b.map);

export function mapRows(c: Catalog): MapSummary[] {
  if (c.maps?.length) return [...c.maps].sort(byMatches);
  const rows = new Map<string, MapSummary>();
  const mapOf = new Map(c.matches.map((m) => [m.id, m.map]));
  for (const m of c.matches) {
    const row = rows.get(m.map) || {
      map: m.map,
      matches: 0,
      rounds: 0,
      throws: 0,
      complete: 0,
    };
    row.matches += 1;
    rows.set(m.map, row);
  }
  for (const r of c.rounds) {
    const row = rows.get(mapOf.get(r.match_id) || "");
    if (row) row.rounds += 1;
  }
  for (const t of c.throws) {
    const row = rows.get(t.map);
    if (row) {
      row.throws += 1;
      if (t.gaps?.length === 0 && t.teaching?.status === "published")
        row.complete += 1;
    }
  }
  return [...rows.values()].sort(byMatches);
}

export function teamRows(c: Catalog) {
  const rows = new Map<
    string,
    { team: string; matches: number; latest: string }
  >();
  for (const m of c.matches) {
    // "A vs B", "A vs. B" or "A v B"; a team listed twice still played one map.
    const names = new Set(
      teamsOf(m.source.match)
        .split(/\s+(?:vs\.?|v)\s+/i)
        .map((t) => t.trim())
        .filter(Boolean),
    );
    for (const name of names) {
      const row = rows.get(name) || { team: name, matches: 0, latest: "" };
      row.matches += 1;
      if (byText(m.source.date, row.latest) > 0) row.latest = m.source.date;
      rows.set(name, row);
    }
  }
  return [...rows.values()].sort(
    (a, b) =>
      b.matches - a.matches ||
      byText(a.team.toLowerCase(), b.team.toLowerCase()),
  );
}

export function recentMatches(c: Catalog, limit = 10) {
  return [...c.matches]
    .sort((a, b) => byText(b.source.date, a.source.date) || byText(a.id, b.id))
    .slice(0, limit)
    .map((m) => ({
      id: m.id,
      date: m.source.date,
      event: m.source.event,
      teams: teamsOf(m.source.match),
      map: m.map,
      verified: Boolean(m.source.verified),
    }));
}
