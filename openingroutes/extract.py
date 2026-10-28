"""Parse real CS2 demos. No tactical explanations are inferred as facts."""

import hashlib
import json
import time
from collections import defaultdict
from importlib.metadata import version
from pathlib import Path

import pandas as pd
from demoparser2 import DemoParser

from .domain import build_rounds, side
from .formations import FORMATIONS_VERSION, canonical_teams, extract_formations, finalize_formations
from .store import Store, now

KINDS = {
    "smokegrenade": "smoke",
    "flashbang": "flash",
    "hegrenade": "he",
    "molotov": "molotov",
    "incgrenade": "incendiary",
    "decoy": "decoy",
}
PROJECTILES = {
    "CSmokeGrenadeProjectile": "smoke",
    "CFlashbangProjectile": "flash",
    "CHEGrenadeProjectile": "he",
    "CMolotovProjectile": "fire",
    "CDecoyProjectile": "decoy",
}
EVENTS = [
    "round_start",
    "round_freeze_end",
    "round_end",
    "grenade_thrown",
    "smokegrenade_detonate",
    "flashbang_detonate",
    "hegrenade_detonate",
    "inferno_startburn",
    "decoy_started",
    "player_death",
    "bomb_planted",
    "bomb_defused",
    "bomb_exploded",
]


def records(frame):
    """Rows of a parser result; demoparser2 returns a plain list for events absent from a demo."""
    if not hasattr(frame, "to_json"):
        return list(frame or [])
    return json.loads(frame.to_json(orient="records"))


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while block := f.read(1024 * 1024):
            h.update(block)
    return h.hexdigest()


PLACES_VERSION = 2
EFFECT_PLACE_RADIUS = 300.0
EFFECT_PLACE_DZ = 160.0


def annotate_places(parser, throws: list[dict], observed=None) -> int:
    """Attach demo callouts. The release place is the thrower's own ``last_place_name``.
    The effect place is approximated from the nearest position any player occupied in this
    match (same height band) and is stored with its basis and distance; never presented as exact."""
    thrown = records(parser.parse_event("grenade_thrown", player=["last_place_name"]))
    origin = {(e["tick"], str(e.get("user_steamid"))): e.get("user_last_place_name") for e in thrown}
    if observed is None:
        ticks = [t["tick"] for t in throws]
        lo, hi = (min(ticks), max(t.get("effect_tick") or t["tick"] for t in throws)) if ticks else (0, -1)
        observed = parser.parse_ticks(["X", "Y", "Z", "last_place_name"], ticks=list(range(lo, hi + 1, 32)))
    observed = observed.dropna(subset=["X", "Y", "Z"])
    observed = observed[observed["last_place_name"].fillna("") != ""]
    xyz = observed[["X", "Y", "Z"]].to_numpy(dtype=float)
    names = observed["last_place_name"].to_numpy()
    for t in throws:
        t["origin_place"] = origin.get((t["tick"], str(t["player_id"]))) or None
        t["effect_place"], t["effect_place_basis"] = None, None
        effect = t.get("effect_position")
        if not len(xyz) or not effect or any(v is None for v in effect):
            continue
        band = abs(xyz[:, 2] - effect[2]) <= EFFECT_PLACE_DZ
        if not band.any():
            continue
        flat = ((xyz[band, 0] - effect[0]) ** 2 + (xyz[band, 1] - effect[1]) ** 2) ** 0.5
        best = int(flat.argmin())
        if flat[best] <= EFFECT_PLACE_RADIUS:
            t["effect_place"] = str(names[band][best])
            t["effect_place_basis"] = {
                "method": "nearest_observed_player_position",
                "distance": round(float(flat[best])),
            }
    return sum(1 for t in throws if t["origin_place"])


def enrich_places(path: Path, store: Store) -> dict:
    """Add callouts and CT formations to a match imported before they existed, without re-importing it."""
    match_id = file_hash(path)[:20]
    match = store.all("matches").get(match_id)
    if match is None:
        raise ValueError("This demo has not been imported")
    parser = DemoParser(str(path))
    if match.get("places_version") != PLACES_VERSION:
        annotate_places(parser, match["throws"])
        match["places_version"] = PLACES_VERSION
    if match.get("formations_version") != FORMATIONS_VERSION:
        clans = [e.get("team") for r in match["rounds"] for e in r.get("equipment", [])]
        match["team_aliases"] = canonical_teams(clans, match["source"].get("match", ""))
        match["formations"] = finalize_formations(
            extract_formations(parser, match["rounds"], match["tick_rate"]),
            match["rounds"],
            match["team_aliases"],
        )
        match["formations_version"] = FORMATIONS_VERSION
    store.save_match(match)
    return match


def extract_demo(path: Path, source: dict, store: Store, progress=lambda stage: None) -> dict:
    started = time.monotonic()
    sha = file_hash(path)
    match_id = sha[:20]
    existing = store.all("matches").get(match_id)
    if existing is not None:
        if (
            existing.get("places_version") != PLACES_VERSION
            or existing.get("formations_version") != FORMATIONS_VERSION
        ):
            progress("places")
            return enrich_places(path, store)
        return existing
    parser = DemoParser(str(path))
    header = parser.parse_header()
    progress("events")
    event_frames = dict(
        parser.parse_events(
            EVENTS,
            player=[
                "X",
                "Y",
                "Z",
                "pitch",
                "yaw",
                "team_num",
                "team_clan_name",
                "inventory",
                "armor_value",
            ],
            other=["total_rounds_played", "is_warmup_period", "game_phase"],
        )
    )
    events = {name: records(frame) for name, frame in event_frames.items()}
    convars = parser.parse_event("server_cvar")
    maxrounds = convars[convars["name"] == "mp_maxrounds"]["value"].tolist() if not convars.empty else []
    half = int(maxrounds[-1]) // 2 if maxrounds and str(maxrounds[-1]).isdigit() else None
    rounds = build_rounds(match_id, events.get("round_freeze_end", []), events.get("round_end", []), half)
    if not rounds:
        raise ValueError("No official rounds found; check demo format and warmup state")
    first_tick = rounds[0]["freeze_end_tick"]
    clock = (
        parser.parse_ticks(["game_time"], ticks=[first_tick, first_tick + 64])
        .groupby("tick")
        .game_time.first()
    )
    if len(clock) < 2 or clock.iloc[-1] <= clock.iloc[0]:
        raise ValueError("Cannot verify demo tick-to-time conversion")
    rate = (clock.index[-1] - clock.index[0]) / (clock.iloc[-1] - clock.iloc[0])
    warnings = []
    if half is None:
        warnings.append("Regulation length missing: pistol identification requires manual review")
    for r in rounds:
        starts = [
            e["tick"]
            for e in events.get("round_start", [])
            if e.get("is_warmup_period") is False and e["tick"] <= r["freeze_end_tick"]
        ]
        r["start_tick"] = max(starts, default=r["freeze_end_tick"])
    final_tick = max(r["end_tick"] or r["freeze_end_tick"] for r in rounds)
    progress("routes")
    stride = max(1, round(rate / 4))
    sample_ticks = sorted(
        set(range(rounds[0]["start_tick"], final_tick + 1, stride)) | {r["freeze_end_tick"] for r in rounds}
    )
    positions = parser.parse_ticks(
        [
            "X",
            "Y",
            "Z",
            "is_alive",
            "team_num",
            "team_clan_name",
            "inventory",
            "armor_value",
            "health",
            "last_place_name",
        ],
        ticks=sample_ticks,
    )
    positions["steamid"] = positions["steamid"].astype(str)
    player_info = records(parser.parse_player_info())
    players = {str(p["steamid"]): p["name"] for p in player_info}
    progress("grenades")
    grenades = parser.parse_grenades()
    grenades = grenades[grenades["grenade_type"].isin(PROJECTILES)].dropna(subset=["x", "y", "z"])
    grenades["steamid"] = grenades["steamid"].astype(str)
    tracks = defaultdict(list)
    for (owner, entity, grenade_type), group in grenades.groupby(
        ["steamid", "grenade_entity_id", "grenade_type"]
    ):
        group = group.sort_values("tick").drop_duplicates("tick")
        segments = (group["tick"].diff().fillna(1) > 2).cumsum()
        for _, segment in group.groupby(segments):
            tracks[owner].append((int(entity), PROJECTILES[grenade_type], segment))
    throws = []
    det_names = [
        "smokegrenade_detonate",
        "flashbang_detonate",
        "hegrenade_detonate",
        "inferno_startburn",
        "decoy_started",
    ]
    detonations = sorted([e for name in det_names for e in events.get(name, [])], key=lambda e: e["tick"])
    for event in sorted(events.get("grenade_thrown", []), key=lambda e: e["tick"]):
        if event.get("is_warmup_period") is not False:
            continue
        tick = event["tick"]
        r = next((r for r in rounds if r["start_tick"] <= tick <= (r["end_tick"] or final_tick)), None)
        if not r:
            continue
        owner = str(event.get("user_steamid", ""))
        kind = KINDS.get(event.get("weapon"), event.get("weapon", "unknown"))
        candidates = [
            (entity, group)
            for entity, gkind, group in tracks[owner]
            if (gkind == kind or gkind == "fire" and kind in ("molotov", "incendiary"))
            and abs(int(group.iloc[0]["tick"]) - tick) <= 2
        ]
        entity, group = candidates[0] if len(candidates) == 1 else (None, None)
        effect = next(
            (
                e
                for e in detonations
                if entity is not None
                and e.get("entityid") == entity
                and tick <= e["tick"] <= tick + rate * 15
            ),
            None,
        )
        trajectory = []
        if group is not None:
            if effect:
                group = group[group["tick"] <= effect["tick"]]
            sampled = pd.concat([group.iloc[::4], group.tail(1)]).drop_duplicates("tick")
            trajectory = [
                [int(t), round(x, 3), round(y, 3), round(z, 3)]
                for t, x, y, z in sampled[["tick", "x", "y", "z"]].itertuples(index=False, name=None)
            ]
        throws.append(
            {
                "id": f"{match_id}-t{tick}-{owner}",
                "match_id": match_id,
                "round_id": r["id"],
                "round_number": r["number"],
                "map": header["map_name"],
                "player_id": owner,
                "player": event.get("user_name"),
                "team": event.get("user_team_clan_name"),
                "side": side(event.get("user_team_num")),
                "kind": kind,
                "tick": tick,
                "time": round((tick - r["freeze_end_tick"]) / rate, 3),
                "position": [event.get(f"user_{c}") for c in ("X", "Y", "Z")],
                "view": {"pitch": event.get("user_pitch"), "yaw": event.get("user_yaw")},
                "inventory": event.get("user_inventory"),
                "entity_id": entity,
                "effect_position": [effect.get(c) for c in ("x", "y", "z")] if effect else None,
                "effect_tick": effect["tick"] if effect else None,
                "trajectory": trajectory,
                "trajectory_status": "matched" if trajectory else "unmatched",
                "is_pistol": r["is_pistol"],
                "action_status": "requires reproduction",
            }
        )
    progress("places")
    annotate_places(parser, throws, positions)
    progress("validation")
    for r in rounds:
        end = r["end_tick"] or final_tick
        frame = positions[(positions.tick >= r["start_tick"]) & (positions.tick <= end)]
        equipment = frame[frame.tick == r["freeze_end_tick"]]
        r["equipment"] = [
            {
                "player_id": row["steamid"],
                "player": row["name"],
                "team": row.get("team_clan_name"),
                "side": side(row.get("team_num")),
                "inventory": row.get("inventory"),
                "armor": row.get("armor_value"),
            }
            for row in records(equipment)
        ]
        deaths = [e for e in events.get("player_death", []) if r["freeze_end_tick"] <= e["tick"] <= end]
        r["opening_kill"] = (
            {
                "attacker": deaths[0].get("attacker_name"),
                "victim": deaths[0].get("user_name"),
                "tick": deaths[0]["tick"],
            }
            if deaths
            else None
        )
        r["bomb_events"] = [
            {"kind": name, "tick": e["tick"], "player": e.get("user_name")}
            for name in ("bomb_planted", "bomb_defused", "bomb_exploded")
            for e in events.get(name, [])
            if r["freeze_end_tick"] <= e["tick"] <= end
        ]
        routes = {}
        for owner, group in frame.groupby("steamid"):
            routes[owner] = {
                "name": players.get(owner, owner),
                "points": [
                    [int(t), round(x, 2), round(y, 2), round(z, 2), side(team), bool(alive)]
                    for t, x, y, z, team, alive in group.dropna(subset=["X", "Y", "Z"])[
                        ["tick", "X", "Y", "Z", "team_num", "is_alive"]
                    ].itertuples(index=False, name=None)
                ],
            }
        store.write_timeline(
            r["id"],
            {
                "round_id": r["id"],
                "tick_rate": rate,
                "sample_hz": rate / stride,
                "point_fields": ["tick", "x", "y", "z", "side", "alive"],
                "players": routes,
            },
        )
    progress("formations")
    clans = [e.get("team") for r in rounds for e in r.get("equipment", [])]
    aliases = canonical_teams(clans, source.get("match", ""))
    formations = finalize_formations(extract_formations(parser, rounds, rate), rounds, aliases)
    unmatched = sum(t["trajectory_status"] == "unmatched" for t in throws)
    if unmatched:
        warnings.append(f"{unmatched} throws have no unambiguous projectile match")
    data = {
        "id": match_id,
        "map": header["map_name"],
        "source": source,
        "sha256": sha,
        "parser_version": version("demoparser2"),
        "places_version": PLACES_VERSION,
        "formations_version": FORMATIONS_VERSION,
        "formations": formations,
        "team_aliases": aliases,
        "game_version": header.get("patch_version", "unknown"),
        "tick_rate": rate,
        "route_sample_hz": rate / stride,
        "regulation_half": half,
        "players": [{"id": key, "name": value} for key, value in players.items()],
        "rounds": rounds,
        "throws": throws,
        "warnings": warnings,
        "imported_at": now(),
        "parse_seconds": round(time.monotonic() - started, 2),
    }
    store.save_match(data)
    return data
