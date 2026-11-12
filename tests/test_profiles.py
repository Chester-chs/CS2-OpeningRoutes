"""Player-area evidence, uncertainty, transfers and cache/API boundaries."""

import copy
import importlib

from fastapi.testclient import TestClient

from openingroutes.api import create_app
from openingroutes.patterns import analyze_map
from openingroutes.store import Store
from tests.test_workflow import auth


def learning_fixture(matches=5, rounds=7):
    library, timelines = [], {}
    for match_index in range(matches):
        mid = f"match{match_index}"
        match = {
            "id": mid,
            "map": "de_mirage",
            "sha256": mid,
            "game_version": "test-map-v1",
            "learning_version": 1,
            "formations_version": 2,
            "tick_rate": 64,
            "source": {
                "event": "Synthetic test event",
                "match": "Alpha vs Beta",
                "verified": True,
                "date": f"2026-10-{match_index + 1:02d}",
                "url": "https://example.org/match",
            },
            "players": [{"id": "111", "name": "Same nickname"}, {"id": "222", "name": "Same nickname"}],
            "rounds": [],
            "throws": [],
            "formations": {},
            "team_aliases": {},
            "warnings": [],
        }
        for number in range(1, rounds + 1):
            rid = f"{mid}-r{number}"
            row = {
                "id": rid,
                "match_id": mid,
                "number": number,
                "start_tick": 0,
                "freeze_end_tick": 0,
                "end_tick": 2560,
                "complete": True,
                "is_pistol": number == 1,
                "winner": "CT",
                "review_required": False,
                "equipment": [
                    {
                        "player_id": pid,
                        "player": "Same nickname",
                        "side": side,
                        "team": team,
                        "equip": 800 if number == 1 else 5000,
                    }
                    for pid, side, team in (("111", "CT", "Alpha"), ("222", "T", "Beta"))
                ],
                "learning_events": [
                    {
                        "kind": "hurt",
                        "tick": 768,
                        "attacker_id": "222",
                        "victim_id": "111",
                        "victim_place": "BombsiteA",
                        "attacker_place": "BombsiteA",
                        "victim_position": [0, 0, 0],
                    }
                ],
            }
            match["rounds"].append(row)
            timeline = {
                "round_id": rid,
                "tick_rate": 64,
                "sample_hz": 4,
                "learning_version": 1,
                "point_fields": ["tick", "x", "y", "z", "side", "alive"],
                "players": {},
            }
            for pid, side in (("111", "CT"), ("222", "T")):
                ticks = list(range(0, 2561, 16))
                timeline["players"][pid] = {
                    "name": "Same nickname",
                    "points": [[tick, 0, 0, 0, side, True] for tick in ticks],
                    "places": ["TSpawn" if side == "T" and tick < 640 else "BombsiteA" for tick in ticks],
                }
            timelines[rid] = timeline
            match["throws"].append(
                {
                    "id": f"{mid}-t{number}-111",
                    "round_id": rid,
                    "match_id": mid,
                    "player_id": "111",
                    "player": "Same nickname",
                    "side": "CT",
                    "kind": "smoke",
                    "tick": 128,
                    "time": 2,
                    "origin_place": "BombsiteA",
                    "effect_place": "BombsiteA",
                    "effect_place_basis": {"method": "nearest_observed_player_position", "distance": 20},
                }
            )
        library.append(match)
    return library, timelines


def build(library, timelines, **kwargs):
    return importlib.import_module("openingroutes.profiles").build(library, timelines.get, **kwargs)


def player_profile(result, pid="111", area="A"):
    return next(
        p
        for p in result["profiles"].values()
        if p["kind"] == "player" and p["subject_id"] == pid and p["area"] == area
    )


def seed_learning(root, matches=1, rounds=2):
    library, timelines = learning_fixture(matches, rounds)
    store = Store(root)
    for match in library:
        store.save_match(match)
    for rid, timeline in timelines.items():
        store.write_timeline(rid, timeline)
    return store


def test_occupancy_requires_two_seconds_and_marks_contested_unknown_and_terminal_state():
    library, timelines = learning_fixture(1, 1)
    row = library[0]["rounds"][0]
    timeline = timelines[row["id"]]
    module = importlib.import_module("openingroutes.profiles")
    states = module.area_states(timeline, row, {"BombsiteA"})
    by_time = {p[0]: p for p in states["points"]}
    assert by_time[0][3] == "transit"
    assert by_time[2][3] == "CT"
    assert by_time[10][3] == "contested"
    assert states["end_state"] == "contested"
    timeline["players"]["222"]["places"][12] = None
    assert module.area_states(timeline, row, {"BombsiteA"})["points"][12][3] == "unknown"
    timeline["players"]["222"]["points"][-1][5] = False
    assert module.area_states(timeline, row, {"BombsiteA"})["end_state"] == "transit"


def test_profiles_count_rounds_not_samples_and_link_observed_sequences():
    library, timelines = learning_fixture()
    result = build(library + [copy.deepcopy(library[0])], timelines)
    profile = player_profile(result)
    assert profile["counts"] == {"rounds": 35, "matches": 5, "players": 1, "pistols": 5}
    assert profile["confidence"]["status"] == "descriptive"
    assert profile["habits"][0]["interval"] is not None
    assert profile["samples"][0]["utility"][0]["time"] == 2
    assert profile["samples"][0]["first_contact"]["tick"] == 768
    assert profile["samples"][0]["control"]["end_state"] == "contested"
    assert profile["contexts"]["pistol"]["counts"]["rounds"] == 5
    assert player_profile(result, "222")["side"] == "T"
    assert any(p["kind"] == "team" for p in result["profiles"].values())


def test_missing_old_data_unverified_abnormal_and_excluded_rounds_never_become_claims():
    library, timelines = learning_fixture(3, 3)
    library[0]["source"]["verified"] = False
    library[1]["rounds"][0]["review_required"] = True
    timelines["match1-r2"]["players"]["111"].pop("places")
    result = build(library, timelines, reviews={"match2-r1": {"resolution": "excluded"}})
    profile = player_profile(result)
    assert profile["counts"]["rounds"] == 3
    assert profile["confidence"]["status"] == "exploratory"
    assert profile["habits"][0]["interval"] is None
    assert result["index"]["coverage"]["missing_rounds"] == 1
    assert {s["round_id"] for s in profile["samples"]} == {"match1-r3", "match2-r2", "match2-r3"}


def test_transfers_returning_stints_versions_and_nicknames_do_not_merge():
    library, timelines = learning_fixture(4, 1)
    library[1]["rounds"][0]["equipment"][0]["team"] = "Gamma"
    library[3]["game_version"] = "test-map-v2"
    result = build(library, timelines)
    players = [
        p
        for p in result["profiles"].values()
        if p["kind"] == "player" and p["subject_id"] == "111" and p["area"] == "A"
    ]
    assert len(players) == 4
    assert sum(p["counts"]["rounds"] for p in players) == 4
    assert len({p["id"] for p in players}) == 4


def test_custom_region_and_confirmed_role_keep_individual_profiles():
    library, timelines = learning_fixture(1, 2)
    groups = {
        "a-site": {"kind": "region", "map": "de_mirage", "label": "A site", "places": ["BombsiteA"]},
        "anchor": {
            "kind": "role",
            "map": "de_mirage",
            "label": "A anchor",
            "side": "CT",
            "area": "a-site",
            "team": "Alpha",
            "players": ["111"],
            "confirmed": True,
        },
    }
    result = build(library, timelines, groups=groups)
    assert player_profile(result, area="a-site")["counts"]["rounds"] == 2
    cohort = next(p for p in result["profiles"].values() if p["kind"] == "role")
    assert cohort["members"] == ["111"] and cohort["counts"]["rounds"] == 2


def test_profile_cache_invalidates_for_review_labels_source_and_roles(tmp_path):
    store = seed_learning(tmp_path)
    index = store.learning_index(wait=True)
    assert index["state"] == "ready"
    pid = next(p["id"] for p in index["profiles"] if p["kind"] == "player")
    assert store.learning_profile(pid)["samples"]
    first = store._profile_key()
    store.put("round_reviews", "match0-r1", {"resolution": "excluded"})
    assert store._profile_key() != first
    assert store.learning_index(wait=True)["coverage"]["analyzed_rounds"] == 1
    for table, key, value in (
        ("places", "de_mirage:BombsiteA", {"label": "Custom"}),
        ("learning_groups", "role1", {"kind": "role", "confirmed": False}),
    ):
        before = store._profile_key()
        store.put(table, key, value)
        assert store._profile_key() != before
    match = store.all("matches")["match0"]
    match["source"]["verified"] = False
    store.save_match(match)
    assert store.learning_index(wait=True)["profiles"] == []
    assert store.learning_profile(pid) is None


def test_learning_api_reuses_write_auth_and_rejects_invalid_groups(tmp_path):
    store = seed_learning(tmp_path)
    index = store.learning_index(wait=True)
    client = TestClient(create_app(tmp_path, testing=True))
    response = client.get("/api/learning")
    assert response.status_code == 200 and response.json()["state"] == "ready"
    pid = index["profiles"][0]["id"]
    assert client.get(f"/api/learning/profiles/{pid}").status_code == 200
    assert client.get("/api/learning/profiles/not-a-profile").status_code == 404
    assert client.put("/api/learning/groups/x", json={}).status_code == 403
    assert (
        client.put("/api/learning/groups/x", headers=auth(client), json={"kind": "role"}).status_code == 422
    )
    region = {"kind": "region", "map": "de_mirage", "label": "A site", "places": ["BombsiteA"]}
    assert client.put("/api/learning/groups/a-site", headers=auth(client), json=region).status_code == 200
    assert client.get("/api/catalog/summary").json()["schema_version"] == 1


def test_t_formation_analysis_has_its_own_clock_and_labels():
    result = analyze_map("de_mirage", [], [], side="T")
    assert result["side"] == "T"
    assert result["snapshot_seconds"] == [0, 5, 10, 15, 20, 25, 30]
    assert result["rounds"] == 0

    formations = [
        {
            "round_id": f"m-r{i}",
            "winner": "T",
            "context": {"t_score_before": 3, "ct_score_before": 1},
            "opening_context": {"t_econ": "long_gun"},
            "t_snapshots": [
                {
                    "second": second,
                    "t": [
                        {"player_id": str(p), "place": "TSpawn" if i < 4 else "BombsiteA", "alive": p != 0}
                        for p in range(5)
                    ],
                }
                for second in (0, 5, 10, 15, 20, 25, 30)
            ],
        }
        for i in range(8)
    ]
    expanded = analyze_map("de_mirage", formations, [], side="T", max_k=2, min_cluster=2)
    assert expanded["rounds"] == 8 and len(expanded["patterns"]) == 2
    assert all(p["name"].startswith("T 展开") for p in expanded["patterns"])
    assert all(sum(p["shares"][15].values()) == 0.8 for p in expanded["patterns"])
    assert all(p["score"] == {"leading": 4} for p in expanded["patterns"])


def test_learning_events_do_not_inflate_the_legacy_startup_payload(tmp_path):
    store = seed_learning(tmp_path)
    assert "learning_events" not in store.summary()["rounds"][0]
    assert "learning_events" not in store.catalog()["rounds"][0]


def test_plan_edits_do_not_restart_the_learning_cache(tmp_path):
    store = seed_learning(tmp_path)
    before = store._profile_key()
    store.put("plans", "draft", {"status": "draft"})
    assert store._profile_key() == before
    match = store.all("matches")["match0"]
    match["rounds"][0]["learning_events"] = []
    store.save_match(match)
    assert store._profile_key() != before
