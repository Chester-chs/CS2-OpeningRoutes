"""Transactional metadata; dense timelines live in separate per-round files."""
import gzip
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


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
                CREATE TABLE IF NOT EXISTS revisions(id INTEGER PRIMARY KEY, entity TEXT, data TEXT, at TEXT);
                PRAGMA user_version=1;
            """)

    def connect(self):
        c = sqlite3.connect(self.db, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def put(self, table: str, key: str, data: dict):
        if table not in {"matches", "teachings", "plans", "round_reviews", "jobs"}:
            raise ValueError("Invalid collection")
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False)
        with self.connect() as c:
            c.execute(f"INSERT OR REPLACE INTO {table}(id,data) VALUES(?,?)", (key, encoded))
            if table != "jobs":
                c.execute("INSERT INTO revisions(entity,data,at) VALUES(?,?,?)", (key, encoded, now()))

    def all(self, table):
        if table not in {"matches", "teachings", "plans", "round_reviews", "jobs"}:
            raise ValueError("Invalid collection")
        with self.connect() as c:
            return {key: json.loads(data) for key, data in c.execute(f"SELECT id,data FROM {table}")}

    def save_match(self, data):
        self.put("matches", data["id"], data)

    def save_teaching(self, throw_id, teaching):
        self.put("teachings", throw_id, teaching)

    def catalog(self):
        from .domain import teaching_gaps
        teachings, reviews = self.all("teachings"), self.all("round_reviews")
        catalog = {"schema_version": 1, "matches": [], "rounds": [], "throws": [],
                   "plans": list(self.all("plans").values())}
        for match in self.all("matches").values():
            catalog["matches"].append({k: v for k, v in match.items() if k not in ("rounds", "throws")})
            for row in match["rounds"]:
                catalog["rounds"].append({**row, "review": reviews.get(row["id"], {})})
            for row in match["throws"]:
                t = teachings.get(row["id"], {})
                catalog["throws"].append({**row, "teaching": t,
                                          "gaps": teaching_gaps(t, source_verified=match["source"]["verified"])})
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
