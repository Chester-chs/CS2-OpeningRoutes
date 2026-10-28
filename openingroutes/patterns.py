"""CT defensive pattern analysis.

Method: TAGNet pipeline (Zhang et al., "TAGNet: Temporal Attention Graph Network
for Defensive Tactical Pattern Recognition in Professional Counter-Strike 2",
IEEE Transactions on Games, 2026, doi:10.1109/TG.2026.3745970):
five CT snapshots at 10/12/15/18/20 s, macro areas A/B/Mid/CT, K-Means with
K chosen by the mean rank of silhouette / Davies-Bouldin / Calinski-Harabasz,
rule-based draft names from the 15 s area shares, chi-square context tests with
Holm correction and team fingerprints. The round encoding is the paper's
count-based baseline (Table VII), which clustered better than the neural encoder
in the paper's own comparison and needs no deep-learning runtime.
Additions: per-player positions (roles), spot-level formations, rotation routes,
utility usage and sample-size guards for small datasets.
"""

from collections import Counter, defaultdict

import numpy as np

from . import stats
from .formations import SNAPSHOT_SECONDS

AREAS = ("A", "B", "Mid", "CT", "other")
ANALYSIS_VERSION = 1

CITATION = {
    "title": "TAGNet: Temporal Attention Graph Network for Defensive Tactical Pattern Recognition "
    "in Professional Counter-Strike 2",
    "authors": "X. Zhang, R. Zhang, G. Chen, X. Cao, C. Yue, C. Yuan",
    "venue": "IEEE Transactions on Games, 2026 (early access)",
    "doi": "10.1109/TG.2026.3745970",
    "url": "https://doi.org/10.1109/TG.2026.3745970",
    "code": "https://github.com/zhangx1ang03620/TAGNet-CS2",
}

# Dust2 is the paper's mapping. Mirage and Ancient are this project's defaults,
# derived from place positions relative to the bombsites and CT spawn; curators
# can override any place per map (``places`` table, field ``area``).
DEFAULT_MACRO = {
    "de_dust2": {
        **dict.fromkeys(
            [
                "BombsiteA",
                "ARamp",
                "LongA",
                "LongDoors",
                "ExtendedA",
                "Catwalk",
                "ShortStairs",
                "Pit",
                "OutsideLong",
                "UnderA",
            ],
            "A",
        ),
        **dict.fromkeys(
            ["BombsiteB", "BDoors", "LowerTunnel", "UpperTunnel", "OutsideTunnel", "TunnelStairs"], "B"
        ),
        **dict.fromkeys(["MidDoors", "Middle", "TopofMid", "TopMid", "Suicide", "Xbox", "Hole"], "Mid"),
        **dict.fromkeys(["CTSpawn", "Side"], "CT"),
    },
    "de_mirage": {
        **dict.fromkeys(
            [
                "BombsiteA",
                "Stairs",
                "Jungle",
                "PalaceInterior",
                "PalaceAlley",
                "Scaffolding",
                "TRamp",
                "TicketBooth",
                "Tetris",
                "ARamp",
            ],
            "A",
        ),
        **dict.fromkeys(
            ["BombsiteB", "Apartments", "Truck", "Shop", "Market", "Kitchen", "BackAlley", "House"], "B"
        ),
        **dict.fromkeys(
            ["SnipersNest", "Catwalk", "Connector", "Underpass", "Middle", "TopofMid", "Ladder", "SideAlley"],
            "Mid",
        ),
        **dict.fromkeys(["CTSpawn"], "CT"),
    },
    "de_ancient": {
        **dict.fromkeys(["BombsiteA", "SideHall", "MainHall", "Outside"], "A"),
        **dict.fromkeys(["BombsiteB", "Alley", "SideEntrance", "Ramp", "Ruins"], "B"),
        **dict.fromkeys(["Middle", "TopofMid", "TSideUpper", "TSideLower", "Water"], "Mid"),
        **dict.fromkeys(["CTSpawn", "House"], "CT"),
    },
}

NAMES = {
    "mid": ("中路控制·两点均衡", "Mid-Control Balanced", "15 秒时中路人数占比高，A、B 两点人数接近。"),
    "a_push": ("A 区重兵前压", "Aggressive A-Heavy Push", "A 区占比明显最高、B 区很少，常见于前压或叠 A。"),
    "a_anchor": ("A 偏重·双点留人", "Anchor-A Biased", "两点都有人守，A 区人数占多数。"),
    "b_double": ("B 偏重·双点", "B-Biased Double-Point", "A、B 人数接近，B 略多。"),
    "a_mid": ("A 区+中路", "A-Long+Mid", "A 区为主，同时保留中路控制。"),
    "retreat": ("后撤回防", "Retreat-and-Rotate", "CT 出生点附近人数多，偏保守、准备回防。"),
    "default": ("均衡默认站位", "Default Balanced", "人数分布均匀。"),
}


def macro_area(map_name: str, place: str | None, overrides: dict | None = None) -> str:
    if not place:
        return "other"
    custom = (overrides or {}).get(map_name, {}).get(place)
    if custom in AREAS:
        return custom
    return DEFAULT_MACRO.get(map_name, {}).get(place, "other")


def draft_name(shares: dict) -> tuple[str, str, str]:
    """TAGNet ``infer_tactical_name`` thresholds on the 15 s area shares."""
    a, b, mid, ct = (shares.get(x, 0.0) for x in ("A", "B", "Mid", "CT"))
    if mid >= 0.28 and abs(a - b) <= 0.08:
        key = "mid"
    elif a >= 0.68 and b <= 0.18:
        key = "a_push"
    elif a >= 0.56 and b >= 0.33:
        key = "a_anchor"
    elif b >= 0.40 and a >= 0.38:
        key = "b_double"
    elif a >= 0.55 and mid >= 0.18:
        key = "a_mid"
    elif ct >= 0.10:
        key = "retreat"
    else:
        key = "default"
    return NAMES[key]


def rule_label(counts: dict) -> str:
    """TAGNet's rule-based positional baseline on the 20 s area counts."""
    a, b, mid = counts.get("A", 0), counts.get("B", 0), counts.get("Mid", 0)
    if mid >= 2:
        return "mid_control"
    if a >= 4:
        return "a_heavy"
    if b >= 3:
        return "b_heavy"
    if a >= b + 2:
        return "a_leaning"
    if b >= a + 2:
        return "b_leaning"
    return "balanced"


def area_counts(snapshot: dict, map_name: str, overrides: dict | None) -> dict:
    c = Counter(macro_area(map_name, p.get("place"), overrides) for p in snapshot["ct"])
    return {a: c.get(a, 0) for a in AREAS}


def count_features(formation: dict, map_name: str, overrides: dict | None) -> list[float]:
    """Paper's count baseline: CT players per macro area at each snapshot (5 x 5 = 25)."""
    by_second = {s["second"]: s for s in formation["snapshots"]}
    vec = []
    for area in AREAS:
        for second in SNAPSHOT_SECONDS:
            vec.append(float(area_counts(by_second[second], map_name, overrides)[area]))
    return vec


def setup_string(counts: dict) -> str:
    parts = [
        f"{label}{counts[key]}"
        for key, label in (("A", "A"), ("Mid", "中"), ("B", "B"), ("CT", "CT"))
        if counts.get(key)
    ]
    if counts.get("other"):
        parts.append(f"其他{counts['other']}")
    return " · ".join(parts)


def score_state(context: dict) -> str:
    diff = (context.get("ct_score_before") or 0) - (context.get("t_score_before") or 0)
    return "leading" if diff > 0 else "trailing" if diff < 0 else "tied"


def _usable(formations):
    return [f for f in formations if f.get("complete")]


def player_roles(formations, map_name, overrides, second=15, min_rounds=5):
    places = defaultdict(Counter)
    areas = defaultdict(Counter)
    teams, names = {}, {}
    for f in formations:
        snap = next((s for s in f["snapshots"] if s["second"] == second), None)
        if not snap:
            continue
        for p in snap["ct"]:
            pid = p["player_id"]
            places[pid][p.get("place") or "未知"] += 1
            areas[pid][macro_area(map_name, p.get("place"), overrides)] += 1
            teams.setdefault(pid, Counter())[f.get("ct_team")] += 1
            names[pid] = p.get("player") or pid
    roles = []
    for pid, counter in places.items():
        n = sum(counter.values())
        if n < min_rounds:
            continue
        top = counter.most_common(3)
        roles.append(
            {
                "player_id": pid,
                "player": names[pid],
                "team": teams[pid].most_common(1)[0][0],
                "rounds": n,
                "top_places": [{"place": k, "share": round(v / n, 3)} for k, v in top],
                "area_shares": {a: round(areas[pid].get(a, 0) / n, 3) for a in AREAS if areas[pid].get(a)},
                "consistency": round(top[0][1] / n, 3),
            }
        )
    return sorted(roles, key=lambda r: (str(r["team"]), -r["consistency"]))


def rotations(formation, map_name, overrides):
    """Per player: macro area at 10 s -> 20 s (only changes)."""
    by_second = {s["second"]: {p["player_id"]: p for p in s["ct"]} for s in formation["snapshots"]}
    first, last = by_second.get(SNAPSHOT_SECONDS[0], {}), by_second.get(SNAPSHOT_SECONDS[-1], {})
    moves = []
    for pid, p in first.items():
        q = last.get(pid)
        if not q:
            continue
        a, b = (
            macro_area(map_name, p.get("place"), overrides),
            macro_area(map_name, q.get("place"), overrides),
        )
        if a != b or p.get("place") != q.get("place"):
            moves.append(
                {
                    "player": p.get("player"),
                    "from": p.get("place"),
                    "to": q.get("place"),
                    "from_area": a,
                    "to_area": b,
                }
            )
    return moves


def bootstrap_stability(x, k, *, rounds=30, seed=7):
    """Mean ARI between the full partition and partitions refit on bootstrap resamples."""
    rng = np.random.default_rng(seed)
    full, _, _ = stats.kmeans(x, k)
    scores = []
    for _ in range(rounds):
        idx = rng.choice(len(x), len(x), replace=True)
        uniq = np.unique(idx)
        if len(uniq) <= k:
            continue
        labels, centers, _ = stats.kmeans(x[uniq], k, n_init=5)
        assigned = ((x[uniq][:, None] - centers[None]) ** 2).sum(-1).argmin(1)
        scores.append(stats.adjusted_rand(full[uniq], assigned))
    return float(np.mean(scores)) if scores else None


def analyze_map(
    map_name: str,
    formations: list[dict],
    throws: list[dict],
    overrides: dict | None = None,
    *,
    max_k: int = 8,
    min_cluster: int = 3,
) -> dict:
    usable = _usable(formations)
    n = len(usable)
    result = {
        "map": map_name,
        "method": "tagnet-count-baseline",
        "citation": CITATION,
        "rounds": n,
        "excluded_rounds": len(formations) - n,
        "matches": len({f["round_id"].rsplit("-r", 1)[0] for f in usable}),
        "teams": sorted({f["ct_team"] for f in usable if f.get("ct_team")}),
        "snapshot_seconds": list(SNAPSHOT_SECONDS),
        "patterns": [],
        "k_selection": [],
        "warnings": [],
    }
    if n < 2 * min_cluster:
        result["warnings"].append("样本太少，无法聚类。")
        return result
    if n < 100:
        result["warnings"].append(
            f"只有 {n} 个 CT 回合（论文用了 697 个）：阵型划分和检验结论都不稳定，仅供参考。"
        )
    x = np.array([count_features(f, map_name, overrides) for f in usable])
    # Deviation from the paper (K = 2..15): on our maps the rank rule prefers K = 2 (stacked vs
    # spread), which is too coarse to teach from, so candidates start at 4.
    min_size = max(min_cluster, int(0.03 * n))
    ks = range(min(4, max(2, n // min_size)), max(2, min(max_k, n // min_size)) + 1)
    best, rows = stats.select_k(x, ks, min_size=min_size)
    result["k_selection"] = [{k: v for k, v in r.items() if k != "labels"} for r in rows]
    if best is None:
        result["warnings"].append("无法确定阵型数量。")
        return result
    labels = best["labels"]
    k = best["k"]
    result["k"] = k
    result["stability_ari"] = bootstrap_stability(x, k)
    result["quality"] = {key: best[key] for key in ("silhouette", "davies_bouldin", "calinski_harabasz")}
    throw_index = defaultdict(list)
    for t in throws:
        if t.get("side") == "CT":
            throw_index[t["round_id"]].append(t)
    centers = np.array([x[labels == c].mean(0) for c in range(k)])
    assignments = {}
    for c in range(k):
        members = [f for f, lab in zip(usable, labels, strict=True) if lab == c]
        idx = np.where(labels == c)[0]
        shares_over_time = {}
        for second in SNAPSHOT_SECONDS:
            total = Counter()
            for f in members:
                snap = next(s for s in f["snapshots"] if s["second"] == second)
                total.update(area_counts(snap, map_name, overrides))
            shares_over_time[second] = {a: round(total[a] / (5 * len(members)), 3) for a in AREAS}
        name_zh, name_en, rationale = draft_name(shares_over_time[15])
        rep = usable[int(idx[((x[idx] - centers[c]) ** 2).sum(1).argmin()])]
        setups = Counter(
            setup_string(
                area_counts(next(s for s in f["snapshots"] if s["second"] == 15), map_name, overrides)
            )
            for f in members
        )
        decided = [f for f in members if f.get("winner") in ("CT", "T")]
        wins = sum(f["winner"] == "CT" for f in decided)
        utility = Counter()
        for f in members:
            for t in throw_index[f["round_id"]]:
                if t.get("time", 999) <= 20:
                    utility[(t["kind"], t.get("origin_area") or t.get("origin_place") or "未知")] += 1
        places = Counter()
        for f in members:
            snap = next(s for s in f["snapshots"] if s["second"] == 15)
            places.update(p.get("place") or "未知" for p in snap["ct"])
        for f in members:
            assignments[f["round_id"]] = c
        result["patterns"].append(
            {
                "id": c,
                "name": name_zh,
                "name_en": name_en,
                "rationale": rationale,
                "name_source": "规则草拟（论文阈值），待人工确认",
                "rounds": len(members),
                "ct_wins": wins,
                "decided": len(decided),
                "ct_win_rate": round(wins / len(decided), 3) if decided else None,
                "shares": shares_over_time,
                "setups": [{"setup": s, "rounds": v} for s, v in setups.most_common(5)],
                "top_places": [
                    {"place": p, "share": round(v / (5 * len(members)), 3)} for p, v in places.most_common(6)
                ],
                "economy": dict(Counter(f["context"]["ct_econ"] for f in members)),
                "teams": dict(Counter(f.get("ct_team") for f in members)),
                "utility_per_round": [
                    {"kind": kind, "area": area, "per_round": round(v / len(members), 2)}
                    for (kind, area), v in utility.most_common(6)
                ],
                "representative": rep["round_id"],
                "round_ids": [f["round_id"] for f in members],
            }
        )
    name_patterns(result["patterns"])
    result["assignments"] = assignments
    result["context_tests"] = context_tests(usable, labels)
    result["teams_fingerprint"] = team_fingerprints(usable, labels, k)
    result["roles"] = player_roles(usable, map_name, overrides)
    if n >= 40:
        spots = learn_spots(usable)
        result["spots"] = spots["spots"]
        result["team_habits"] = team_habits(usable, labels, k, spots, throws, map_name, overrides)
    return result


AREA_ZH = {"A": "A 区", "B": "B 区", "Mid": "中路", "CT": "CT 后场", "other": "其他"}


def name_patterns(patterns):
    """Readable, unique names: the macro area most over-represented at 15 s relative to the
    map average, plus the most common setup. The paper's threshold name is kept separately."""
    if not patterns:
        return
    total = sum(p["rounds"] for p in patterns)
    mean = {a: sum(p["shares"][15][a] * p["rounds"] for p in patterns) / total for a in AREAS}
    for p in patterns:
        lift = {a: p["shares"][15][a] - mean[a] for a in ("A", "B", "Mid", "CT")}
        area = max(lift, key=lift.get)
        p["paper_name"], p["paper_name_en"] = p["name"], p["name_en"]
        p["name"] = (
            f"{AREA_ZH[area]}加人 · {p['setups'][0]['setup']}"
            if lift[area] > 0.04
            else (f"均衡默认 · {p['setups'][0]['setup']}")
        )
        p["emphasis"] = {"area": area, "lift": round(lift[area], 3)}
    seen = Counter(p["name"] for p in patterns)
    for p in patterns:
        if seen[p["name"]] > 1:
            p["name"] = f"{p['name']}（{p['id'] + 1}）"


def context_tests(usable, labels, min_expected=5.0):
    variables = {
        "ct_econ": lambda f: f["context"]["ct_econ"],
        "score_state": lambda f: score_state(f["context"]),
        "prev_winner_side": lambda f: f["context"].get("prev_winner_side"),
        "prev_attack_site": lambda f: f["context"].get("prev_attack_site") or "unknown",
    }
    rows = []
    for name, get in variables.items():
        values = [get(f) for f in usable]
        keep = [i for i, v in enumerate(values) if v is not None]
        cats = sorted({values[i] for i in keep})
        k = int(labels.max()) + 1
        table = np.zeros((len(cats), k))
        for i in keep:
            table[cats.index(values[i]), labels[i]] += 1
        test = stats.chi2_test(table)
        test.update(variable=name, categories=cats, table=table.astype(int).tolist())
        test["reliable"] = bool(test["min_expected"] is not None and test["min_expected"] >= min_expected)
        rows.append(test)
    for row, adj in zip(rows, stats.holm([r["p_value"] for r in rows]), strict=True):
        row["p_holm"] = adj
    return rows


def team_fingerprints(usable, labels, k, min_rounds=5):
    by_team = defaultdict(list)
    for f, lab in zip(usable, labels, strict=True):
        if f.get("ct_team"):
            by_team[f["ct_team"]].append(int(lab))
    teams = []
    for team, labs in sorted(by_team.items()):
        if len(labs) < min_rounds:
            continue
        counts = np.bincount(labs, minlength=k)
        teams.append({"team": team, "rounds": len(labs), "shares": (counts / len(labs)).round(3).tolist()})
    similarity = []
    for i in range(len(teams)):
        for j in range(i + 1, len(teams)):
            similarity.append(
                {
                    "a": teams[i]["team"],
                    "b": teams[j]["team"],
                    "cosine": stats.cosine_similarity(teams[i]["shares"], teams[j]["shares"]),
                }
            )
    return {"teams": teams, "similarity": similarity}


def learn_spots(formations, *, k_range=range(10, 25, 2), seed=0, sample=1500):
    """Project method: data-driven CT positions ("spots") from player coordinates at all
    snapshots, K chosen by silhouette on a sample. Each spot is named after its majority
    demo place (with a number when a place splits into several spots)."""
    pts, names = [], []
    for f in formations:
        for s in f["snapshots"]:
            for p in s["ct"]:
                if p.get("x") is not None:
                    pts.append([p["x"], p["y"], (p.get("z") or 0) * 2])
                    names.append(p.get("place") or "未知")
    x = np.array(pts, float)
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(x), min(sample, len(x)), replace=False)
    best = None
    for k in k_range:
        if k >= len(idx):
            break
        labels, centers, _ = stats.kmeans(x[idx], k, n_init=4, seed=seed)
        score = stats.silhouette(x[idx], labels)
        if best is None or score > best[0]:
            best = (score, k, centers)
    _, k, centers = best
    assign = ((x[:, None] - centers[None]) ** 2).sum(-1).argmin(1)
    spots = []
    used = Counter()
    for c in range(k):
        members = [names[i] for i in np.where(assign == c)[0]]
        place = Counter(members).most_common(1)[0][0] if members else "未知"
        used[place] += 1
        spots.append(
            {
                "id": c,
                "place": place,
                "x": round(float(centers[c][0])),
                "y": round(float(centers[c][1])),
                "z": round(float(centers[c][2] / 2)),
                "points": len(members),
            }
        )
    for spot in spots:
        same = [s for s in spots if s["place"] == spot["place"]]
        spot["name"] = spot["place"] if len(same) == 1 else f"{spot['place']}·{same.index(spot) + 1}"
    return {"spots": spots, "centers": centers, "k": k}


def _spot_of(p, centers):
    v = np.array([p["x"], p["y"], (p.get("z") or 0) * 2], float)
    return int(((centers - v) ** 2).sum(1).argmin())


def team_habits(usable, labels, k, spots, throws, map_name, overrides, min_rounds=15):
    """Per team: pattern mix vs the league (chi-square, Holm across teams), most frequent spot
    setups at 15 s, player roles and 10 s -> 20 s rotations, CT utility per round vs the league."""
    centers, spot_names = spots["centers"], [s["name"] for s in spots["spots"]]
    throw_index = defaultdict(list)
    for t in throws:
        if t.get("side") == "CT" and (t.get("time") or 999) <= 20:
            throw_index[t["round_id"]].append(t)
    league_util = Counter()
    for f in usable:
        for t in throw_index[f["round_id"]]:
            league_util[(t["kind"], macro_area(map_name, t.get("origin_place"), overrides))] += 1
    by_team = defaultdict(list)
    for f, lab in zip(usable, labels, strict=True):
        if f.get("ct_team"):
            by_team[f["ct_team"]].append((f, int(lab)))
    league_counts = np.bincount(labels, minlength=k)
    rows = []
    for team, items in sorted(by_team.items()):
        if len(items) < min_rounds:
            continue
        labs = np.array([lab for _, lab in items])
        counts = np.bincount(labs, minlength=k)
        rest = league_counts - counts
        test = stats.chi2_test(np.vstack([counts, rest]))
        setups, players, moves, util = Counter(), defaultdict(Counter), defaultdict(Counter), Counter()
        names = {}
        for f, _ in items:
            by_second = {s["second"]: s for s in f["snapshots"]}
            at15 = by_second[15]["ct"]
            setups[setup_string(area_counts(by_second[15], map_name, overrides))] += 1
            first = {p["player_id"]: p for p in by_second[10]["ct"]}
            last = {p["player_id"]: p for p in by_second[20]["ct"]}
            for p in at15:
                players[p["player_id"]][spot_names[_spot_of(p, centers)]] += 1
                names[p["player_id"]] = p.get("player") or p["player_id"]
                a, b = first.get(p["player_id"]), last.get(p["player_id"])
                if a and b:
                    sa, sb = spot_names[_spot_of(a, centers)], spot_names[_spot_of(b, centers)]
                    if sa != sb:
                        moves[p["player_id"]][f"{sa} → {sb}"] += 1
            for t in throw_index[f["round_id"]]:
                util[(t["kind"], macro_area(map_name, t.get("origin_place"), overrides))] += 1
        n = len(items)
        decided = [f for f, _ in items if f.get("winner") in ("CT", "T")]
        role_rows = []
        for pid, counter in players.items():
            rounds_played = sum(counter.values())
            if rounds_played < max(5, n // 4):
                continue
            top = counter.most_common(3)
            role_rows.append(
                {
                    "player": names[pid],
                    "rounds": rounds_played,
                    "spots": [{"spot": s, "share": round(v / rounds_played, 3)} for s, v in top],
                    "consistency": round(top[0][1] / rounds_played, 3),
                    "rotations": [
                        {"move": m, "share": round(v / rounds_played, 3)}
                        for m, v in moves[pid].most_common(2)
                    ],
                }
            )
        rows.append(
            {
                "team": team,
                "rounds": n,
                "matches": len({f["round_id"].rsplit("-r", 1)[0] for f, _ in items}),
                "ct_win_rate": round(sum(f["winner"] == "CT" for f in decided) / len(decided), 3)
                if decided
                else None,
                "pattern_shares": (counts / n).round(3).tolist(),
                "league_shares": (league_counts / league_counts.sum()).round(3).tolist(),
                "differs_from_league": {
                    k2: test[k2] for k2 in ("chi2", "dof", "p_value", "cramers_v", "min_expected")
                },
                "top_setups": [
                    {"setup": s, "rounds": v, "share": round(v / n, 3)} for s, v in setups.most_common(4)
                ],
                "roles": sorted(role_rows, key=lambda r: -r["consistency"]),
                "utility_per_round": [
                    {
                        "kind": kind,
                        "area": area,
                        "per_round": round(v / n, 2),
                        "league_per_round": round(league_util[(kind, area)] / len(usable), 2),
                    }
                    for (kind, area), v in util.most_common(6)
                ],
            }
        )
    for row, adj in zip(rows, stats.holm([r["differs_from_league"]["p_value"] for r in rows]), strict=True):
        row["differs_from_league"]["p_holm"] = adj
    return rows
