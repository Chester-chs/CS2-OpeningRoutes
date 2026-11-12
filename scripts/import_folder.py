"""Import reviewed professional demos through the desktop extraction pipeline.

Create a CSV with --template first. Close other library writers before importing.
Extracted demos and partial files stay in --work/staging for inspection/resume;
neither originals nor staging demos are deleted. Run --help for examples.
"""

import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import closing
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openingroutes.extract import DemoParser, extract_demo, file_hash  # noqa: E402
from openingroutes.models import Source  # noqa: E402
from openingroutes.store import Store  # noqa: E402

CSV_FIELDS = ("archive", "event", "match", "date", "url", "reviewed", "reviewer")
MAPS = {f"de_{m}" for m in "mirage ancient dust2 inferno nuke anubis train overpass vertigo cache".split()}
MAX_MEMBER_BYTES = 2 * 1024**3  # Same limit as the desktop upload endpoint.
MAX_ARCHIVE_BYTES = 20 * 1024**3
HLTV = re.compile(r"https://(?:www\.)?hltv\.org/matches/(\d+)/[a-zA-Z0-9-]+/?")


def inputs(folder):
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in {".rar", ".zip", ".dem"})


def write_template(folder, target):
    """Filename guesses are hints only: never invent a date, URL, or review."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for path in inputs(folder):
            stem = re.split(r"-bo[135](?:-|$)", path.stem, maxsplit=1)[0]
            parts = re.match(r"(.*?20\d{2}(?:-season-\d+)?(?:-finals)?)-(.*-vs-.*)", stem)
            event, matchup = parts.groups() if parts else ("", stem)
            day = re.search(r"\d{4}-\d{2}-\d{2}", stem)
            writer.writerow(
                {
                    "archive": path.name,
                    "event": event.replace("-", " "),
                    "match": matchup.replace("-", " "),
                    "date": day[0] if day else "",
                    "url": "",
                    "reviewed": "false",
                    "reviewer": "",
                }
            )


def read_sources(path):
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not set(CSV_FIELDS).issubset(reader.fieldnames or []):
            raise ValueError(f"CSV requires: {', '.join(CSV_FIELDS)}")
        rows = {}
        for row in reader:
            name = (row.get("archive") or "").strip()
            if not name or name.casefold() in rows:
                raise ValueError(f"Empty or duplicate CSV archive: {name}")
            rows[name.casefold()] = {key: (row.get(key) or "").strip() for key in CSV_FIELDS}
        return rows


def reviewed_source(row):
    if row is None or row["reviewed"].lower() != "true":
        raise ValueError("Set reviewed=true only after checking the match source")
    if not HLTV.fullmatch(row["url"]) or not row["reviewer"]:
        raise ValueError("A reviewed HLTV match-page URL and reviewer are required")
    date.fromisoformat(row["date"])
    return Source(
        **{key: row[key] for key in ("event", "match", "date", "url", "reviewer")}, verified=True
    ).model_dump()


def member_map(name):
    hit = re.search(
        r"(?:^|[-_ .])(mirage|ancient|dust2|inferno|nuke|anubis|train|overpass|vertigo|cache)"
        r"(?=[-_. ]|$)",
        PurePosixPath(name).name.lower(),
    )
    return f"de_{hit[1]}" if hit else None


def split_member(name):
    return bool(re.search(r"(?:^|[-_ .])(?:p|part|half)[-_ ]?\d+(?=[-_. ]|$)", name.lower()))


def safe_member(name):
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or path.is_absolute()
        or ".." in path.parts
        or any(c in normalized for c in ":*?[]")
        or any(ord(c) < 32 for c in normalized)
    ):
        raise ValueError(f"Unsafe archive member: {name!r}")


def parse_tar_listing(raw):
    try:
        listing = raw.decode("utf-8")
    except UnicodeDecodeError:
        listing = raw.decode("gb18030")
    entries = []
    for line in listing.splitlines():
        fields = line.split(maxsplit=8)
        if len(fields) != 9 or fields[0][0] not in "-d":
            raise ValueError(f"Unsupported tar entry (links are not allowed): {line!r}")
        name = fields[8]
        safe_member(name)
        if fields[0][0] == "-":
            entries.append((name, int(fields[4])))
    return entries


def members(path):
    if path.suffix.lower() == ".dem":
        entries = [(path.name, path.stat().st_size)]
    elif path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as handle:
            entries = []
            for info in handle.infolist():
                safe_member(info.filename)
                kind = stat.S_IFMT(info.external_attr >> 16)
                if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                    raise ValueError(f"Archive links/devices are not allowed: {info.filename}")
                if not info.is_dir():
                    entries.append((info.filename, info.file_size))
    else:
        raw = subprocess.run(
            ["tar", "-tvf", str(path)], stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=60
        ).stdout
        entries = parse_tar_listing(raw)
    names = [name.casefold() for name, _ in entries]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate archive member names")
    if any(size < 0 or size > MAX_MEMBER_BYTES for _, size in entries):
        raise ValueError("Demo/archive member exceeds the 2 GiB limit")
    if sum(size for _, size in entries) > MAX_ARCHIVE_BYTES:
        raise ValueError("Archive exceeds the 20 GiB expanded limit")
    return [(name, size) for name, size in entries if name.lower().endswith(".dem")]


def copy_member(stream, target, size):
    remaining = size
    with target.open("xb") as handle:
        while remaining:
            chunk = stream.read(min(8 * 1024**2, remaining))
            if not chunk:
                raise ValueError("Truncated archive member")
            handle.write(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            raise ValueError("Archive member exceeds its declared size")


def stage_member(archive, name, size, work):
    if archive.suffix.lower() == ".dem":
        return archive
    before = archive.stat()
    key = hashlib.sha256(
        json.dumps([str(archive.resolve()), before.st_size, before.st_mtime_ns, name]).encode()
    ).hexdigest()
    stage = work / "staging" / key
    stage.mkdir(parents=True, exist_ok=True)
    receipt = stage / "ready.json"
    if receipt.exists():
        try:
            saved = json.loads(receipt.read_text(encoding="utf-8"))
            path = stage / saved["file"]
            if (
                path.resolve().parent == stage.resolve()
                and path.is_file()
                and file_hash(path) == saved["sha256"]
            ):
                return path
        except (ValueError, KeyError, TypeError):
            pass  # An interrupted receipt is not evidence of a complete member.
    if shutil.disk_usage(stage).free < size + 1024**3:
        raise OSError("Insufficient staging space (keep 1 GiB free)")
    partial = stage / f"{uuid.uuid4().hex}.partial"
    if archive.suffix.lower() == ".zip":
        with zipfile.ZipFile(archive) as handle, handle.open(name) as stream:
            copy_member(stream, partial, size)
    else:
        # Stream into our own generated filename: tar never chooses an output path.
        with tempfile.TemporaryFile() as errors:
            process = subprocess.Popen(
                ["tar", "-xOf", str(archive), "--", name],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=errors,
            )
            timer = threading.Timer(1200, process.kill)
            timer.daemon = True
            timer.start()
            try:
                copy_member(process.stdout, partial, size)
                code = process.wait()
                if code:
                    errors.seek(0)
                    raise ValueError(f"tar failed ({code}): {errors.read(2000)!r}")
            finally:
                timer.cancel()
                process.stdout.close()
                if process.poll() is None:
                    process.kill()
                    process.wait()
    after = archive.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError("Archive changed while extracting")
    target = partial.with_suffix(".dem")
    partial.rename(target)
    receipt.write_text(json.dumps({"file": target.name, "sha256": file_hash(target)}), encoding="utf-8")
    return target


def read_matches(data):
    db = data / "library.sqlite"
    if not db.exists():
        return {}
    with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as conn:
        return {
            row["sha256"]: row
            for (encoded,) in conn.execute("SELECT data FROM matches")
            if (row := json.loads(encoded)).get("sha256")
        }


def backup_library(data, work):
    validate_work_path(data, work)
    backup = work / "backups" / (datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:8])
    backup.mkdir(parents=True)
    db = data / "library.sqlite"
    if db.exists():
        with closing(sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(backup / "library.sqlite")) as dst:
                src.backup(dst)
    if (data / "timelines").exists():
        shutil.copytree(data / "timelines", backup / "timelines")
    else:
        (backup / "timelines").mkdir()
    (backup / "manifest.json").write_text(
        json.dumps(
            {
                "library": str(data.resolve()),
                "existing_database": db.exists(),
                "completed_at": datetime.now(UTC).isoformat(),
            }
        ),
        encoding="utf-8",
    )
    return backup


def demo_map(path):
    with path.open("rb") as handle:
        if not handle.read(8).startswith(b"PBDEMS2"):
            raise ValueError("Expected a CS2 PBDEMS2 demo")
    return DemoParser(str(path)).parse_header()["map_name"]


def match_map_key(source, map_name):
    try:
        url = urlsplit(source.get("url", ""))
    except ValueError:
        return None
    hit = re.fullmatch(r"/matches/(\d+)(?:/[a-zA-Z0-9-]+)?/?", url.path)
    if url.scheme == "https" and url.hostname in {"www.hltv.org", "hltv.org"} and hit:
        return hit[1], map_name
    return None


def validate_work_path(data, work):
    if work.resolve().is_relative_to(data.resolve()):
        raise ValueError("The work directory must be outside the library directory")


def import_folder(folder, data, csv_path, work, maps):
    validate_work_path(data, work)
    if not maps or not maps.issubset(MAPS):
        raise ValueError("Provide a nonempty supported map whitelist")
    rows = read_sources(csv_path)
    known = read_matches(data)
    logical_maps = {key for match in known.values() if (key := match_map_key(match["source"], match["map"]))}
    work.mkdir(parents=True, exist_ok=True)
    results, store = [], None

    def record(row, started):
        row["seconds"] = round(time.perf_counter() - started, 3)
        results.append(row)
        with (work / "results.jsonl").open("a", encoding="utf-8") as log:
            log.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)

    for archive in inputs(folder):
        started = time.perf_counter()
        try:
            entries = members(archive)
        except Exception as exc:
            record({"archive": archive.name, "status": "error", "error": str(exc)}, started)
            continue
        for name, size in entries:
            started = time.perf_counter()
            map_name = member_map(name)
            row = {"archive": archive.name, "member": name, "map": map_name, "bytes": size}
            try:
                if split_member(name):
                    row["status"] = "pending_split"
                elif map_name is None:
                    row["status"] = "unknown_map"
                elif map_name not in maps:
                    row["status"] = "filtered"
                else:
                    try:
                        source = reviewed_source(rows.get(archive.name.casefold()))
                    except ValueError as exc:
                        row.update(status="pending_source", error=str(exc))
                        record(row, started)
                        continue
                    path = stage_member(archive, name, size, work)
                    digest = file_hash(path)
                    row.update(sha256=digest, staged=str(path.resolve()))
                    if digest in known:
                        row.update(status="duplicate", match_id=known[digest]["id"])
                    elif demo_map(path) != map_name:
                        raise ValueError("Demo header map does not match the filename whitelist")
                    elif match_map_key(source, map_name) in logical_maps:
                        row["status"] = "pending_match_map"
                    else:
                        if store is None:
                            backup_library(data, work)
                            store = Store(data)
                        match = extract_demo(path, source, store)
                        known[digest] = match
                        logical_maps.add(match_map_key(source, map_name))
                        row.update(status="imported", match_id=match["id"])
            except Exception as exc:
                row.update(status="error", error=str(exc))
            record(row, started)
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--template", type=Path, help="Write CSV guesses, never overwrite an existing CSV")
    parser.add_argument("--sources", type=Path, help="Reviewed CSV; true requires URL, date and reviewer")
    parser.add_argument("--data", type=Path, default=Path(".local/data"))
    parser.add_argument("--work", type=Path, default=Path(".local/learning-data"))
    parser.add_argument("--maps", nargs="+", help="Explicit whitelist, e.g. mirage ancient")
    args = parser.parse_args(argv)
    if args.template:
        write_template(args.folder, args.template)
        return 0
    if not args.sources or not args.maps:
        parser.error("Import requires --sources and --maps; generate --template first")
    selected = {name if name.startswith("de_") else f"de_{name}" for name in args.maps}
    rows = import_folder(args.folder, args.data, args.sources, args.work, selected)
    return 1 if any(r["status"] == "error" for r in rows) else 0


if __name__ == "__main__":
    raise SystemExit(main())
