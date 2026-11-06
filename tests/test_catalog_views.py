"""Summary, per-map slices and lookups for the studio (synthetic data, clearly labelled)."""

import pytest
from fastapi.testclient import TestClient

from openingroutes import variants
from openingroutes.api import create_app
from openingroutes.store import Store
from tests.test_workflow import auth

SOURCE = {
    "event": "Synthetic",
    "match": "A v B",
    "date": "2025-01-01",
    "url": "https://example.org/m",
    "verified": True,
    "reviewer": "test",
}


def throw(match_id, n, *, pos=(0, 0, 0), yaw=90.0, effect=(1000, 0, 0), kind="smoke", player="Alice"):
    return {
        "id": f"{match_id}-t{n * 64}-{player}",
        "match_id": match_id,
        "round_id": f"{match_id}-r1",
        "round_number": 1,
        "map": f"de_{match_id[:-1]}",
        "player": player,
        "team": "A",
        "side": "CT",
        "kind": kind,
        "tick": n * 64,
        "time": 1,
        "position": list(pos),
        "view": {"pitch": -10.0, "yaw": yaw},
        "effect_position": list(effect),
        "trajectory": [[n * 64 + i, 0.123456 + i, 1.5 * i, 2.0] for i in range(40)],
        "trajectory_status": "matched",
        "origin_place": "CTSpawn",
        "effect_place": "Middle",
    }


def match(match_id, throws):
    return {
        "id": match_id,
        "map": f"de_{match_id[:-1]}",
        "source": SOURCE,
        "sha256": match_id * 4,
        "rounds": [{"id": f"{match_id}-r1", "match_id": match_id, "number": 1, "is_pistol": True}],
        "formations": {
            f"{match_id}-r1": {
                "round_id": f"{match_id}-r1",
                "ct_team": "A",
                "t_team": "B",
                "complete": True,
                "snapshots": [],
            }
        },
        "throws": throws,
        "warnings": [],
    }


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path)
    store.save_match(
        match(
            "alpha1",
            [
                throw("alpha1", 1),
                throw("alpha1", 2, pos=(10, 0, 0), player="Bob"),
                throw("alpha1", 3, kind="he"),
            ],
        )
    )
    store.save_match(match("alpha2", [throw("alpha2", 1, pos=(20, 0, 0), yaw=60.0, player="Carol")]))
    store.save_match(match("beta1", [throw("beta1", 1), throw("beta1", 2, pos=(900, 0, 0))]))
    return store


def ids(rows):
    return sorted(r["id"] for r in rows)


def groups(rows):
    return sorted((v["id"], tuple(v["members"]), v["source"]) for v in rows)


def test_summary_lists_maps_and_rounds_without_heavy_fields(store):
    summary = store.summary()
    assert summary["schema_version"] == 1
    assert summary["throws"] == [] and summary["variants"] == []
    assert [(m["map"], m["matches"], m["rounds"], m["throws"]) for m in summary["maps"]] == [
        ("de_alpha", 2, 2, 4),
        ("de_beta", 1, 1, 2),
    ]
    assert ids(summary["matches"]) == ["alpha1", "alpha2", "beta1"]
    assert all("throws" not in m and "rounds" not in m and "formations" not in m for m in summary["matches"])
    assert len(summary["rounds"]) == 3 and all("formation" not in r for r in summary["rounds"])
    assert set(summary["places"]) == {"de_alpha", "de_beta"}


def test_map_slice_matches_the_full_catalog_for_that_map(store):
    store.save_teaching("alpha1-t64-Alice", {"title": "Draft", "status": "draft"})
    full = store.catalog()
    part = store.map_slice("de_alpha")
    assert part["map"] == "de_alpha"
    expected = [t for t in full["throws"] if t["map"] == "de_alpha"]
    assert ids(part["throws"]) == ids(expected)
    by_id = {t["id"]: t for t in part["throws"]}
    for row in expected:
        light = by_id[row["id"]]
        assert "trajectory" not in light
        assert {k: v for k, v in light.items() if k != "trajectory_preview"} == {
            k: v for k, v in row.items() if k != "trajectory"
        }
    assert groups(part["variants"]) == groups(v for v in full["variants"] if v["map"] == "de_alpha")
    assert ids(part["rounds"]) == ["alpha1-r1", "alpha2-r1"]
    assert all("formation" in r for r in part["rounds"])


def test_trajectory_preview_is_small_and_keeps_the_end_points(store):
    row = store.map_slice("de_beta")["throws"][0]
    preview, full = row["trajectory_preview"], store.throw(row["id"])["trajectory"]
    assert 2 <= len(preview) <= 12
    assert preview[0][0] == full[0][0] and preview[-1][0] == full[-1][0]
    assert all(isinstance(v, int) for p in preview for v in p)


def test_unknown_map_slice_is_none(store):
    assert store.map_slice("de_missing") is None


def test_throw_lookup_returns_the_full_row(store):
    row = store.throw("beta1-t128-Alice")
    assert row["map"] == "de_beta" and len(row["trajectory"]) == 40 and "gaps" in row
    assert store.throw("nope") is None
    rows = store.throws_by_id(["beta1-t64-Alice", "alpha2-t64-Carol", "nope"])
    assert ids(rows) == ["alpha2-t64-Carol", "beta1-t64-Alice"]
    assert all("trajectory" not in r and r["variant_id"] for r in rows)


def test_throw_lookup_works_for_ids_without_a_match_prefix(tmp_path):
    store = Store(tmp_path)
    row = throw("gamma1", 1)
    store.save_match(match("gamma1", [{**row, "id": "t1"}]))
    assert store.throw("t1")["match_id"] == "gamma1"


def test_variant_groups_are_cached_until_grouping_inputs_change(store, monkeypatch):
    store.catalog()  # CT analysis cached, as after an import
    calls = []
    real = variants.group
    monkeypatch.setattr(variants, "group", lambda *a: calls.append(1) or real(*a))
    first = store.map_slice("de_alpha")["variants"]
    store.map_slice("de_alpha")
    assert len(calls) == 1
    # a label is applied on read and does not regroup
    auto = next(v for v in first if len(v["members"]) > 1)
    store.put("variants", auto["id"], {"id": auto["id"], "source": "auto", "title": "窗口烟"})
    assert (
        next(v for v in store.map_slice("de_alpha")["variants"] if v["id"] == auto["id"])["title"] == "窗口烟"
    )
    assert len(calls) == 1
    # a manual split regroups
    store.put("variants", "v-manual", {"id": "v-manual", "source": "manual", "members": [auto["members"][0]]})
    regrouped = store.map_slice("de_alpha")["variants"]
    assert len(calls) == 2 and any(v["id"] == "v-manual" for v in regrouped)
    # a fresh process reads the disk cache without regrouping
    Store._variant_cache.clear()
    Store(store.root).map_slice("de_alpha")
    assert len(calls) == 2


def test_studio_endpoints_validate_and_serve(store):
    c = TestClient(create_app(store.root, testing=True))
    summary = c.get("/api/catalog/summary")
    assert summary.status_code == 200 and [m["map"] for m in summary.json()["maps"]] == [
        "de_alpha",
        "de_beta",
    ]
    assert c.get("/api/catalog/maps/de_beta").json()["map"] == "de_beta"
    assert c.get("/api/catalog/maps/de_missing").status_code == 404
    assert c.get("/api/catalog/maps/..%2Fx").status_code in (404, 422)
    assert c.get("/api/catalog/maps/DE BETA").status_code == 422
    assert len(c.get("/api/throws/beta1-t64-Alice").json()["trajectory"]) == 40
    assert c.get("/api/throws/nope").status_code == 404
    assert c.get("/api/throws/bad%20id").status_code == 422
    many = c.get("/api/throws", params={"ids": "beta1-t64-Alice,alpha1-t128-Bob"})
    assert ids(many.json()) == ["alpha1-t128-Bob", "beta1-t64-Alice"]
    assert c.get("/api/throws", params={"ids": ",".join(f"x{i}" for i in range(201))}).status_code == 422
    assert c.get("/api/catalog/summary", headers={"Host": "evil.test"}).status_code == 400


def test_writes_do_not_rebuild_the_full_catalog(store, monkeypatch):
    c = TestClient(create_app(store.root, testing=True))
    h = auth(c)
    slices = c.get("/api/catalog/maps/de_alpha").json()
    monkeypatch.setattr(Store, "catalog", lambda self: pytest.fail("full catalog rebuilt"))
    draft = c.put("/api/teachings/alpha1-t64-Alice", headers=h, json={"title": "Draft", "status": "draft"})
    assert draft.status_code == 200
    published = c.put(
        "/api/teachings/alpha1-t64-Alice", headers=h, json={"title": "X", "status": "published"}
    )
    assert published.status_code == 422 and "pro_video" in published.json()["detail"]["gaps"]
    assert c.put("/api/teachings/nope", headers=h, json={"title": "X"}).status_code == 404
    plan = {
        "id": "p1",
        "title": "跨图",
        "area": "Mid",
        "side": "CT",
        "purpose": "x",
        "conditions": "x",
        "steps": [
            {"throw_id": "alpha1-t64-Alice", "role": "a", "time": 1},
            {"throw_id": "beta1-t64-Alice", "role": "b", "time": 2},
        ],
    }
    assert c.put("/api/plans/p1", headers=h, json=plan).status_code == 200
    bad = {**plan, "steps": [{"throw_id": "missing", "role": "a", "time": 1}]}
    assert c.put("/api/plans/p1", headers=h, json=bad).status_code == 422
    pair = [v for v in slices["variants"] if v["kind"] == "smoke"]
    merged = c.post("/api/variants/merge", headers=h, json={"ids": [v["id"] for v in pair[:2]]})
    assert merged.status_code == 200
    after = c.get("/api/catalog/maps/de_alpha").json()
    assert merged.json()["id"] in {t["variant_id"] for t in after["throws"]}
    assert c.get("/api/catalog/summary").json()["plans"][0]["id"] == "p1"
