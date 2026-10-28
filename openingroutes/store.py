"""Transactional metadata; dense timelines live in separate per-round files."""

import gzip
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

TABLES = {"matches", "teachings", "plans", "round_reviews", "jobs", "variants", "places"}


def now():
    return datetime.now(UTC).isoformat()


def _finite(value):
    """JSON responses reject inf/NaN (e.g. Calinski-Harabasz on perfectly separated clusters)."""
    if isinstance(value, float) and (value != value or value in (float("inf"), float("-inf"))):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_finite(v) for v in value]
    return value


def compact_formation(formation: dict) -> dict:
    return {
        "ct_team": formation.get("ct_team"),
        "t_team": formation.get("t_team"),
        "complete": formation.get("complete"),
        "context": formation.get("context", {}),
        "snapshots": [
            {
                "second": s["second"],
                "ct": [
                    {k: p.get(k) for k in ("player", "place", "x", "y", "z", "alive", "equip")}
                    for p in s["ct"]
                ],
            }
            for s in formation.get("snapshots", [])
        ],
    }


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in ("uploads", "timelines", "media", "exports", "logs"):
            (self.root / directory).mkdir(exist_ok=True)
        self.db = self.root / "library.sqlite"
        with self.connect() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS matches(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS teachings(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS round_reviews(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS variants(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS places(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY, entity TEXT, data TEXT, at TEXT);
                PRAGMA user_version=2;
            """)

    def connect(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def put(self, table: str, key: str, data: dict):
        if table not in TABLES:
            raise ValueError("Invalid collection")
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
        with self.connect() as c:
            c.execute(f"INSERT OR REPLACE INTO {table}(id,data) VALUES(?,?)", (key, encoded))
            if table != "jobs":
                c.execute("INSERT INTO revisions(entity,data,at) VALUES(?,?,?)", (key, encoded, now()))

    def delete(self, table: str, key: str):
        if table not in TABLES:
            raise ValueError("Invalid collection")
        with self.connect() as c:
            c.execute(f"DELETE FROM {table} WHERE id=?", (key,))
            c.execute("INSERT INTO revisions(entity,data,at) VALUES(?,?,?)", (key, '{"deleted":true}', now()))

    def all(self, table):
        if table not in TABLES:
            raise ValueError("Invalid collection")
        with self.connect() as c:
            return {key: json.loads(data) for key, data in c.execute(f"SELECT id,data FROM {table}")}

    def save_match(self, data):
        self.put("matches", data["id"], data)

    def save_teaching(self, throw_id, teaching):
        self.put("teachings", throw_id, teaching)

    def place_overrides(self, field: str = "label"):
        overrides: dict[str, dict[str, str]] = {}
        for key, value in self.all("places").items():
            map_name, _, place = key.partition(":")
            if value.get(field):
                overrides.setdefault(map_name, {})[place] = value[field]
        return overrides

    _pattern_cache: dict = {}

    def ct_patterns(self, matches, rounds_by_id, throws):
        """TAGNet-style CT pattern analysis per map, cached on the inputs that affect it."""
        import hashlib

        from .patterns import ANALYSIS_VERSION, analyze_map

        areas = self.place_overrides("area")
        by_map: dict[str, list] = {}
        for match in matches:
            if not match["source"].get("verified"):
                continue
            for round_id, formation in (match.get("formations") or {}).items():
                row = rounds_by_id.get(round_id)
                if row is None or row.get("excluded"):
                    continue
                by_map.setdefault(match["map"], []).append(formation)
        key = hashlib.sha256(
            json.dumps(
                [
                    ANALYSIS_VERSION,
                    sorted(
                        (m["id"], m.get("formations_version")) for m in matches if m["source"].get("verified")
                    ),
                    areas,
                    self.place_overrides(),
                    sorted(r for r, v in rounds_by_id.items() if v.get("excluded")),
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        cached = Store._pattern_cache.get(str(self.db))
        if cached and cached[0] == key:
            return cached[1]
        # The analysis takes minutes on a full library, so it is also kept on disk.
        disk = self.root / "cache" / "ct_patterns.json"
        try:
            stored = json.loads(disk.read_text(encoding="utf-8"))
            if stored.get("key") == key:
                Store._pattern_cache[str(self.db)] = (key, stored["result"])
                return stored["result"]
        except (OSError, ValueError, AttributeError):
            pass
        result = {
            map_name: analyze_map(
                map_name,
                sorted(f, key=lambda x: x["round_id"]),
                [t for t in throws if t.get("map") == map_name],
                areas,
            )
            for map_name, f in sorted(by_map.items())
        }
        result = _finite(json.loads(json.dumps(result)))
        Store._pattern_cache[str(self.db)] = (key, result)
        try:
            disk.parent.mkdir(exist_ok=True)
            tmp = disk.with_suffix(".tmp")
            tmp.write_text(json.dumps({"key": key, "result": result}), encoding="utf-8")
            tmp.replace(disk)
        except OSError:
            pass
        return result

    def catalog(self):
        from .domain import effective_round, teaching_gaps
        from .places import GENERIC, place_label
        from .variants import cluster

        teachings, reviews = self.all("teachings"), self.all("round_reviews")
        overrides = self.place_overrides()
        catalog = {
            "schema_version": 1,
            "matches": [],
            "rounds": [],
            "throws": [],
            "plans": list(self.all("plans").values()),
        }
        for match in self.all("matches").values():
            catalog["matches"].append(
                {k: v for k, v in match.items() if k not in ("rounds", "throws", "formations")}
            )
            formations = match.get("formations") or {}
            for row in match["rounds"]:
                entry = effective_round(row, reviews.get(row["id"], {}))
                if row["id"] in formations:
                    entry["formation"] = compact_formation(formations[row["id"]])
                catalog["rounds"].append(entry)
            for row in match["throws"]:
                t = teachings.get(row["id"], {})
                catalog["throws"].append(
                    {
                        **row,
                        "origin_area": place_label(row.get("map"), row.get("origin_place"), overrides),
                        "effect_area": place_label(row.get("map"), row.get("effect_place"), overrides),
                        "teaching": t,
                        "gaps": teaching_gaps(t, source_verified=match["source"]["verified"]),
                    }
                )
        variants = cluster(catalog["throws"], list(self.all("variants").values()))
        owner = {m: v["id"] for v in variants for m in v["members"]}
        for row in catalog["throws"]:
            row["variant_id"] = owner.get(row["id"])
        catalog["variants"] = variants
        maps = {m["map"] for m in catalog["matches"]} | set(overrides)
        catalog["places"] = {m: {**GENERIC, **overrides.get(m, {})} for m in sorted(maps)}
        from .patterns import DEFAULT_MACRO

        area_overrides = self.place_overrides("area")
        catalog["place_areas"] = {
            m: {**DEFAULT_MACRO.get(m, {}), **area_overrides.get(m, {})} for m in sorted(maps)
        }
        rounds_by_id = {r["id"]: r for r in catalog["rounds"]}
        analyses = self.ct_patterns(list(self.all("matches").values()), rounds_by_id, catalog["throws"])
        catalog["ct_patterns"] = {}
        for map_name, analysis in analyses.items():
            catalog["ct_patterns"][map_name] = {k: v for k, v in analysis.items() if k != "assignments"}
            for round_id, pattern in analysis.get("assignments", {}).items():
                rounds_by_id[round_id]["ct_pattern"] = pattern
        return catalog

    def timeline(self, round_id):
        path = self.root / "timelines" / f"{round_id}.json.gz"
        if not path.exists():
            return None
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)

    def write_timeline(self, round_id, data):
        destination = self.root / "timelines" / f"{round_id}.json.gz"
        with gzip.open(destination.with_suffix(".tmp"), "wt", encoding="utf-8") as f:
            json.dump(data, f, allow_nan=False, separators=(",", ":"))
        destination.with_suffix(".tmp").replace(destination)
