"""Transactional metadata; dense timelines live in separate per-round files."""

import gzip
import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

TABLES = {"matches", "teachings", "plans", "round_reviews", "jobs", "variants", "places", "misthrows"}


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


def _throw_row(row: dict, match: dict, teachings: dict, overrides: dict) -> dict:
    from .domain import teaching_gaps
    from .places import place_label

    t = teachings.get(row["id"], {})
    return {
        **row,
        "origin_area": place_label(row.get("map"), row.get("origin_place"), overrides),
        "effect_area": place_label(row.get("map"), row.get("effect_place"), overrides),
        "teaching": t,
        "gaps": teaching_gaps(t, source_verified=match["source"]["verified"]),
    }


def _published(teachings: dict) -> set:
    return {key for key, t in teachings.items() if t.get("status") == "published"}


def _mark(rows: list, groups: list, auto: dict, decisions: dict, protected: set):
    """Give each throw its variant and, where a rule matched or a curator decided, its misthrow state."""
    from .misthrows import status

    owner = {m: g["id"] for g in groups for m in g["members"]}
    for row in rows:
        row["variant_id"] = owner.get(row["id"])
        state = status(row["id"], auto, decisions, protected)
        if state:
            row["misthrow"] = state
            if state["flagged"]:
                row["gaps"] = [*row["gaps"], "misthrow"]


PREVIEW_POINTS = 12  # enough for the card thumbnail; the full path is fetched with the throw


def _preview(points: list) -> list:
    if len(points) <= PREVIEW_POINTS:
        chosen = points
    else:
        step = (len(points) - 1) / (PREVIEW_POINTS - 1)
        chosen = [points[round(i * step)] for i in range(PREVIEW_POINTS)]
    return [[round(v) for v in p] for p in chosen]


class Store:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        for directory in ("uploads", "timelines", "media", "exports", "logs"):
            (self.root / directory).mkdir(exist_ok=True)
        self.db = self.root / "library.sqlite"
        with closing(self.connect()) as c, c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS matches(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS teachings(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS round_reviews(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS variants(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS places(id TEXT PRIMARY KEY, data TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS misthrows(id TEXT PRIMARY KEY, data TEXT NOT NULL);
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
        with closing(self.connect()) as c, c:
            c.execute(f"INSERT OR REPLACE INTO {table}(id,data) VALUES(?,?)", (key, encoded))
            if table != "jobs":
                c.execute("INSERT INTO revisions(entity,data,at) VALUES(?,?,?)", (key, encoded, now()))

    def delete(self, table: str, key: str):
        if table not in TABLES:
            raise ValueError("Invalid collection")
        with closing(self.connect()) as c, c:
            c.execute(f"DELETE FROM {table} WHERE id=?", (key,))
            c.execute("INSERT INTO revisions(entity,data,at) VALUES(?,?,?)", (key, '{"deleted":true}', now()))

    def all(self, table):
        if table not in TABLES:
            raise ValueError("Invalid collection")
        with closing(self.connect()) as c, c:
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

    def _ct_key(self, matches, rounds_by_id):
        """Only match metadata and round exclusions: the key never needs the heavy formations."""
        import hashlib

        from .patterns import ANALYSIS_VERSION

        return hashlib.sha256(
            json.dumps(
                [
                    ANALYSIS_VERSION,
                    sorted(
                        (m["id"], m.get("formations_version")) for m in matches if m["source"].get("verified")
                    ),
                    self.place_overrides("area"),
                    self.place_overrides(),
                    sorted(r for r, v in rounds_by_id.items() if v.get("excluded")),
                ],
                sort_keys=True,
            ).encode()
        ).hexdigest()

    def _ct_cached(self, key):
        cached = Store._pattern_cache.get(str(self.db))
        if cached and cached[0] == key:
            return cached[1]
        # The analysis takes minutes on a full library, so it is also kept on disk.
        try:
            stored = json.loads((self.root / "cache" / "ct_patterns.json").read_text(encoding="utf-8"))
            if stored.get("key") == key:
                Store._pattern_cache[str(self.db)] = (key, stored["result"])
                return stored["result"]
        except (OSError, ValueError, AttributeError):
            pass
        return None

    def ct_patterns(self, matches, rounds_by_id, throws):
        """TAGNet-style CT pattern analysis per map, cached on the inputs that affect it."""
        from .patterns import analyze_map

        areas = self.place_overrides("area")
        key = self._ct_key(matches, rounds_by_id)
        cached = self._ct_cached(key)
        if cached is not None:
            return cached
        by_map: dict[str, list] = {}
        for match in matches:
            if not match["source"].get("verified"):
                continue
            for round_id, formation in (match.get("formations") or {}).items():
                row = rounds_by_id.get(round_id)
                if row is None or row.get("excluded"):
                    continue
                by_map.setdefault(match["map"], []).append(formation)
        disk = self.root / "cache" / "ct_patterns.json"
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
        from .domain import effective_round
        from .misthrows import evaluate
        from .variants import with_meta

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
            catalog["throws"].extend(_throw_row(row, match, teachings, overrides) for row in match["throws"])
        stored = list(self.all("variants").values())
        decisions, protected = self.all("misthrows"), _published(teachings)
        groups, auto = evaluate(catalog["throws"], stored, decisions, protected)
        _mark(catalog["throws"], groups, auto, decisions, protected)
        catalog["variants"] = with_meta(groups, stored)
        catalog.update(self._vocabulary({m["map"] for m in catalog["matches"]}, overrides))
        rounds_by_id = {r["id"]: r for r in catalog["rounds"]}
        analyses = self.ct_patterns(list(self.all("matches").values()), rounds_by_id, catalog["throws"])
        catalog["ct_patterns"] = {}
        for map_name, analysis in analyses.items():
            catalog["ct_patterns"][map_name] = {k: v for k, v in analysis.items() if k != "assignments"}
            for round_id, pattern in analysis.get("assignments", {}).items():
                rounds_by_id[round_id]["ct_pattern"] = pattern
        return catalog

    def _vocabulary(self, maps, overrides):
        from .patterns import DEFAULT_MACRO
        from .places import GENERIC

        maps = set(maps) | set(overrides)
        area_overrides = self.place_overrides("area")
        return {
            "places": {m: {**GENERIC, **overrides.get(m, {})} for m in sorted(maps)},
            "place_areas": {
                m: {**DEFAULT_MACRO.get(m, {}), **area_overrides.get(m, {})} for m in sorted(maps)
            },
        }

    # The studio reads the library a map at a time. Results are memoized per library
    # revision: every put/delete (the import worker's included) writes a revision row.
    _memo: dict = {}
    _variant_cache: dict = {}

    def revision(self) -> int:
        with closing(self.connect()) as c, c:
            return c.execute("SELECT COALESCE(MAX(id), 0) FROM revisions").fetchone()[0]

    def _memoized(self, name, build):
        key = (str(self.db), name)
        revision = self.revision()
        cached = Store._memo.get(key)
        if cached and cached[0] == revision:
            return cached[1]
        value = build()
        Store._memo[key] = (revision, value)
        return value

    def _light_matches(self):
        """Match metadata, rounds and throw counts, without parsing the throws in Python."""
        with closing(self.connect()) as c, c:
            rows = c.execute(
                "SELECT json_remove(data,'$.rounds','$.throws','$.formations'),"
                " json_extract(data,'$.rounds'), json_array_length(data,'$.throws') FROM matches"
            ).fetchall()
        return [(json.loads(meta), json.loads(rounds or "[]"), count or 0) for meta, rounds, count in rows]

    def _map_matches(self, map_name):
        with closing(self.connect()) as c, c:
            rows = c.execute(
                "SELECT data FROM matches WHERE json_extract(data,'$.map')=?", (map_name,)
            ).fetchall()
        return [json.loads(data) for (data,) in rows]

    @staticmethod
    def _all_rounds(light, reviews):
        from .domain import effective_round

        return [effective_round(row, reviews.get(row["id"], {})) for _, rounds, _ in light for row in rounds]

    def summary(self):
        """Everything but throws, variants and formations: what the studio needs to open."""
        return self._memoized("summary", self._build_summary)

    def _build_summary(self):
        from .domain import teaching_gaps

        light = self._light_matches()
        verified = {meta["id"]: meta["source"].get("verified") for meta, _, _ in light}
        map_of = {meta["id"]: meta["map"] for meta, _, _ in light}
        complete: dict[str, int] = {}
        for throw_id, teaching in self.all("teachings").items():
            match_id = throw_id.partition("-t")[0]
            if match_id in map_of and not teaching_gaps(teaching, source_verified=verified[match_id]):
                complete[map_of[match_id]] = complete.get(map_of[match_id], 0) + 1
        maps: dict[str, dict] = {}
        for meta, rounds, count in light:
            row = maps.setdefault(
                meta["map"],
                {"map": meta["map"], "matches": 0, "rounds": 0, "throws": 0, "complete": 0},
            )
            row["matches"] += 1
            row["rounds"] += len(rounds)
            row["throws"] += count
            row["complete"] = complete.get(meta["map"], 0)
        return {
            "schema_version": 1,
            "matches": [meta for meta, _, _ in light],
            "rounds": self._all_rounds(light, self.all("round_reviews")),
            "throws": [],
            "variants": [],
            "plans": list(self.all("plans").values()),
            "maps": [maps[m] for m in sorted(maps)],
            "ct_patterns": {},
            **self._vocabulary(maps, self.place_overrides()),
        }

    def map_slice(self, map_name):
        """One map's throws (with a small trajectory preview), rounds with formations, variants, CT."""
        return self._memoized(f"map:{map_name}", lambda: self._build_slice(map_name))

    def _build_slice(self, map_name):
        from .domain import effective_round

        matches = self._map_matches(map_name)
        if not matches:
            return None
        teachings, reviews = self.all("teachings"), self.all("round_reviews")
        overrides = self.place_overrides()
        throws, rounds = [], []
        for match in matches:
            formations = match.get("formations") or {}
            for row in match["rounds"]:
                entry = effective_round(row, reviews.get(row["id"], {}))
                if row["id"] in formations:
                    entry["formation"] = compact_formation(formations[row["id"]])
                rounds.append(entry)
            throws.extend(_throw_row(row, match, teachings, overrides) for row in match["throws"])
        decisions, protected = self.all("misthrows"), _published(teachings)
        variants, auto = self.map_variants(map_name, throws, decisions, protected)
        _mark(throws, variants, auto, decisions, protected)
        for row in throws:
            row["trajectory_preview"] = _preview(row.pop("trajectory", None) or [])
        analysis = self._ct_for_map(map_name, reviews)
        if analysis:
            by_id = {r["id"]: r for r in rounds}
            for round_id, pattern in analysis.get("assignments", {}).items():
                if round_id in by_id:
                    by_id[round_id]["ct_pattern"] = pattern
            analysis = {k: v for k, v in analysis.items() if k != "assignments"}
        return {
            "map": map_name,
            "throws": throws,
            "rounds": rounds,
            "variants": variants,
            "ct_patterns": {map_name: analysis} if analysis else {},
        }

    def _ct_for_map(self, map_name, reviews):
        light = self._light_matches()
        rounds_by_id = {r["id"]: r for r in self._all_rounds(light, reviews)}
        result = self._ct_cached(self._ct_key([meta for meta, _, _ in light], rounds_by_id))
        if result is None:
            # Cache miss (e.g. right after an import): the analysis needs every map's formations.
            result = self.ct_patterns(
                list(self.all("matches").values()), rounds_by_id, self.catalog()["throws"]
            )
        return result.get(map_name)

    def map_variants(self, map_name, throws, decisions, protected):
        """One map's variant groups and matched misthrow rules, cached on disk on their inputs."""
        import hashlib

        from . import misthrows as M
        from . import variants as V

        stored = list(self.all("variants").values())
        features = sorted(
            (
                [t["id"], t.get("match_id"), t.get("tick"), t.get("map"), t.get("kind"), t.get("side")]
                + [t.get("player"), t.get("position"), t.get("effect_position"), t.get("view")]
                for t in throws
            ),
            key=lambda r: str(r[0]),
        )
        # Stored order matters when manual records overlap, so it is kept.
        manual = [(v["id"], v.get("members")) for v in stored if v.get("source") == "manual"]
        thresholds = [V.ORIGIN_RADIUS, V.ORIGIN_DZ, V.EFFECT_RADIUS, V.ANGLE_DEG]
        rules = [M.RULES_VERSION, M.BOUNCE_RADIUS, M.OUTLIER_RADIUS, M.OUTLIER_MIN_MEMBERS, M.KINDS]
        ids = {t["id"] for t in throws}
        decided = sorted((i, d.get("decision")) for i, d in decisions.items() if i in ids)
        key = hashlib.sha256(
            json.dumps(
                [V.VARIANTS_VERSION, thresholds, rules, map_name, features, manual, decided]
                + [sorted(protected & ids)],
                sort_keys=True,
            ).encode()
        ).hexdigest()
        memory = Store._variant_cache.get((str(self.db), map_name))
        if memory and memory[0] == key:
            return V.with_meta(memory[1], stored), memory[2]
        disk = self.root / "cache" / "variants.json"
        try:
            cached = json.loads(disk.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            cached = {}
        if not isinstance(cached, dict):
            cached = {}
        entry = cached.get(map_name)
        if isinstance(entry, dict) and entry.get("key") == key:
            groups, auto = entry["groups"], entry["auto"]
        else:
            groups, auto = M.evaluate(throws, stored, decisions, protected)
            cached[map_name] = {"key": key, "groups": groups, "auto": auto}
            try:
                disk.parent.mkdir(exist_ok=True)
                tmp = disk.with_suffix(".tmp")
                tmp.write_text(json.dumps(cached), encoding="utf-8")
                tmp.replace(disk)
            except OSError:
                pass
        Store._variant_cache[(str(self.db), map_name)] = (key, groups, auto)
        return V.with_meta(groups, stored), auto

    def locate(self, throw_id):
        """The raw throw and its match; reads one match when the id starts with its match id."""

        def find(row):
            match = json.loads(row[0]) if row else None
            found = next((t for t in match["throws"] if t["id"] == throw_id), None) if match else None
            return (found, match) if found else (None, None)

        with closing(self.connect()) as c, c:
            hit = find(
                c.execute("SELECT data FROM matches WHERE id=?", (throw_id.partition("-t")[0],)).fetchone()
            )
            if hit[0] is None:
                # ids from early imports do not always start with their match id
                hit = find(
                    c.execute(
                        "SELECT m.data FROM matches m, json_each(m.data,'$.throws') j"
                        " WHERE json_extract(j.value,'$.id')=? LIMIT 1",
                        (throw_id,),
                    ).fetchone()
                )
        return hit

    def throw(self, throw_id):
        """The full row, trajectory included, as the full catalog would give it."""
        raw, match = self.locate(throw_id)
        if raw is None:
            return None
        row = _throw_row(raw, match, self.all("teachings"), self.place_overrides())
        light = next((t for t in self.map_slice(match["map"])["throws"] if t["id"] == throw_id), {})
        row["variant_id"] = light.get("variant_id")
        row.update({k: light[k] for k in ("misthrow", "gaps") if k in light})
        return row

    def throws_by_id(self, ids):
        """Light rows, as in a map slice, for throws on any map."""
        wanted, maps = set(ids), set()
        map_of = {meta["id"]: meta["map"] for meta, _, _ in self._light_matches()}
        for throw_id in wanted:
            map_name = map_of.get(throw_id.partition("-t")[0])
            if map_name is None:
                _, match = self.locate(throw_id)
                map_name = match["map"] if match else None
            if map_name:
                maps.add(map_name)
        return [t for m in sorted(maps) for t in self.map_slice(m)["throws"] if t["id"] in wanted]

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
