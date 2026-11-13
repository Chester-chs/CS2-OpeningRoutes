"""Map eras: profiles pool a map's games across patches inside a curated period (synthetic data)."""

from itertools import pairwise

from fastapi.testclient import TestClient

from openingroutes import eras
from openingroutes.api import create_app
from tests.test_profiles import build, learning_fixture, player_profile, seed_learning

ERA = "de_mirage:2026-09/10"


def players(result, pid="111", area="A"):
    return [
        p
        for p in result["profiles"].values()
        if p["kind"] == "player" and p["subject_id"] == pid and p["area"] == area
    ]


def test_era_table_has_unique_ordered_and_non_overlapping_ranges():
    for map_name, rows in eras.MAP_ERAS.items():
        assert len({r["id"] for r in rows}) == len(rows)
        ranges = sorted((r["from"], r["to"]) for r in rows)
        assert all(start <= end for start, end in ranges)
        assert all(previous[1] < current[0] for previous, current in pairwise(ranges))
        assert all(r["id"].startswith(f"{map_name}:") for r in rows)


def test_era_for_needs_the_map_a_date_inside_the_period_and_a_known_patch():
    assert eras.era_for("de_mirage", "2026-09-01", "14180")["id"] == ERA
    assert eras.era_for("de_mirage", "2026-10-31", "14191")["id"] == ERA
    assert eras.era_for("de_mirage", "2026-11-01", "14191") is None
    assert eras.era_for("de_mirage", "2026-08-31", "14174") is None
    assert eras.era_for("de_mirage", "", "14190") is None
    assert eras.era_for("de_mirage", "2026-10-01", None) is None
    assert eras.era_for("de_ancient", "2026-10-01", "14190") is None


def test_patches_inside_the_era_pool_into_one_profile_with_the_split():
    library, timelines = learning_fixture()
    for index, match in enumerate(library):
        match["game_version"] = "14180" if index < 2 else "14190"
    [profile] = players(build(library, timelines))
    assert profile["version"] == ERA and profile["era"]["label"] == "2026-09/10"
    assert profile["counts"]["matches"] == 5 and profile["confidence"]["status"] == "descriptive"
    assert profile["patches"] == {
        "14180": {"rounds": 14, "matches": 2},
        "14190": {"rounds": 21, "matches": 3},
    }
    assert {s["game_version"] for s in profile["samples"]} == {"14180", "14190"}


def test_games_outside_the_era_or_without_a_patch_keep_their_exact_patch():
    library, timelines = learning_fixture(4, 1)
    library[0]["game_version"] = "14190"
    library[1]["game_version"] = "14190"
    library[2]["source"]["date"] = "2026-11-02"
    library[2]["game_version"] = "14190"
    library[3]["game_version"] = None
    result = build(library, timelines)
    by_version = {p["version"]: p for p in players(result)}
    assert set(by_version) == {ERA, "14190", "unknown:match3"}
    assert by_version[ERA]["counts"]["matches"] == 2
    assert by_version["14190"]["era"] is None
    assert by_version["14190"]["patches"] == {"14190": {"rounds": 1, "matches": 1}}


def test_other_maps_do_not_pool():
    library, timelines = learning_fixture(2, 1)
    for index, match in enumerate(library):
        match["map"] = "de_ancient"
        match["game_version"] = str(14180 + index)
    assert {p["version"] for p in players(build(library, timelines))} == {"14180", "14181"}


def test_splitting_an_era_splits_profiles_and_the_cache_key(tmp_path, monkeypatch):
    library, timelines = learning_fixture(2, 1)
    library[1]["source"]["date"] = "2026-10-20"
    assert len(players(build(library, timelines))) == 1
    split = {
        "de_mirage": [
            {
                "id": "de_mirage:2026-09/10a",
                "label": "2026-09—10-15",
                "from": "2026-09-01",
                "to": "2026-10-15",
            },
            {
                "id": "de_mirage:2026-10b",
                "label": "2026-10-16—10-31",
                "from": "2026-10-16",
                "to": "2026-10-31",
            },
        ]
    }
    store = seed_learning(tmp_path)
    before = store._profile_key()
    monkeypatch.setattr(eras, "MAP_ERAS", split)
    assert len(players(build(library, timelines))) == 2
    store._memo.clear()
    assert store._profile_key() != before


def test_learning_api_carries_the_era_and_each_sample_patch(tmp_path):
    store = seed_learning(tmp_path)
    store.learning_index(wait=True)
    client = TestClient(create_app(tmp_path, testing=True))
    entry = next(p for p in client.get("/api/learning").json()["profiles"] if p["kind"] == "player")
    assert entry["era"]["id"] == ERA and entry["patches"] == {"test-map-v1": {"rounds": 2, "matches": 1}}
    detail = client.get(f"/api/learning/profiles/{entry['id']}").json()
    assert {s["game_version"] for s in detail["samples"]} == {"test-map-v1"}
    assert player_profile(build(*learning_fixture(1, 1)))["era"]["id"] == ERA
