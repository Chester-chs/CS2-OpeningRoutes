"""Lineup variants, area vocabulary and abnormal-round review (synthetic data, clearly labelled)."""

from fastapi.testclient import TestClient

from openingroutes.api import create_app
from openingroutes.places import place_label
from openingroutes.store import Store
from openingroutes.variants import cluster, same_lineup
from tests.test_workflow import auth


def throw(tid, player, *, pos=(0, 0, 0), yaw=90.0, pitch=-10.0, effect=(1000, 0, 0), kind="smoke", side="CT"):
    return {
        "id": tid,
        "match_id": "m1",
        "round_id": "m1-r1",
        "round_number": 1,
        "map": "de_test",
        "player": player,
        "team": "A",
        "side": side,
        "kind": kind,
        "tick": int(tid[1:]) * 64,
        "time": 1,
        "position": list(pos),
        "view": {"pitch": pitch, "yaw": yaw},
        "effect_position": list(effect) if effect else None,
        "origin_place": "CTSpawn",
        "effect_place": "Middle",
    }


def seed_many(root, throws, rounds=None):
    store = Store(root)
    store.save_match(
        {
            "id": "m1",
            "map": "de_test",
            "source": {
                "event": "Synthetic",
                "match": "A v B",
                "date": "2025-01-01",
                "url": "https://example.org/m",
                "verified": True,
                "reviewer": "test",
            },
            "sha256": "b" * 64,
            "rounds": rounds
            or [{"id": "m1-r1", "match_id": "m1", "number": 1, "is_pistol": True, "complete": True}],
            "throws": throws,
            "warnings": [],
        }
    )
    store.write_timeline("m1-r1", {"round_id": "m1-r1", "players": {}})
    return store


def test_same_lineup_by_different_players_groups_and_different_release_splits():
    rows = [
        throw("t1", "Alice"),
        throw("t2", "Bob", pos=(30, 20, 0), yaw=91.5, effect=(1040, 30, 0)),
        throw("t3", "Alice", pos=(400, 0, 0), yaw=60, effect=(1010, 10, 0)),  # same landing, other throw
        throw("t4", "Carol", kind="flash"),
        throw("t5", "Dan", effect=None),  # no effect position -> never auto-merged
    ]
    groups = cluster(rows, [])
    by_member = {m: g for g in groups for m in g["members"]}
    assert by_member["t1"] is by_member["t2"]
    assert by_member["t3"] is not by_member["t1"]
    assert by_member["t4"] is not by_member["t1"]
    assert by_member["t5"]["members"] == ["t5"]
    assert by_member["t1"]["source"] == "auto" and by_member["t1"]["players"] == ["Alice", "Bob"]
    # deterministic ids anchored on the earliest member
    assert cluster(list(reversed(rows)), [])[0]["id"] in {g["id"] for g in groups}


def test_malformed_throws_never_join_a_lineup():
    good = throw("t1", "Alice")
    assert same_lineup(good, throw("t2", "Bob"))
    malformed = [
        {**throw("t2", "Bob"), "view": None},
        {**throw("t3", "Bob"), "view": ["yaw", 90]},  # not a dict: skipped, not an error
        {**throw("t4", "Bob"), "view": {"yaw": "90", "pitch": -10.0}},
        {**throw("t5", "Bob"), "position": None},
        {**throw("t6", "Bob"), "position": [0, 0]},  # needs z
        {**throw("t7", "Bob"), "position": [0, True, 0]},
        {**throw("t8", "Bob"), "effect_position": "1000,0"},
    ]
    for row in malformed:
        assert not same_lineup(good, row) and not same_lineup(row, good), row["id"]
    groups = cluster([good, *malformed], [])
    assert sorted(len(g["members"]) for g in groups) == [1] * 8


def test_manual_variants_override_auto_clustering():
    rows = [throw("t1", "Alice"), throw("t2", "Bob", pos=(10, 0, 0)), throw("t3", "Carol", pos=(20, 0, 0))]
    manual = [{"id": "v-manual", "source": "manual", "members": ["t3", "missing"], "title": "X"}]
    groups = cluster(rows, manual)
    by_member = {m: g for g in groups for m in g["members"]}
    assert by_member["t3"]["id"] == "v-manual" and by_member["t3"]["members"] == ["t3"]
    assert by_member["t1"]["id"] == by_member["t2"]["id"] != "v-manual"


def test_merge_split_and_label_variants_through_api(tmp_path):
    seed_many(
        tmp_path,
        [throw("t1", "Alice"), throw("t2", "Bob", pos=(600, 0, 0), yaw=10), throw("t3", "C", kind="flash")],
    )
    c = TestClient(create_app(tmp_path, testing=True))
    h = auth(c)
    cat = c.get("/api/catalog").json()
    vid = {t["id"]: t["variant_id"] for t in cat["throws"]}
    assert vid["t1"] != vid["t2"]
    assert c.post("/api/variants/merge", json={"ids": [vid["t1"]]}).status_code == 403  # token required
    assert (
        c.post("/api/variants/merge", headers=h, json={"ids": [vid["t1"], vid["t3"]]}).status_code == 409
    )  # different grenade types
    merged = c.post("/api/variants/merge", headers=h, json={"ids": [vid["t1"], vid["t2"]]})
    assert merged.status_code == 200
    new_id = merged.json()["id"]
    cat = c.get("/api/catalog").json()
    assert {t["id"]: t["variant_id"] for t in cat["throws"]}["t2"] == new_id
    variant = next(v for v in cat["variants"] if v["id"] == new_id)
    assert variant["source"] == "manual" and sorted(variant["members"]) == ["t1", "t2"]
    labelled = c.put(
        f"/api/variants/{new_id}",
        headers=h,
        json={"title": "CT 回防烟", "purpose": "封住中路连接", "reviewed": True, "reviewer": "me"},
    )
    assert labelled.status_code == 200
    split = c.post(f"/api/variants/{new_id}/split", headers=h, json={"throw_ids": ["t2"]})
    assert split.status_code == 200
    cat = c.get("/api/catalog").json()
    vid = {t["id"]: t["variant_id"] for t in cat["throws"]}
    assert vid["t1"] == new_id and vid["t2"] == split.json()["id"] != new_id
    kept = next(v for v in cat["variants"] if v["id"] == new_id)
    assert kept["title"] == "CT 回防烟" and kept["members"] == ["t1"]
    assert c.post(f"/api/variants/{new_id}/split", headers=h, json={"throw_ids": ["t1"]}).status_code == 422
    assert c.post(f"/api/variants/{new_id}/split", headers=h, json={"throw_ids": ["t3"]}).status_code == 422


def test_area_vocabulary_defaults_and_overrides(tmp_path):
    assert place_label("de_ancient", "BombsiteA", {}) == "A 包点"
    assert place_label("de_mirage", "CTSpawn", {}) == "CT 出生点"
    assert place_label("de_ancient", "SomethingUnknown", {}) == "SomethingUnknown"
    assert place_label("de_ancient", "", {}) == ""
    seed_many(tmp_path, [throw("t1", "Alice")])
    c = TestClient(create_app(tmp_path, testing=True))
    h = auth(c)
    assert c.put("/api/places/de_test/Middle", headers=h, json={"label": "中路"}).status_code == 200
    assert c.put("/api/places/de_test/..", headers=h, json={"label": "x"}).status_code in (400, 404, 422)
    cat = c.get("/api/catalog").json()
    row = cat["throws"][0]
    assert row["effect_area"] == "中路" and row["origin_area"] == "CT 出生点"
    assert cat["places"]["de_test"]["Middle"] == "中路"


def test_abnormal_round_requires_resolution_before_approval_and_can_be_excluded(tmp_path):
    rounds = [
        {
            "id": "m1-r1",
            "match_id": "m1",
            "number": 1,
            "is_pistol": True,
            "complete": True,
            "review_required": True,
        },
        {
            "id": "m1-r13",
            "match_id": "m1",
            "number": 13,
            "is_pistol": False,
            "complete": True,
            "review_required": True,
        },
    ]
    seed_many(tmp_path, [throw("t1", "Alice")], rounds)
    c = TestClient(create_app(tmp_path, testing=True))
    h = auth(c)
    approve = {"approved": True, "pro_video": "https://example.org/v", "description": "d", "reviewer": "me"}
    assert c.put("/api/rounds/m1-r1/review", headers=h, json=approve).status_code == 422
    assert (
        c.put("/api/rounds/m1-r1/review", headers=h, json={**approve, "resolution": "confirmed"}).status_code
        == 422
    )  # resolution needs a written basis
    ok = {
        **approve,
        "resolution": "confirmed",
        "resolution_note": "重开后保留最终完整回合",
    }
    assert c.put("/api/rounds/m1-r1/review", headers=h, json=ok).status_code == 200
    fix = {
        "resolution": "confirmed",
        "resolution_note": "第二半场首局，比赛页核对",
        "pistol_override": True,
        "reviewer": "me",
    }
    assert c.put("/api/rounds/m1-r13/review", headers=h, json=fix).status_code == 200
    cat = c.get("/api/catalog").json()
    r1, r13 = sorted(cat["rounds"], key=lambda r: r["number"])
    assert r1["review_required"] is False and r1["review"]["approved"]
    assert r13["is_pistol"] is True and r13["pistol_basis"].startswith("manual")
    excluded = {"resolution": "excluded", "resolution_note": "技术暂停导致重赛", "reviewer": "me"}
    assert c.put("/api/rounds/m1-r13/review", headers=h, json=excluded).status_code == 200
    cat = c.get("/api/catalog").json()
    assert [r["number"] for r in cat["rounds"] if not r.get("excluded")] == [1]
    assert next(r for r in cat["rounds"] if r["number"] == 13)["is_pistol"] is False
