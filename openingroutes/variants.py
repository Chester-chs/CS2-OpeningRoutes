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


def same_lineup(a: dict, b: dict) -> bool:
    if (a.get("map"), a.get("kind"), a.get("side")) != (b.get("map"), b.get("kind"), b.get("side")):
        return False
    pa, pb = _num(a.get("position"), 3), _num(b.get("position"), 3)
    ea, eb = _num(a.get("effect_position"), 2), _num(b.get("effect_position"), 2)
    va, vb = a.get("view") or {}, b.get("view") or {}
    angles = [va.get("yaw"), vb.get("yaw"), va.get("pitch"), vb.get("pitch")]
    if not (pa and pb and ea and eb) or any(not isinstance(x, int | float) for x in angles):
        return False
    return (
        math.dist(pa[:2], pb[:2]) <= ORIGIN_RADIUS
        and abs(pa[2] - pb[2]) <= ORIGIN_DZ
        and math.dist(ea, eb) <= EFFECT_RADIUS
        and _angle(angles[0], angles[1]) <= ANGLE_DEG
        and _angle(angles[2], angles[3]) <= ANGLE_DEG
    )


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
    for row in sorted((t for t in throws if t["id"] not in assigned), key=_order):
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
        if cell:
            nearby = sorted(
                g
                for dx in (-1, 0, 1)
                for dy in (-1, 0, 1)
                for g in index.get((*cell[:3], cell[3] + dx, cell[4] + dy), ())
            )
            home = next((g for g in nearby if same_lineup(rows[auto[g][0]], row)), None)
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
