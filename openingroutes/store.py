"""Transactional metadata; dense timelines live in separate per-round files."""

import gzip
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

TABLES = {"matches", "teachings", "plans", "round_reviews", "jobs", "variants", "places"}


def now():
    return datetime.now(UTC).isoformat()


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

    def place_overrides(self):
        overrides: dict[str, dict[str, str]] = {}
        for key, value in self.all("places").items():
            map_name, _, place = key.partition(":")
            overrides.setdefault(map_name, {})[place] = value["label"]
        return overrides

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
            catalog["matches"].append({k: v for k, v in match.items() if k not in ("rounds", "throws")})
            for row in match["rounds"]:
                catalog["rounds"].append(effective_round(row, reviews.get(row["id"], {})))
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
