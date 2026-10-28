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
META = ("title", "purpose", "reviewed", "reviewer")


def _num(values, n):
    if not isinstance(values, list | tuple) or len(values) < n:
        return None
    if any(not isinstance(v, int | float) or isinstance(v, bool) for v in values[:n]):
        return None
    return [float(v) for v in values[:n]]


def _angle(a, b):
    return abs((a - b + 180) % 360 - 180)


# (map, kind, side), release (x, y), release z, effect (x, y), yaw, pitch
Features = tuple[tuple, tuple[float, float], float, list[float], float, float]


def _features(t: dict) -> Features | None:
    """Parsed comparison fields, or None when a throw can never join a lineup."""
    position, effect = _num(t.get("position"), 3), _num(t.get("effect_position"), 2)
    view = t.get("view")
    if not (position and effect) or not isinstance(view, dict):
        return None
    yaw, pitch = view.get("yaw"), view.get("pitch")
    if not isinstance(yaw, int | float) or not isinstance(pitch, int | float):
        return None
    key = (t.get("map"), t.get("kind"), t.get("side"))
    return key, (position[0], position[1]), position[2], effect, yaw, pitch


def _same(fa: Features | None, fb: Features | None) -> bool:
    """Whether two parsed throws fall within every lineup threshold."""
    if fa is None or fb is None or fa[0] != fb[0]:
        return False
    _, xy_a, z_a, ea, yaw_a, pitch_a = fa
    _, xy_b, z_b, eb, yaw_b, pitch_b = fb
    return (
        math.dist(xy_a, xy_b) <= ORIGIN_RADIUS
        and abs(z_a - z_b) <= ORIGIN_DZ
        and math.dist(ea, eb) <= EFFECT_RADIUS
        and _angle(yaw_a, yaw_b) <= ANGLE_DEG
        and _angle(pitch_a, pitch_b) <= ANGLE_DEG
    )


def same_lineup(a: dict, b: dict) -> bool:
    """Convenience wrapper over the parsed comparison used by cluster()."""
    return _same(_features(a), _features(b))


def _order(t):
    return (str(t.get("match_id")), t.get("tick") or 0, str(t.get("id")))


def _describe(group_id, source, members, rows, meta):
    first = rows[members[0]]
    return {
        "id": group_id,
        "source": source,
        "members": members,
        "players": sorted({str(rows[m].get("player") or "") for m in members} - {""}),
        "map": first.get("map"),
        "kind": first.get("kind"),
        "side": first.get("side"),
        **{k: meta.get(k, False if k == "reviewed" else "") for k in META},
    }


def cluster(throws: list[dict], stored: list[dict]) -> list[dict]:
    rows = {t["id"]: t for t in throws}
    groups, assigned = [], set()
    meta = {v["id"]: v for v in stored}
    for record in stored:
        if record.get("source") != "manual":
            continue
        members = sorted(
            (m for m in record.get("members", []) if m in rows and m not in assigned),
            key=lambda m: _order(rows[m]),
        )
        if members:
            assigned.update(members)
            groups.append(_describe(record["id"], "manual", members, rows, record))
    auto: list[list[str]] = []
    # Groups are indexed by the grid cell of their first member's release point, so each throw
    # only checks nearby groups; the result is the same as scanning every group in order.
    index: dict[tuple, list[int]] = {}
    # Parsed once per throw: the pair checks below run about a million times on a full library.
    todo = sorted((t for t in throws if t["id"] not in assigned), key=_order)
    features = {t["id"]: _features(t) for t in todo}
    for row in todo:
        pos = _num(row.get("position"), 2)
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
        mine = features[row["id"]]
        if cell and mine is not None:
            nearby = sorted(
                g
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for g in index.get((*cell[:3], cell[3] + dx, cell[4] + dy), ())
            )
            home = next((g for g in nearby if _same(features[auto[g][0]], mine)), None)
        if home is None:
            auto.append([row["id"]])
            if cell:
                index.setdefault(cell, []).append(len(auto) - 1)
        else:
            auto[home].append(row["id"])
    for members in auto:
        group_id = "auto-" + hashlib.sha1(members[0].encode()).hexdigest()[:12]
        groups.append(_describe(group_id, "auto", members, rows, meta.get(group_id, {})))
    return groups
