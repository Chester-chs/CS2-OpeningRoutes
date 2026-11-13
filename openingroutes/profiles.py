"""Observed player/team area habits. Occupancy and damage are proxies, not tactical truth."""

import hashlib
import json
from bisect import bisect_right
from collections import Counter, defaultdict

import numpy as np

from . import eras
from .domain import effective_round
from .formations import economy_bucket
from .patterns import DEFAULT_MACRO
from .places import place_label

PROFILE_VERSION = 2  # 2: map eras pool patches
WINDOW_SECONDS = 30
HOLD_SECONDS = 2
AREA_LABELS = {"A": "A 区", "B": "B 区", "Mid": "中路", "CT": "CT 后场", "T": "T 后场"}


def _frames(timeline, row):
    rate = timeline["tick_rate"]
    start, end = row["freeze_end_tick"], row["end_tick"]
    step = max(1, round(rate / 4))
    expected = {e["player_id"] for e in row.get("equipment", [])} or set(timeline["players"])
    players = []
    for pid in expected:
        player = timeline["players"].get(pid, {})
        points = player.get("points", [])
        players.append((points, player.get("places", []), [p[0] for p in points]))
    result = []
    for tick in sorted(set(range(start, end + 1, step)) | {end}):
        counts, known = Counter(), bool(players)
        for points, places, ticks in players:
            i = bisect_right(ticks, tick) - 1
            if i < 0 or tick - ticks[i] > step * 1.5 or i >= len(places):
                known = False
                continue
            point = points[i]
            if point[5]:
                if not places[i] or point[4] not in ("CT", "T"):
                    known = False
                else:
                    counts[(point[4], places[i])] += 1
        result.append(((tick - start) / rate, counts, known))
    return result


def area_states(timeline, row, places, *, frames=None):
    """A two-second uninterrupted solo presence, with missing/dead observations handled explicitly."""
    frames = _frames(timeline, row) if frames is None else frames
    points, previous, since, known_count = [], None, 0, 0
    state = "unknown"
    for second, counts, known in frames:
        ct = sum(n for (side, place), n in counts.items() if side == "CT" and place in places)
        t = sum(n for (side, place), n in counts.items() if side == "T" and place in places)
        candidate = (
            ("contested" if ct and t else "CT" if ct else "T" if t else "empty") if known else "unknown"
        )
        if candidate != previous:
            since = second
        state = "transit" if candidate in ("CT", "T") and second - since < HOLD_SECONDS else candidate
        if second <= WINDOW_SECONDS:
            points.append([round(second, 3), ct, t, state])
            known_count += int(known)
        previous = candidate
    return {
        "points": points,
        "end_state": state,
        "missing_fraction": round(1 - known_count / len(points), 4) if points else 1,
        "basis": "alive presence; 2 s hold; not visibility or tactical control",
    }


def _route(player, row, rate):
    segments = []
    for point, place in zip(player["points"], player["places"], strict=True):
        second = (point[0] - row["freeze_end_tick"]) / rate
        if not (0 <= second < WINDOW_SECONDS) or not point[5] or not place:
            continue
        end = min(second + 0.25, WINDOW_SECONDS, (row["end_tick"] - row["freeze_end_tick"]) / rate)
        if end <= second:
            continue
        if segments and segments[-1]["place"] == place and second - segments[-1]["end"] < 0.01:
            segments[-1]["end"] = round(end, 3)
        else:
            segments.append(
                {"place": place, "start": round(second, 3), "end": round(end, 3), "position": point[1:4]}
            )
    return segments


def _team(match, equipment):
    name = equipment.get("team") or "unknown"
    return match.get("team_aliases", {}).get(name, name)


def _stints(matches):
    last, epochs, result = {}, {}, {}
    for match in sorted(matches, key=lambda m: (m["source"].get("date", ""), m["id"])):
        if not match["source"].get("verified"):
            continue
        for row in match["rounds"]:
            for e in row.get("equipment", []):
                pid, team = e["player_id"], _team(match, e)
                if last.get(pid) != team:
                    epochs[pid] = f"{match['source'].get('date', '')}:{match['id']}"
                    last[pid] = team
                result[(match["id"], pid, team)] = epochs[pid]
    return result


def _regions(map_name, overrides, groups):
    mapping = {**DEFAULT_MACRO.get(map_name, {}), **overrides.get(map_name, {})}
    mapping.update({p: "T" for p in ("TSpawn", "TStart") if p not in overrides.get(map_name, {})})
    result = {
        key: {"label": label, "places": {p for p, area in mapping.items() if area == key}}
        for key, label in AREA_LABELS.items()
    }
    for key, group in groups.items():
        if group.get("kind") == "region" and group.get("map") == map_name:
            result[key] = {"label": group["label"], "places": set(group["places"])}
    return {key: value for key, value in result.items() if value["places"]}


def _interval(samples, selected):
    """Resample whole matches, preserving within-match dependence and sample weights."""
    blocks = defaultdict(lambda: [0, 0])
    for sample in samples:
        block = blocks[sample["match_id"]]
        block[0] += int(sample["id"] in selected)
        block[1] += 1
    if len(blocks) < 5:
        return None
    values = np.array(list(blocks.values()))
    draws = np.random.default_rng(7).integers(0, len(values), size=(400, len(values)))
    sums = values[draws].sum(axis=1)
    return [round(float(x), 3) for x in np.quantile(sums[:, 0] / sums[:, 1], [0.025, 0.975])]


def _distribution(samples, key):
    groups = defaultdict(set)
    for sample in samples:
        for value in set(sample.get(key, [])):
            groups[value].add(sample["id"])
    return [
        {
            "label": label,
            "rounds": len(ids),
            "share": round(len(ids) / len(samples), 3),
            "interval": _interval(samples, ids),
        }
        for label, ids in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0]))[:8]
    ]


def summarize(samples):
    rounds = len({s["round_id"] for s in samples})
    matches = len({s["match_id"] for s in samples})
    players = {pid for s in samples for pid in s["player_ids"]}
    timings = defaultdict(list)
    for sample in samples:
        for throw in sample["utility"]:
            timings[throw["kind"]].append(throw["time"])
    return {
        "counts": {
            "rounds": rounds,
            "matches": matches,
            "players": len(players),
            "pistols": sum(s["pistol"] for s in samples),
        },
        "confidence": {
            "status": "exploratory" if rounds < 30 or matches < 5 else "descriptive",
            "method": "95% match-block bootstrap; 400 resamples" if matches >= 5 else "insufficient_matches",
            "minimum_rounds": 30,
            "minimum_matches": 5,
        },
        "habits": _distribution(samples, "standing_places"),
        "routes": _distribution(samples, "route_labels"),
        "sequences": _distribution(samples, "utility_labels"),
        "utility_timing": [
            {
                "kind": kind,
                "count": len(times),
                "median": round(float(np.median(times)), 2),
                "p25": round(float(np.quantile(times, 0.25)), 2),
                "p75": round(float(np.quantile(times, 0.75)), 2),
            }
            for kind, times in sorted(timings.items())
        ],
        "wins": sum(s["winner"] == s["side"] for s in samples),
        "missing_fraction": round(float(np.mean([s["control"]["missing_fraction"] for s in samples])), 4)
        if samples
        else 1,
    }


def _sample(match, row, timeline, actors, team, side, places, control, throws, routes):
    selected = set(actors)
    utility = [t for t in throws if t["player_id"] in selected]
    opponent = [
        t
        for t in throws
        if t.get("side") not in (None, side)
        and (t.get("effect_place") in places or t.get("origin_place") in places)
    ]
    contacts = [
        e
        for e in row.get("learning_events", [])
        if e.get("attacker_place") in places or e.get("victim_place") in places
    ]
    first_contact = next((e for e in contacts if e["kind"] == "hurt"), None)
    first_kill = next((e for e in contacts if e["kind"] == "death"), None)
    equipment = [e for e in row["equipment"] if e.get("side") == side]
    total = sum(e["equip"] for e in equipment) if all(e.get("equip") is not None for e in equipment) else None
    ctx = match.get("formations", {}).get(row["id"], {}).get("context", {})
    score = (ctx.get(f"{side.lower()}_score_before") or 0) - (
        ctx.get("t_score_before" if side == "CT" else "ct_score_before") or 0
    )
    standing, route_labels = [], []
    for pid in actors:
        dwell = Counter()
        for segment in routes[pid]:
            dwell[segment["place"]] += segment["end"] - segment["start"]
        if dwell:
            standing.append(dwell.most_common(1)[0][0])
        route_labels.append(" → ".join(s["place"] for s in routes[pid]))
    return {
        "id": f"{row['id']}:{','.join(sorted(actors))}",
        "round_id": row["id"],
        "match_id": match["id"],
        "number": row["number"],
        "player_ids": sorted(actors),
        "team": team,
        "side": side,
        "pistol": bool(row.get("is_pistol")),
        "winner": row.get("winner"),
        "economy": economy_bucket(total, bool(row.get("is_pistol"))),
        "score": ("leading" if score > 0 else "trailing" if score < 0 else "tied") if ctx else "unknown",
        "date": match["source"].get("date", ""),
        "game_version": match.get("game_version"),
        "source": {k: match["source"].get(k) for k in ("event", "match", "date", "url")},
        "routes": {pid: routes[pid] for pid in actors},
        "standing_places": standing,
        "route_labels": route_labels,
        "utility_labels": [" → ".join(t["kind"] for t in utility)] if utility else [],
        "utility": utility,
        "opponent_utility": opponent,
        "first_contact": first_contact,
        "first_kill": first_kill,
        "control": control,
        "practice": [
            "核对冻结结束装备和出生位",
            "对照前 30 秒站位与移动",
            "按相对时间核对道具顺序",
            "观察对手动作与后续位置；因果待人工确认",
            "打开完整回合，优先复用已验证教学跟练",
        ],
    }


def build(matches, timeline_loader, *, reviews=None, overrides=None, labels=None, groups=None):
    reviews, overrides, labels, groups = reviews or {}, overrides or {}, labels or {}, groups or {}
    matches = list({m["id"]: m for m in matches}.values())
    epochs = _stints(matches)
    profiles, definitions = {}, {}
    coverage = {
        "library_rounds": sum(len(m["rounds"]) for m in matches),
        "eligible_rounds": 0,
        "analyzed_rounds": 0,
        "missing_rounds": 0,
    }
    for match in matches:
        if not match["source"].get("verified"):
            continue
        map_name = match["map"]
        regions = _regions(map_name, overrides, groups)
        definitions[map_name] = {key: {**r, "places": sorted(r["places"])} for key, r in regions.items()}
        by_round = defaultdict(list)
        for throw in match["throws"]:
            if 0 <= throw.get("time", -1) <= WINDOW_SECONDS:
                by_round[throw["round_id"]].append(
                    {
                        k: throw.get(k)
                        for k in (
                            "id",
                            "tick",
                            "time",
                            "kind",
                            "side",
                            "player_id",
                            "player",
                            "origin_place",
                            "effect_place",
                            "effect_place_basis",
                        )
                    }
                )
        # one era per match: it depends only on the map, the date and the patch
        era = eras.era_for(map_name, match["source"].get("date", ""), match.get("game_version"))
        for original in match["rounds"]:
            row = effective_round(original, reviews.get(original["id"], {}))
            if row.get("excluded") or row.get("review_required") or not row.get("complete"):
                continue
            coverage["eligible_rounds"] += 1
            timeline = timeline_loader(row["id"]) if match.get("learning_version") == 1 else None
            roster = {e["player_id"] for e in row.get("equipment", [])}
            if (
                not timeline
                or not roster
                or not roster.issubset(timeline.get("players", {}))
                or any(
                    not p.get("points") or len(p.get("places", [])) != len(p["points"])
                    for p in timeline["players"].values()
                )
            ):
                coverage["missing_rounds"] += 1
                continue
            coverage["analyzed_rounds"] += 1
            frames = _frames(timeline, row)
            routes = {pid: _route(p, row, timeline["tick_rate"]) for pid, p in timeline["players"].items()}
            throws = sorted(by_round[row["id"]], key=lambda t: (t["tick"], t["id"]))
            for area, region in regions.items():
                places = region["places"]
                participants = []
                for e in row["equipment"]:
                    pid = e["player_id"]
                    dwell = sum(s["end"] - s["start"] for s in routes[pid] if s["place"] in places)
                    if dwell >= HOLD_SECONDS or any(
                        t["player_id"] == pid and t.get("effect_place") in places for t in throws
                    ):
                        participants.append(e)
                if not participants:
                    continue
                control = area_states(timeline, row, places, frames=frames)
                subjects = []
                for e in participants:
                    team, pid = _team(match, e), e["player_id"]
                    subjects.append(
                        (
                            "player",
                            pid,
                            e.get("player") or pid,
                            team,
                            e["side"],
                            epochs[(match["id"], pid, team)],
                            [pid],
                        )
                    )
                for side in ("CT", "T"):
                    members = [e for e in participants if e.get("side") == side]
                    if not members:
                        continue
                    team = _team(match, members[0])
                    roster_key = ",".join(
                        sorted(e["player_id"] for e in row["equipment"] if e.get("side") == side)
                    )
                    subjects.append(
                        ("team", team, team, team, side, roster_key, [e["player_id"] for e in members])
                    )
                    for gid, g in groups.items():
                        if (
                            g.get("kind") != "role"
                            or not g.get("confirmed")
                            or g.get("map") != map_name
                            or g.get("side") != side
                            or g.get("area") != area
                            or g.get("team") != team
                        ):
                            continue
                        date = match["source"].get("date", "")
                        if (g.get("date_from") and date < g["date_from"]) or (
                            g.get("date_to") and date > g["date_to"]
                        ):
                            continue
                        selected = [e["player_id"] for e in members if e["player_id"] in g.get("players", [])]
                        if selected:
                            subjects.append(("role", gid, g["label"], team, side, gid, selected))
                for kind, subject, name, team, side, epoch, actors in subjects:
                    version = era["id"] if era else str(match.get("game_version") or f"unknown:{match['id']}")
                    identity = (kind, subject, map_name, version, side, area, team, epoch)
                    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()[:24]
                    p = profiles.setdefault(
                        key,
                        {
                            "id": key,
                            "kind": kind,
                            "subject_id": subject,
                            "name": name,
                            "map": map_name,
                            "version": version,
                            "era": era,
                            "side": side,
                            "area": area,
                            "area_label": region["label"],
                            "area_places": sorted(places),
                            "team": team,
                            "epoch": epoch,
                            "members": [],
                            "aliases": [],
                            "samples": [],
                        },
                    )
                    p["aliases"] = sorted(set(p["aliases"]) | {name})
                    p["members"] = sorted(set(p["members"]) | set(actors))
                    p["samples"].append(
                        _sample(match, row, timeline, actors, team, side, places, control, throws, routes)
                    )
    index = []
    for p in profiles.values():
        samples = sorted(p["samples"], key=lambda s: (s["date"], s["round_id"]), reverse=True)
        p["samples"] = samples
        p.update(summarize(samples))
        p["date_from"], p["date_to"] = min(s["date"] for s in samples), max(s["date"] for s in samples)
        patches = defaultdict(lambda: (set(), set()))
        for s in samples:
            rounds, games = patches[str(s["game_version"] or "unknown")]
            rounds.add(s["round_id"])
            games.add(s["match_id"])
        p["patches"] = {k: {"rounds": len(r), "matches": len(g)} for k, (r, g) in sorted(patches.items())}
        p["contexts"] = {}
        for field in ("economy", "score"):
            for value in sorted({s[field] for s in samples}):
                p["contexts"][f"{field}:{value}"] = summarize([s for s in samples if s[field] == value])
        p["contexts"]["pistol"] = summarize([s for s in samples if s["pistol"]])
        p["contexts"]["non_pistol"] = summarize([s for s in samples if not s["pistol"]])
        p["place_labels"] = {
            place: place_label(p["map"], place, labels)
            for s in samples
            for routes in s["routes"].values()
            for seg in routes
            for place in [seg["place"]]
        }
        index.append(
            {
                k: p[k]
                for k in (
                    "id",
                    "kind",
                    "subject_id",
                    "name",
                    "aliases",
                    "map",
                    "version",
                    "era",
                    "patches",
                    "side",
                    "area",
                    "area_label",
                    "team",
                    "members",
                    "counts",
                    "confidence",
                    "date_from",
                    "date_to",
                )
            }
        )
    return {
        "index": {
            "schema_version": 1,
            "state": "ready",
            "profiles": sorted(index, key=lambda p: (-p["counts"]["rounds"], p["id"])),
            "coverage": coverage,
            "regions": definitions,
            "groups": groups,
        },
        "profiles": profiles,
    }
