"""Opening defaults: how teams play the first 30 seconds of a round, per map era.

T defaults are clustered from the area counts of all five T players at 0-30 s. A dead player
stays where he fell and a missing snapshot carries the previous one forward, so fast openings
with early deaths are not dropped. CT setups reuse the existing CT formation analysis. Each
round pairs one T default with one CT setup; the matchup table always reports counts and gives
a win rate only with enough rounds and matches. Utility is described by our own facts only;
the lineups themselves are linked to nades.ai by the frontend.
"""

import statistics
from collections import Counter, defaultdict

import numpy as np

from . import eras, stats
from .domain import effective_round
from .formations import T_SNAPSHOT_SECONDS
from .patterns import AREA_ZH, AREAS, bootstrap_stability, macro_area

OPENINGS_VERSION = 1
T_AREAS = (*AREAS, "T")
WINDOW_SECONDS = 30
# Below these a matchup or a team's default shows counts only, never a rate.
MIN_ROUNDS = 10
MIN_MATCHES = 3
AREA_NAMES = {**AREA_ZH, "T": "T 区"}
SHORT = {"A": "A", "B": "B", "Mid": "中", "CT": "CT", "other": "其他", "T": "T区"}


def _t_area(map_name, place, overrides):
    return "T" if place in ("TSpawn", "TStart") else macro_area(map_name, place, overrides)


def t_counts(formation, map_name, overrides=None):
    """T players per macro area at each snapshot second; None without a full opening snapshot."""
    snaps = {s["second"]: s for s in formation.get("t_snapshots", [])}
    start = snaps.get(T_SNAPSHOT_SECONDS[0])
    if not start or len(start["t"]) != 5:
        return None
    places, out = {}, []
    for second in T_SNAPSHOT_SECONDS:
        for player in (snaps.get(second) or {"t": []})["t"]:
            if player.get("place"):
                places[player["player_id"]] = player["place"]
        c = Counter(_t_area(map_name, place, overrides) for place in places.values())
        out.append({a: c.get(a, 0) for a in T_AREAS})
    return out


def _setup(counts):
    return " · ".join(
        f"{SHORT[a]}{counts[a]}" for a in ("A", "Mid", "B", "CT", "T", "other") if counts.get(a)
    )


def _name(patterns):
    """Unique readable names from the area most over-represented at 20 s versus the average."""
    total = sum(p["rounds"] for p in patterns)
    mean = {a: sum(p["shares"][20][a] * p["rounds"] for p in patterns) / total for a in ("A", "B", "Mid")}
    for p in patterns:
        lift = {a: p["shares"][20][a] - mean[a] for a in mean}
        area = max(lift, key=lift.get)
        setup = p["setups"][0]["setup"] if p["setups"] else ""
        p["name"] = f"{AREA_NAMES[area]}主攻 · {setup}" if lift[area] > 0.04 else f"均衡展开 · {setup}"
        p["name_source"] = "规则草拟（20 秒时人数最多高于平均的区域），待人工确认"
    seen = Counter(p["name"] for p in patterns)
    for p in patterns:
        if seen[p["name"]] > 1:
            p["name"] = f"{p['name']}（{p['id'] + 1}）"


def cluster_t(map_name, formations, throws, overrides=None, *, min_cluster=3, max_k=8):
    usable, counts = [], []
    for f in formations:
        c = t_counts(f, map_name, overrides)
        if c is not None:
            usable.append(f)
            counts.append(c)
    n = len(usable)
    result = {
        "map": map_name,
        "side": "T",
        "method": "t-opening-count-clustering",
        "snapshot_seconds": list(T_SNAPSHOT_SECONDS),
        "rounds": n,
        "excluded_rounds": len(formations) - n,
        "patterns": [],
        "assignments": {},
        "warnings": [],
    }
    if n < 2 * min_cluster:
        result["warnings"].append("样本太少，无法区分 T 方默认打法。")
        return result
    x = np.array([[c[a] for c in rows for a in T_AREAS] for rows in counts], dtype=float)
    # Like the CT analysis: at least 4 candidates when the data allow, so defaults are teachable.
    min_size = max(min_cluster, int(0.03 * n))
    upper = max(2, min(max_k, n // min_size))
    best, _ = stats.select_k(x, range(min(4, upper), upper + 1), min_size=min_size)
    if best is None:
        result["warnings"].append("展开分布不足以区分多个默认打法。")
        return result
    labels, k = best["labels"], best["k"]
    result["k"] = k
    result["stability_ari"] = bootstrap_stability(x, k)
    early = defaultdict(list)
    for t in throws:
        if t.get("side") == "T" and (t.get("time") if t.get("time") is not None else 999) <= WINDOW_SECONDS:
            early[t["round_id"]].append(t)
    at20 = T_SNAPSHOT_SECONDS.index(20)
    for c in range(k):
        idx = np.where(labels == c)[0]
        if not len(idx):  # k-means can leave a cluster empty on tiny buckets
            continue
        members = [usable[i] for i in idx]
        centre = x[idx].mean(0)
        rep = members[int(((x[idx] - centre) ** 2).sum(1).argmin())]
        decided = [f for f in members if f.get("winner") in ("CT", "T")]
        wins = sum(f["winner"] == "T" for f in decided)
        timing = defaultdict(list)
        for f in members:
            for t in early[f["round_id"]]:
                timing[(t["kind"], t.get("effect_area") or "未知")].append(float(t["time"]))
        result["patterns"].append(
            {
                "id": c,
                "rounds": len(members),
                "decided": len(decided),
                "t_wins": wins,
                "t_win_rate": round(wins / len(decided), 3) if decided else None,
                "shares": {
                    second: {a: round(sum(counts[i][j][a] for i in idx) / (5 * len(idx)), 3) for a in T_AREAS}
                    for j, second in enumerate(T_SNAPSHOT_SECONDS)
                },
                "setups": [
                    {"setup": s, "rounds": v}
                    for s, v in Counter(_setup(counts[i][at20]) for i in idx).most_common(3)
                ],
                "utility_timing": [
                    {"kind": kind, "area": area, "count": len(v), "median": round(statistics.median(v), 2)}
                    for (kind, area), v in sorted(timing.items(), key=lambda kv: (-len(kv[1]), kv[0]))
                ],
                "representative": rep["round_id"],
                "round_ids": [f["round_id"] for f in members],
            }
        )
        result["assignments"].update({f["round_id"]: c for f in members})
    _name(result["patterns"])
    return result


def first_contact(row, tick_rate):
    """The first damage between the two sides: when (seconds after freeze end), where, by whom."""
    for e in sorted(row.get("learning_events") or [], key=lambda e: e.get("tick", 0)):
        a, v = e.get("attacker_side"), e.get("victim_side")
        if e.get("kind") == "hurt" and a and v and a != v:
            second = round((e["tick"] - row.get("freeze_end_tick", 0)) / tick_rate, 2)
            return {"second": second, "place": e.get("victim_place"), "by": a}
    return None


def _rate_interval(rows, side):
    """Match-block bootstrap of the side's win rate over decided rounds."""
    blocks = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["winner"] in ("CT", "T"):
            block = blocks[r["match_id"]]
            block[0] += r["winner"] == side
            block[1] += 1
    values = np.array([v for v in blocks.values() if v[1]])
    if len(values) < 2:
        return None
    draws = np.random.default_rng(7).integers(0, len(values), size=(400, len(values)))
    sums = values[draws].sum(axis=1)
    return [round(float(q), 3) for q in np.quantile(sums[:, 0] / sums[:, 1], [0.025, 0.975])]


def _gated(rows, side, min_rounds, min_matches):
    decided = [r for r in rows if r["winner"] in ("CT", "T")]
    wins = sum(r["winner"] == side for r in decided)
    matches = len({r["match_id"] for r in rows})
    enough = len(rows) >= min_rounds and matches >= min_matches and decided
    return {
        "rounds": len(rows),
        "matches": matches,
        "decided": len(decided),
        "wins": wins,
        "status": "ok" if enough else "insufficient",
        "win_rate": round(wins / len(decided), 3) if enough else None,
        "interval": _rate_interval(rows, side) if enough else None,
    }


def matchup_table(rows, *, min_rounds=MIN_ROUNDS, min_matches=MIN_MATCHES):
    cells = defaultdict(list)
    for r in rows:
        cells[(r["t_label"], r["ct_label"])].append(r)
    out = []
    for (t_label, ct_label), members in cells.items():
        gated = _gated(members, "T", min_rounds, min_matches)
        contacts = [r["contact"] for r in members if r.get("contact")]
        place = Counter(c["place"] for c in contacts).most_common(1)
        out.append(
            {
                "t": t_label,
                "ct": ct_label,
                "rounds": gated["rounds"],
                "matches": gated["matches"],
                "decided": gated["decided"],
                "t_wins": gated["wins"],
                "status": gated["status"],
                "t_win_rate": gated["win_rate"],
                "interval": gated["interval"],
                "plants": dict(Counter(r.get("plant") or "none" for r in members)),
                "contact": {
                    "place": place[0][0],
                    "share": round(place[0][1] / len(contacts), 3),
                    "median_second": round(statistics.median(c["second"] for c in contacts), 2),
                }
                if contacts
                else None,
            }
        )
    return sorted(out, key=lambda c: (-c["rounds"], str(c["t"]), str(c["ct"])))


def _side_scout(rows, side, label_key, team_key, opponent_key, min_rounds, min_matches):
    by_label = defaultdict(list)
    for r in rows:
        by_label[r[label_key]].append(r)
    defaults = []
    for label, members in sorted(by_label.items(), key=lambda kv: (-len(kv[1]), str(kv[0]))):
        examples, seen = [], set()
        for r in sorted(members, key=lambda r: (r["date"], r["round_id"]), reverse=True):
            if r["match_id"] not in seen and len(examples) < 3:
                seen.add(r["match_id"])
                examples.append(r["round_id"])
        defaults.append(
            {"label": label, **_gated(members, side, min_rounds, min_matches), "examples": examples}
        )
    return {
        "rounds": len(rows),
        "matches": len({r["match_id"] for r in rows}),
        "defaults": defaults,
        "opponents": dict(Counter(r[opponent_key] for r in rows)),
        "by_month": {
            month: dict(Counter(r[label_key] for r in rows if r["date"][:7] == month))
            for month in sorted({r["date"][:7] for r in rows})
        },
    }


def team_scout(rows, team, *, min_rounds=MIN_ROUNDS, min_matches=MIN_MATCHES):
    return {
        "T": _side_scout(
            [r for r in rows if r["t_team"] == team],
            "T",
            "t_label",
            "t_team",
            "ct_team",
            min_rounds,
            min_matches,
        ),
        "CT": _side_scout(
            [r for r in rows if r["ct_team"] == team],
            "CT",
            "ct_label",
            "ct_team",
            "t_team",
            min_rounds,
            min_matches,
        ),
    }


def build(
    map_name,
    matches,
    ct_analysis,
    *,
    reviews=None,
    overrides=None,
    min_cluster=3,
    max_k=8,
    min_rounds=MIN_ROUNDS,
    min_matches=MIN_MATCHES,
):
    """Openings per map era (or exact patch outside every era), from source-verified rounds only."""
    reviews = reviews or {}
    ct_assign = (ct_analysis or {}).get("assignments", {})
    ct_names = {p["id"]: p.get("name") for p in (ct_analysis or {}).get("patterns", [])}
    buckets = {}
    for match in matches:
        if match.get("map") != map_name or not match["source"].get("verified"):
            continue
        date, version = match["source"].get("date", ""), match.get("game_version")
        era = eras.era_for(map_name, date, version)
        key = era["id"] if era else f"{map_name}:patch:{version or 'unknown'}"
        bucket = buckets.setdefault(
            key, {"era": era, "version": version, "formations": [], "rows": [], "throws": []}
        )
        formations = match.get("formations") or {}
        kept = set()
        for original in match["rounds"]:
            row = effective_round(original, reviews.get(original["id"], {}))
            f = formations.get(row["id"])
            if row.get("excluded") or row.get("review_required") or not row.get("complete") or not f:
                continue
            if not f.get("complete", True):
                continue
            kept.add(row["id"])
            bucket["formations"].append(f)
            bucket["rows"].append(
                {
                    "round_id": row["id"],
                    "match_id": match["id"],
                    "version": str(version),
                    "date": date,
                    "winner": row.get("winner"),
                    "t_team": f.get("t_team"),
                    "ct_team": f.get("ct_team"),
                    "plant": (f.get("context") or {}).get("plant_site"),
                    "contact": first_contact(row, match.get("tick_rate") or 64),
                    "ct_label": ct_assign.get(row["id"]),
                }
            )
        for t in match.get("throws", []):
            if t.get("round_id") in kept:
                area = _t_area(map_name, t.get("effect_place"), overrides)
                bucket["throws"].append({**t, "effect_area": AREA_NAMES.get(area, area)})
    out = []
    for key, b in sorted(buckets.items(), key=lambda kv: (kv[1]["era"] is None, kv[0])):
        if not b["rows"]:
            continue
        t = cluster_t(map_name, b["formations"], b["throws"], overrides, min_cluster=min_cluster, max_k=max_k)
        for r in b["rows"]:
            r["t_label"] = t["assignments"].get(r["round_id"])
        patches = defaultdict(lambda: (set(), set()))
        for r in b["rows"]:
            patches[r["version"]][0].add(r["round_id"])
            patches[r["version"]][1].add(r["match_id"])
        ct_counts = Counter(r["ct_label"] for r in b["rows"])
        teams = sorted({r["t_team"] for r in b["rows"]} | {r["ct_team"] for r in b["rows"]} - {None})
        out.append(
            {
                "id": key,
                "era": b["era"],
                "label": b["era"]["label"] if b["era"] else f"版本 {b['version']}",
                "rounds": len(b["rows"]),
                "matches": len({r["match_id"] for r in b["rows"]}),
                "patches": {
                    v: {"rounds": len(r), "matches": len(m)} for v, (r, m) in sorted(patches.items())
                },
                "t": t,
                "ct": {
                    "patterns": [
                        {"id": label, "name": ct_names.get(label), "rounds": count}
                        for label, count in ct_counts.most_common()
                        if label is not None
                    ],
                    "unlabelled": ct_counts.get(None, 0),
                },
                "matchups": matchup_table(b["rows"], min_rounds=min_rounds, min_matches=min_matches),
                "teams": {
                    team: team_scout(b["rows"], team, min_rounds=min_rounds, min_matches=min_matches)
                    for team in teams
                },
            }
        )
    return {"schema_version": 1, "map": map_name, "version": OPENINGS_VERSION, "buckets": out}
