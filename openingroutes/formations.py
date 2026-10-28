"""CT opening formations: player snapshots at fixed times after freeze end.

Follows the sampling of TAGNet (Zhang et al., IEEE Transactions on Games, 2026,
doi:10.1109/TG.2026.3745970): snapshots 10/12/15/18/20 s after the freeze time,
five CT players each, plus round context (economy, score, previous round).
Only observed facts are stored; macro areas are applied at analysis time so a
curator's corrections take effect without re-importing demos.
"""

import pandas as pd

SNAPSHOT_SECONDS = (10, 12, 15, 18, 20)
FORMATIONS_VERSION = 1
FIELDS = ["X", "Y", "Z", "last_place_name", "health", "current_equip_value", "team_num", "is_alive"]


def _records(frame):
    return frame.to_dict(orient="records")


def _side(team_num):
    return {2: "T", 3: "CT"}.get(team_num)


def economy_bucket(total_equip: float | None, pistol_round: bool) -> str:
    """TAGNet economy buckets on the team's summed equipment value."""
    if pistol_round:
        return "pistol"
    if total_equip is None:
        return "unknown"
    if total_equip < 10000:
        return "eco"
    if total_equip < 25000:
        return "half_buy"
    return "long_gun"


def plant_sites(parser) -> dict[int, str]:
    try:
        planted = parser.parse_event("bomb_planted", player=["last_place_name"])
    except Exception:  # demos without plants or without the field
        return {}
    sites = {}
    for row in _records(planted):
        place = str(row.get("user_last_place_name") or "")
        sites[int(row["tick"])] = "A" if "BombsiteA" in place else "B" if "BombsiteB" in place else "unknown"
    return sites


def extract_formations(parser, rounds: list[dict], tick_rate: float) -> dict[str, dict]:
    targets = {}
    for r in rounds:
        end = r.get("end_tick")
        for second in SNAPSHOT_SECONDS:
            tick = int(round(r["freeze_end_tick"] + second * tick_rate))
            if end is None or tick < end:
                targets[tick] = (r["id"], second)
    if not targets:
        return {}
    frame = parser.parse_ticks(FIELDS, ticks=sorted(targets))
    frame["steamid"] = frame["steamid"].astype(str)
    by_tick = {int(t): g for t, g in frame.groupby("tick")}
    sites = plant_sites(parser)
    result: dict[str, dict] = {}
    score: dict[str, int] = {}
    previous = None
    for r in sorted(rounds, key=lambda x: x["number"]):
        snapshots = []
        teams = {e.get("side"): e.get("team") for e in r.get("equipment", [])}
        for second in SNAPSHOT_SECONDS:
            tick = int(round(r["freeze_end_tick"] + second * tick_rate))
            group = by_tick.get(tick)
            if group is None:
                continue
            players = {"CT": [], "T": []}
            for row in _records(group):
                side = _side(row.get("team_num"))
                if side not in players:
                    continue
                players[side].append(
                    {
                        "player_id": row["steamid"],
                        "player": row.get("name"),
                        "x": None if pd.isna(row.get("X")) else round(float(row["X"]), 1),
                        "y": None if pd.isna(row.get("Y")) else round(float(row["Y"]), 1),
                        "z": None if pd.isna(row.get("Z")) else round(float(row["Z"]), 1),
                        "place": row.get("last_place_name") or None,
                        "health": int(row.get("health") or 0),
                        "alive": bool(row.get("is_alive")),
                        "equip": int(row.get("current_equip_value") or 0),
                    }
                )
            snapshots.append(
                {
                    "second": second,
                    "tick": tick,
                    "ct": sorted(players["CT"], key=lambda p: p["player_id"]),
                    "t_areas_place": [p["place"] for p in players["T"]],
                    "ct_equip": sum(p["equip"] for p in players["CT"]),
                    "t_equip": sum(p["equip"] for p in players["T"]),
                }
            )
        ct_team, t_team = teams.get("CT"), teams.get("T")
        plant = next(
            (
                site
                for tick, site in sites.items()
                if r["freeze_end_tick"] <= tick <= (r.get("end_tick") or tick)
            ),
            None,
        )
        first = snapshots[0] if snapshots else None
        result[r["id"]] = {
            "round_id": r["id"],
            "number": r["number"],
            "ct_team": ct_team,
            "t_team": t_team,
            "winner": r.get("winner"),
            "complete": len(snapshots) == len(SNAPSHOT_SECONDS) and all(len(s["ct"]) == 5 for s in snapshots),
            "snapshots": snapshots,
            "context": {
                "pistol": bool(r.get("is_pistol")),
                "ct_equip": first["ct_equip"] if first else None,
                "t_equip": first["t_equip"] if first else None,
                "ct_econ": economy_bucket(first["ct_equip"] if first else None, bool(r.get("is_pistol"))),
                "t_econ": economy_bucket(first["t_equip"] if first else None, bool(r.get("is_pistol"))),
                "ct_score_before": score.get(ct_team, 0),
                "t_score_before": score.get(t_team, 0),
                "prev_winner_side": previous["winner"] if previous else None,
                "prev_attack_site": previous["site"] if previous else None,
                "plant_site": plant,
            },
        }
        winner_team = teams.get(r.get("winner"))
        if winner_team:
            score[winner_team] = score.get(winner_team, 0) + 1
        previous = {"winner": r.get("winner"), "site": plant or "unknown"}
    return result


def _norm(name: str) -> str:
    text = "".join(ch for ch in (name or "").lower() if ch.isalnum())
    for noise in ("esports", "esport", "gaming", "team", "the"):
        if len(text) > len(noise) + 1:
            text = text.replace(noise, "")
    return text


def _subsequence(short: str, long: str) -> bool:
    it = iter(long)
    return all(ch in it for ch in short)


def _similarity(clan: str, official: str) -> float:
    a, b = _norm(clan), _norm(official)
    if not a or not b:
        return 0.0
    if a == b:
        return 3.0
    if a in b or b in a:
        return 2.0
    short, long = sorted((a, b), key=len)
    if short[0] == long[0] and _subsequence(short, long):
        return 1.0 + len(short) / len(long)
    return 0.0


def canonical_teams(clans: list[str], source_match: str) -> dict[str, str]:
    """Map the two in-demo clan tags to the two team names of the match source (e.g. HLTV).
    'FLC' -> 'Falcons', 'G2.Esports' -> 'G2'. Unmatched tags keep their own name."""
    head = (source_match or "").split("·")[0]
    official = [x.strip() for x in head.split(" vs ")] if " vs " in head else []
    clans = [c for c in dict.fromkeys(clans) if c]
    mapping = {c: c for c in clans}
    if len(official) != 2 or not clans:
        return mapping
    best, best_score = None, -1.0
    for order in (official, official[::-1]):
        pairs = list(zip(clans[:2], order, strict=False))
        score = sum(_similarity(c, o) for c, o in pairs)
        if score > best_score and all(_similarity(c, o) > 0 for c, o in pairs):
            best, best_score = pairs, score
    for clan, name in best or []:
        mapping[clan] = name
    return mapping


def finalize_formations(formations: dict[str, dict], rounds: list[dict], aliases: dict[str, str]) -> dict:
    """Attach CT/T team names, score before the round and previous-round facts from parsed rounds."""
    score: dict[str, int] = {}
    previous = None
    for r in sorted(rounds, key=lambda x: x["number"]):
        f = formations.get(r["id"])
        teams = {e.get("side"): aliases.get(e.get("team"), e.get("team")) for e in r.get("equipment", [])}
        if f is not None:
            ct_team, t_team = teams.get("CT"), teams.get("T")
            f["ct_team"], f["t_team"] = ct_team, t_team
            ctx = f.setdefault("context", {})
            ctx["ct_score_before"] = score.get(ct_team, 0)
            ctx["t_score_before"] = score.get(t_team, 0)
            ctx["prev_winner_side"] = previous["winner"] if previous else None
            ctx["prev_attack_site"] = previous["site"] if previous else None
            site = ctx.get("plant_site")
        else:
            site = None
        winner_team = teams.get(r.get("winner"))
        if winner_team:
            score[winner_team] = score.get(winner_team, 0) + 1
        previous = {"winner": r.get("winner"), "site": site or "unknown"}
    return formations
