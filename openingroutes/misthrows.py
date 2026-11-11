"""Flag botched grenades so they stay out of lineups, lessons, plans and exports.

Only strong signals are automatic, and only for one-off throws: a throw that someone
repeated is deliberate, however odd it looks (pros throw an HE straight up from the Mirage
window room, and it lands where it was released). A curator's decision always wins.

Flags are derived on read because they depend on the variant groups; only the decisions are
stored. The raw throw is never removed: it still shows on its round's timeline, and CT
research keeps counting it, because that measures what a team threw from where.
"""

import math
import statistics

from . import variants as V

# A smoke or HE that takes effect this close (XY units) to where it was released bounced
# back off a wall or was dropped at the thrower's feet. Flashes are left out: popping one
# overhead is a normal way to use it.
BOUNCE_RADIUS = 200.0
BOUNCE_KINDS = ("smoke", "he")
# Aimed this close to straight up or down (degrees of pitch), a grenade comes back to where
# it was released by design.
STEEP_PITCH = 80.0
# A one-off throw from the same spot with the same aim as an established lineup, landing at
# least this far (XY units) from that lineup's median landing point.
OUTLIER_RADIUS = 750.0
# Uses of a lineup before it counts as established.
OUTLIER_MIN_MEMBERS = 3
# Molotovs and incendiaries have no recorded landing point, so no rule applies to them.
KINDS = ("smoke", "flash", "he")
# Bump when a rule changes so cached flags are rebuilt.
RULES_VERSION = 1


def hidden(throw_id: str, basis: dict | None, decisions: dict, protected: set) -> bool:
    """Manual decisions first; the rules never hide a throw that published content uses."""
    decision = (decisions.get(throw_id) or {}).get("decision")
    if decision:
        return decision == "misthrow"
    return bool(basis) and throw_id not in protected


def _one_off(group: dict) -> bool:
    """A repeated throw, or one a curator grouped by hand, is deliberate."""
    return group["source"] == "auto" and len(group["members"]) == 1


def bounce(throw: dict) -> dict | None:
    if throw.get("kind") not in BOUNCE_KINDS:
        return None
    release, effect = V.numbers(throw.get("position"), 2), V.numbers(throw.get("effect_position"), 2)
    pitch = (throw.get("view") or {}).get("pitch")
    if not (release and effect) or (isinstance(pitch, int | float) and abs(pitch) >= STEEP_PITCH):
        return None
    distance = math.dist(release, effect)
    return {"rule": "bounce_back", "distance": round(distance)} if distance < BOUNCE_RADIUS else None


def _cell(parsed: V.Features, dx: int = 0, dy: int = 0) -> tuple:
    x, y = parsed[1]
    return (parsed[0], math.floor(x / V.ORIGIN_RADIUS) + dx, math.floor(y / V.ORIGIN_RADIUS) + dy)


def _outliers(rows: dict, groups: list[dict]) -> dict[str, dict]:
    """One-off throws released like an established lineup but landing far from it."""
    established: dict[tuple, list] = {}
    for group in groups:
        parsed = [p for m in group["members"] if (p := V.features(rows[m]))]
        if len(parsed) < OUTLIER_MIN_MEMBERS or group["kind"] not in KINDS:
            continue
        median = [statistics.median(p[3][axis] for p in parsed) for axis in (0, 1)]
        established.setdefault(_cell(parsed[0]), []).append((parsed[0], median, group["id"]))
    found = {}
    for group in filter(_one_off, groups):
        mine = V.features(rows[group["members"][0]])
        if mine is None:
            continue
        near = [
            (math.dist(median, mine[3]), group_id)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            for anchor, median, group_id in established.get(_cell(mine, dx, dy), ())
            if V.same_release(anchor, mine)
        ]
        if near and min(near)[0] >= OUTLIER_RADIUS:
            distance, group_id = min(near)
            found[group["members"][0]] = {
                "rule": "variant_outlier",
                "distance": round(distance),
                "variant_id": group_id,
            }
    return found


def evaluate(
    throws: list[dict], stored: list[dict], decisions: dict, protected: set
) -> tuple[list[dict], dict[str, dict]]:
    """Variant groups without the misthrows, and the rule that matched per throw id.

    A matched rule is reported even when a "keep" decision or published content keeps the
    throw. Throws a curator marked are left out before the rules run.
    """
    kept = [t for t in throws if (decisions.get(t["id"]) or {}).get("decision") != "misthrow"]
    rows = {t["id"]: t for t in kept}
    groups = V.group(kept, stored)
    auto = _outliers(rows, groups)
    for group in filter(_one_off, groups):
        if basis := bounce(rows[group["members"][0]]):
            auto[group["members"][0]] = basis
    # Only one-off throws match a rule, so dropping their groups changes no other group.
    groups = [
        g for g in groups if not hidden(g["members"][0], auto.get(g["members"][0]), decisions, protected)
    ]
    return groups, auto


def status(throw_id: str, auto: dict, decisions: dict, protected: set) -> dict | None:
    """What the studio shows for a throw; None when no rule matched and nothing was decided."""
    basis, record = auto.get(throw_id), decisions.get(throw_id) or {}
    if not basis and not record:
        return None
    flagged = hidden(throw_id, basis, decisions, protected)
    return {
        "flagged": flagged,
        "source": "manual" if record.get("decision") else "auto",
        "auto": basis,
        "note": record.get("note", ""),
        "reviewer": record.get("reviewer", ""),
        "at": record.get("at", ""),
        # A rule matched a throw that a published lesson or plan uses: shown, never hidden.
        "conflict": bool(basis) and not flagged and not record.get("decision"),
    }
