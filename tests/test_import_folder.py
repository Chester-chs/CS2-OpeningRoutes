"""Batch import must preserve provenance, curation, and every original demo."""

import csv
import hashlib
import json
import sqlite3
import zipfile

import pytest

from openingroutes.store import Store
from scripts import import_folder as batch


SOURCE = {
    "event": "Test event",
    "match": "Alpha vs Beta",
    "date": "2026-10-18",
    "url": "https://www.hltv.org/matches/2390000/alpha-vs-beta-test",
    "reviewed": "true",
    "reviewer": "Human",
}


def sources(path, names, **changes):
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=batch.CSV_FIELDS)
        writer.writeheader()
        for index, name in enumerate(sorted(names)):
            writer.writerow({"archive": name, **SOURCE,
                             "url": SOURCE["url"].replace("2390000", str(2390000 + index)), **changes})
    return path


def archive(folder, name="match.zip", members=None):
    path = folder / name
    with zipfile.ZipFile(path, "w") as handle:
        for member, content in (members or {"alpha-vs-beta-m1-mirage.dem": b"demo"}).items():
            handle.writestr(member, content)
    return path


@pytest.fixture
def setup(tmp_path, monkeypatch):
    folder = tmp_path / "input"
    folder.mkdir()
    data, work = tmp_path / "data", tmp_path / "work"
    calls = []

    def extract(path, source, store, progress=lambda stage: None):
        assert list((work / "backups").glob("*/manifest.json")), "Back up before extraction"
        calls.append(path)
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        match = {"id": digest[:20], "sha256": digest, "map": "de_mirage", "source": source}
        store.save_match(match)
        return match

    monkeypatch.setattr(batch, "extract_demo", extract)
    monkeypatch.setattr(batch, "demo_map", lambda path: "de_mirage")
    return folder, data, work, calls


def run(setup, **changes):
    folder, data, work, _ = setup
    csv_path = sources(work.parent / "sources.csv", [p.name for p in folder.iterdir()], **changes)
    return batch.import_folder(folder, data, csv_path, work, {"de_mirage"})


def test_template_is_reviewable_and_never_overwrites_edits(tmp_path):
    archive(tmp_path, "event-2026-alpha-vs-beta-bo3-token.zip")
    (tmp_path / "ignore.txt").write_text("ignore")
    target = tmp_path / "sources.csv"
    batch.write_template(tmp_path, target)
    rows = list(csv.DictReader(target.open(encoding="utf-8-sig")))
    assert len(rows) == 1 and "alpha" in rows[0]["match"].lower()
    assert rows[0]["reviewed"] == "false" and rows[0]["url"] == ""
    with pytest.raises(FileExistsError):
        batch.write_template(tmp_path, target)


@pytest.mark.parametrize("changes", [
    {"reviewed": "false"}, {"url": ""}, {"reviewer": ""}, {"reviewed": "yes-ish"},
    {"url": "https://www.hltv.org.evil.test/matches/123/name"},
    {"url": "https://www.hltv.org/news/123/name"}, {"date": "2026-02-30"},
])
def test_unreviewed_or_invalid_sources_never_open_store(setup, changes):
    folder, data, _, calls = setup
    archive(folder)
    rows = run(setup, **changes)
    assert rows[0]["status"] == "pending_source"
    assert not data.exists() and not calls


def test_hash_dedup_and_resume_ignore_stale_success_log(setup):
    folder, data, work, calls = setup
    original = archive(folder, members={"m1-mirage.dem": b"same", "m2-mirage.dem": b"same"})
    before = original.read_bytes()
    assert [r["status"] for r in run(setup)] == ["imported", "duplicate"]
    assert len(calls) == 1 and calls[0].exists()
    assert original.read_bytes() == before
    assert all(r["seconds"] >= 0 and r["sha256"] for r in run(setup))
    assert len(calls) == 1
    with sqlite3.connect(data / "library.sqlite") as conn:
        conn.execute("DELETE FROM matches")
    assert run(setup)[0]["status"] == "imported"
    assert len(calls) == 2  # The database, not an old success log, decides completion.
    assert len((work / "results.jsonl").read_text().splitlines()) == 6


def test_backup_contains_sqlite_and_timelines_and_preserves_curation(setup):
    folder, data, work, _ = setup
    store = Store(data)
    store.put("teachings", "curated", {"title": "Keep"})
    (data / "timelines" / "old.json.gz").write_bytes(b"timeline")
    archive(folder)
    run(setup)
    backup = next((work / "backups").glob("*/manifest.json")).parent
    with sqlite3.connect(backup / "library.sqlite") as conn:
        assert json.loads(conn.execute("SELECT data FROM teachings").fetchone()[0]) == {"title": "Keep"}
        assert conn.execute("SELECT count(*) FROM matches").fetchone()[0] == 0
    assert (backup / "timelines" / "old.json.gz").read_bytes() == b"timeline"
    assert store.all("teachings") == {"curated": {"title": "Keep"}}


def test_backup_failure_prevents_import(setup, monkeypatch):
    folder, data, _, calls = setup
    archive(folder)
    monkeypatch.setattr(batch, "backup_library", lambda *args: (_ for _ in ()).throw(OSError("no space")))
    assert run(setup)[0]["status"] == "error"
    assert not calls and not data.exists()


def test_split_maps_unknown_maps_and_whitelist_never_import(setup):
    folder, data, _, calls = setup
    archive(folder, members={
        "m1-mirage-p1.dem": b"a", "m1-mirage-p2.dem": b"b",
        "m2-nuke.dem": b"c", "unknown.dem": b"d",
    })
    rows = run(setup)
    assert [r["status"] for r in rows] == ["pending_split", "pending_split", "filtered", "unknown_map"]
    assert not calls and not data.exists()


@pytest.mark.parametrize("member", ["../escape.dem", "/absolute.dem", "C:/escape.dem", "x:stream.dem"])
def test_archive_paths_cannot_escape_staging(setup, member):
    folder, data, _, calls = setup
    archive(folder, members={member: b"bad", "m1-mirage.dem": b"good"})
    assert run(setup)[0]["status"] == "error"
    assert not calls and not data.exists()


def test_zip_symlink_is_rejected(setup):
    folder, _, _, calls = setup
    with zipfile.ZipFile(folder / "link.zip", "w") as handle:
        info = zipfile.ZipInfo("m1-mirage.dem")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        handle.writestr(info, "outside")
    assert run(setup)[0]["status"] == "error"
    assert not calls


def test_actual_map_must_match_filename_before_library_write(setup, monkeypatch):
    folder, data, _, calls = setup
    archive(folder)
    monkeypatch.setattr(batch, "demo_map", lambda path: "de_nuke")
    assert run(setup)[0]["status"] == "error"
    assert not calls and not data.exists()


def test_parser_failure_continues_and_retries_on_next_run(setup, monkeypatch):
    folder, _, _, calls = setup
    archive(folder, "bad.zip", {"bad-mirage.dem": b"bad"})
    archive(folder, "good.zip", {"good-mirage.dem": b"good"})
    real = batch.extract_demo

    def fail_once(path, *args, **kwargs):
        if path.read_bytes() == b"bad":
            raise ValueError("Invalid demo")
        return real(path, *args, **kwargs)

    monkeypatch.setattr(batch, "extract_demo", fail_once)
    assert [r["status"] for r in run(setup)] == ["error", "imported"]
    monkeypatch.setattr(batch, "extract_demo", real)
    assert [r["status"] for r in run(setup)] == ["imported", "duplicate"]
    assert len(calls) == 2


def test_same_series_map_with_different_hash_needs_review(setup):
    folder, _, _, calls = setup
    archive(folder, members={"m1-mirage.dem": b"first", "alternate-mirage.dem": b"other"})
    assert [r["status"] for r in run(setup)] == ["imported", "pending_match_map"]
    assert len(calls) == 1


def test_rar_listing_parses_chinese_and_rejects_links():
    listing = "-rw-r--r--  0 0 0 12 Oct 18 2026 比赛-mirage.dem\n".encode("gb18030")
    assert batch.parse_tar_listing(listing) == [("比赛-mirage.dem", 12)]
    with pytest.raises(ValueError):
        batch.parse_tar_listing(b"lrwxrwxrwx  0 0 0 12 Oct 18 2026 m1-mirage.dem -> elsewhere\n")


def test_loose_demo_is_supported_without_moving_original(setup):
    folder, _, _, calls = setup
    demo = folder / "match-mirage.dem"
    demo.write_bytes(b"loose")
    assert run(setup)[0]["status"] == "imported"
    assert calls == [demo] and demo.read_bytes() == b"loose"
