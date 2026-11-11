"""Group real throws into candidate lineup variants; manual merges/splits always win.

Auto grouping is a candidate only: same map, grenade type and side, close release
position, close view angles and close effect position. A shared landing point alone
never merges two throws, and throws without an effect position stay on their own.
"""

import hashlib
import math

ORIGIN_RADIUS = 96.0
ORIGIN_DZ = 64.0
EFFECT_RADIUS = 160.0
ANGLE_DEG = 3.0
# Bump when the grouping rule changes so cached groups are rebuilt.
VARIANTS_VERSION = 1
META = ("title", "purpose", "reviewed", "reviewer")


def numbers(values, n):
    if not isinstance(values, list | tuple) or len(values) < n:
        return None
    if any(not isinstance(v, int | float) or isinstance(v, bool) for v in values[:n]):
        return None
    return [float(v) for v in values[:n]]


def _angle(a, b):
    return abs((a - b + 180) % 360 - 180)


# (map, kind, side), release (x, y), release z, effect (x, y), yaw, pitch
Features = tuple[tuple, tuple[float, float], float, list[float], float, float]


def features(t: dict) -> Features | None:
    """Parsed comparison fields, or None when a throw can never join a lineup."""
    position, effect = numbers(t.get("position"), 3), numbers(t.get("effect_position"), 2)
    view = t.get("view")
    if not (position and effect) or not isinstance(view, dict):
        return None
    yaw, pitch = view.get("yaw"), view.get("pitch")
    if not isinstance(yaw, int | float) or not isinstance(pitch, int | float):
        return None
    key = (t.get("map"), t.get("kind"), t.get("side"))
    return key, (position[0], position[1]), position[2], effect, yaw, pitch


def same_release(fa: Features, fb: Features) -> bool:
    """Same map, grenade and side, thrown from the same spot with the same aim."""
    return (
        fa[0] == fb[0]
        and math.dist(fa[1], fb[1]) <= ORIGIN_RADIUS
        and abs(fa[2] - fb[2]) <= ORIGIN_DZ
        and _angle(fa[4], fb[4]) <= ANGLE_DEG
        and _angle(fa[5], fb[5]) <= ANGLE_DEG
    )


def _same(fa: Features | None, fb: Features | None) -> bool:
    """Whether two parsed throws fall within every lineup threshold."""
    if fa is None or fb is None:
        return False
    return same_release(fa, fb) and math.dist(fa[3], fb[3]) <= EFFECT_RADIUS


def same_lineup(a: dict, b: dict) -> bool:
    """Convenience wrapper over the parsed comparison used by cluster()."""
    return _same(features(a), features(b))


def _order(t):
    return (str(t.get("match_id")), t.get("tick") or 0, str(t.get("id")))


def _describe(group_id, source, members, rows):
    first = rows[members[0]]
    return {
        "id": group_id,
        "source": source,
        "members": members,
        "players": sorted({str(rows[m].get("player") or "") for m in members} - {""}),
        "map": first.get("map"),
        "kind": first.get("kind"),
        "side": first.get("side"),
    }


def _auto_id(throw_id: str) -> str:
    return "auto-" + hashlib.sha1(throw_id.encode()).hexdigest()[:12]


def with_meta(groups: list[dict], stored: list[dict]) -> list[dict]:
    """Curator titles and review flags, applied on read so labelling never regroups."""
    meta = {v["id"]: v for v in stored}
    current = {g["id"] for g in groups}
    # An automatic group is named after its earliest throw, so a later import that adds an
    # earlier throw renames it. Its label then follows the throw it was first given to.
    moved = {k: v for k, v in meta.items() if v.get("source") == "auto" and k not in current}

    def label(group):
        if group["id"] in meta or not moved:
            return meta.get(group["id"], {})
        return next((moved[k] for m in group["members"] if (k := _auto_id(m)) in moved), {})

    return [
        {**g, **{k: record.get(k, False if k == "reviewed" else "") for k in META}}
        for g in groups
        for record in [label(g)]
    ]


def cluster(throws: list[dict], stored: list[dict]) -> list[dict]:
    return with_meta(group(throws, stored), stored)


def group(throws: list[dict], stored: list[dict]) -> list[dict]:
    """Group membership only; depends on the throws' grouping fields and the manual records."""
    rows = {t["id"]: t for t in throws}
    groups, assigned = [], set()
    for record in stored:
        if record.get("source") != "manual":
            continue
        members = sorted(
            (m for m in record.get("members", []) if m in rows and m not in assigned),
            key=lambda m: _order(rows[m]),
        )
        if members:
            assigned.update(members)
            groups.append(_describe(record["id"], "manual", members, rows))
    auto: list[list[str]] = []
    # Groups are indexed by the grid cell of their first member's release point, so each throw
    # only checks nearby groups; the result is the same as scanning every group in order.
    index: dict[tuple, list[int]] = {}
    # Parsed once per throw: the pair checks below run about a million times on a full library.
    todo = sorted((t for t in throws if t["id"] not in assigned), key=_order)
    parsed = {t["id"]: features(t) for t in todo}
    for row in todo:
        pos = numbers(row.get("position"), 2)
        cell = None
        if pos:
            cell = (
                row.get("map"),
                row.get("kind"),
                row.get("side"),
                math.floor(pos[0] / ORIGIN_RADIUS),
                math.floor(pos[1] / ORIGIN_RADIUS),
            )
        home = None
        mine = parsed[row["id"]]
        if cell and mine is not None:
            nearby = sorted(
                g
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for g in index.get((*cell[:3], cell[3] + dx, cell[4] + dy), ())
            )
            home = next((g for g in nearby if _same(parsed[auto[g][0]], mine)), None)
        if home is None:
            auto.append([row["id"]])
            if cell:
                index.setdefault(cell, []).append(len(auto) - 1)
        else:
            auto[home].append(row["id"])
    for members in auto:
        groups.append(_describe(_auto_id(members[0]), "auto", members, rows))
    return groups
