"""Botched grenades are hidden from learning content but kept as records (synthetic data)."""

import json
from contextlib import closing

import pytest
from fastapi.testclient import TestClient

from openingroutes import misthrows, variants
from openingroutes.api import create_app
from openingroutes.domain import TEACHING_FIELDS
from openingroutes.publish import export_bundle
from openingroutes.store import Store
from tests.test_variants import seed_many, throw
from tests.test_workflow import auth


def lineup(count=3, **kwargs):
    """The same lineup thrown by different players: t1, t2, ..."""
    return [throw(f"t{i + 1}", f"P{i}", pos=(i, 0, 0), **kwargs) for i in range(count)]


def evaluate(rows, *, decisions=None, protected=()):
    groups, auto = misthrows.evaluate(rows, [], decisions or {}, set(protected))
    return {m: g for g in groups for m in g["members"]}, auto


def test_bounce_back_flags_one_off_smokes_and_he_that_land_next_to_the_release():
    rows = [
        throw("t1", "A", effect=(199, 0, 0)),
        throw("t2", "A", pos=(5000, 0, 0), effect=(5200, 0, 0)),  # exactly at the radius: kept
        throw("t3", "A", pos=(0, 5000, 0), effect=(0, 5100, 0), kind="flash"),  # overhead pop flash
        throw("t4", "A", pos=(0, 9000, 0), effect=(0, 9100, 0), kind="he"),
        throw("t5", "A", pos=(9000, 0, 0), effect=None, kind="molotov"),  # no landing point recorded
        throw("t6", "A", pos=(9000, 9000, 0), effect=(9000, 9050, 0), kind="decoy"),
        # thrown straight up: it comes down where it was released by design
        throw("t7", "A", pos=(-5000, 0, 0), effect=(-5000, 5, 0), kind="he", pitch=-89.0),
    ]
    by_member, auto = evaluate(rows)
    assert sorted(auto) == ["t1", "t4"]
    assert auto["t1"] == {"rule": "bounce_back", "distance": 199}
    assert sorted(by_member) == ["t2", "t3", "t5", "t6", "t7"]


def test_a_repeated_throw_is_deliberate_even_when_it_lands_next_to_the_release():
    # Several players throwing an HE straight up from the same spot is a lineup, not a mistake.
    rows = [throw(f"t{i}", f"P{i}", pos=(i, 0, 0), effect=(i, 5, 0), kind="he") for i in (1, 2)]
    by_member, auto = evaluate(rows)
    assert auto == {} and by_member["t1"]["members"] == ["t1", "t2"]


def test_single_throw_far_from_an_established_lineup_is_an_outlier():
    rows = [
        *lineup(),
        throw("t10", "X", pos=(50, 0, 0), yaw=91.0, effect=(1750, 0, 0)),  # same spot and aim
        throw("t11", "X", pos=(-60, 0, 0), effect=(1749, 0, 0)),  # just inside the radius
        throw("t12", "X", pos=(97, 0, 0), effect=(3000, 0, 0)),  # released elsewhere
        throw("t13", "X", pos=(50, 0, 70), effect=(3000, 0, 0)),  # another floor
        throw("t14", "X", pos=(50, 0, 0), yaw=94.0, effect=(3000, 0, 0)),  # another aim
    ]
    by_member, auto = evaluate(rows)
    assert sorted(auto) == ["t10"]
    assert auto["t10"] == {
        "rule": "variant_outlier",
        "distance": 750,
        "variant_id": by_member["t1"]["id"],
    }
    assert "t10" not in by_member and by_member["t11"]["members"] == ["t11"]


def test_outliers_need_an_established_lineup_and_are_never_repeated_throws():
    far = throw("t10", "X", pos=(50, 0, 0), effect=(3000, 0, 0))
    assert evaluate([*lineup(count=2), far])[1] == {}  # two throws are not an established lineup
    # The same release with two landing points, both repeated: a jump throw and a standing throw.
    repeated = [
        *lineup(),
        throw("t10", "X", effect=(3000, 0, 0)),
        throw("t11", "Y", effect=(3010, 0, 0)),
    ]
    by_member, auto = evaluate(repeated)
    assert auto == {} and by_member["t10"]["members"] == ["t10", "t11"]


def flagged_rows():
    return [
        *lineup(),
        throw("t10", "X", effect=(100, 0, 0)),  # bounce-back
        throw("t11", "Y", pos=(50, 0, 0), effect=(3000, 0, 0)),  # outlier of the lineup
    ]


def test_curator_decisions_win_over_the_rules():
    decisions = {"t10": {"decision": "keep"}, "t2": {"decision": "misthrow"}}
    by_member, auto = evaluate(flagged_rows(), decisions=decisions)
    assert "t10" in by_member and auto["t10"]["rule"] == "bounce_back"  # kept, basis still shown
    assert "t2" not in by_member and by_member["t1"]["members"] == ["t1", "t3"]
    assert sorted(auto) == ["t10"]  # two members left: no longer an established lineup
    status = misthrows.status("t10", auto, decisions, set())
    assert status["flagged"] is False and status["source"] == "manual" and status["auto"]
    assert misthrows.status("t2", auto, decisions, set())["flagged"] is True
    assert misthrows.status("t1", auto, decisions, set()) is None


def test_a_published_lesson_is_never_hidden_by_the_rules():
    by_member, auto = evaluate([throw("t1", "A", effect=(100, 0, 0))], protected={"t1"})
    assert "t1" in by_member
    status = misthrows.status("t1", auto, {}, {"t1"})
    assert status["flagged"] is False and status["conflict"] is True


@pytest.fixture
def library(tmp_path):
    return seed_many(tmp_path, flagged_rows())


def by_id(rows):
    return {r["id"]: r for r in rows}


def test_catalog_and_map_slice_mark_misthrows_and_leave_them_out_of_variants(library):
    full = library.catalog()
    part = library.map_slice("de_test")
    for throws, groups in ((full["throws"], full["variants"]), (part["throws"], part["variants"])):
        rows = by_id(throws)
        assert rows["t10"]["misthrow"]["flagged"] and rows["t10"]["misthrow"]["source"] == "auto"
        assert rows["t10"]["misthrow"]["auto"]["rule"] == "bounce_back"
        assert rows["t11"]["misthrow"]["auto"]["rule"] == "variant_outlier"
        assert rows["t10"]["variant_id"] is None and "misthrow" in rows["t10"]["gaps"]
        assert "misthrow" not in rows["t1"] and "misthrow" not in rows["t1"]["gaps"]
        assert sorted(m for g in groups for m in g["members"]) == ["t1", "t2", "t3"]
    assert library.throw("t11")["misthrow"]["flagged"] is True


def test_grouping_is_cached_until_a_decision_changes(library, monkeypatch):
    library.catalog()  # CT analysis cached, as after an import
    calls = []
    real = variants.group
    monkeypatch.setattr(variants, "group", lambda *a: calls.append(1) or real(*a))
    library.map_slice("de_test")
    library.put("misthrows", "t10", {"decision": "keep", "note": "", "reviewer": "me"})
    kept = by_id(library.map_slice("de_test")["throws"])["t10"]
    assert len(calls) == 2 and kept["misthrow"]["flagged"] is False and kept["variant_id"]
    # a fresh process reads the disk cache without regrouping
    Store._variant_cache.clear()
    Store._memo.clear()
    reread = by_id(Store(library.root).map_slice("de_test")["throws"])
    assert len(calls) == 2
    assert reread["t10"]["misthrow"]["auto"]["rule"] == "bounce_back"
    assert reread["t11"]["misthrow"]["flagged"] is True


def test_curator_marks_restores_and_clears_through_the_api(library):
    c = TestClient(create_app(library.root, testing=True))
    h = auth(c)
    body = {"decision": "misthrow", "note": "撞到门框", "reviewer": "me"}
    assert c.put("/api/throws/t1/misthrow", json=body).status_code == 403  # token required
    assert c.put("/api/throws/nope/misthrow", headers=h, json=body).status_code == 404
    assert c.put("/api/throws/bad%20id/misthrow", headers=h, json=body).status_code == 422
    assert c.put("/api/throws/t1/misthrow", headers=h, json={"decision": "maybe"}).status_code == 422
    assert c.put("/api/throws/t1/misthrow", headers=h, json={**body, "extra": 1}).status_code == 422
    marked = c.put("/api/throws/t1/misthrow", headers=h, json=body)
    assert marked.status_code == 200 and marked.json()["flagged"] is True
    row = c.get("/api/throws/t1").json()
    assert row["misthrow"]["source"] == "manual" and row["misthrow"]["note"] == "撞到门框"
    assert row["variant_id"] is None
    restored = c.put("/api/throws/t10/misthrow", headers=h, json={"decision": "keep", "reviewer": "me"})
    assert restored.json()["flagged"] is False and restored.json()["auto"]["rule"] == "bounce_back"
    assert c.delete("/api/throws/t10/misthrow", headers=h).status_code == 200
    assert c.get("/api/throws/t10").json()["misthrow"]["source"] == "auto"
    assert c.delete("/api/throws/t10/misthrow", headers=h).status_code == 404
    with closing(library.connect()) as db:
        trail = db.execute("SELECT COUNT(*) FROM revisions WHERE entity IN ('t1','t10')").fetchone()[0]
    assert trail == 3


def complete_teaching(root):
    teaching = {key: "Confirmed" for key in TEACHING_FIELDS}
    for key in ("stance_image", "aim_image", "pro_video"):
        teaching[key] = f"media/{key}.png"
        (root / "media" / f"{key}.png").write_bytes(b"\x89PNG\r\n\x1a\nx")
    return {**teaching, "reproduction": "verified", "status": "published"}


def test_misthrows_cannot_be_published_and_published_lessons_cannot_be_marked(library):
    c = TestClient(create_app(library.root, testing=True))
    h = auth(c)
    teaching = complete_teaching(library.root)
    blocked = c.put("/api/teachings/t10", headers=h, json=teaching)
    assert blocked.status_code == 422 and blocked.json()["detail"]["gaps"] == ["misthrow"]
    assert c.put("/api/teachings/t10", headers=h, json={**teaching, "status": "draft"}).status_code == 200
    assert c.put("/api/teachings/t1", headers=h, json=teaching).status_code == 200
    body = {"decision": "misthrow", "reviewer": "me"}
    assert c.put("/api/throws/t1/misthrow", headers=h, json=body).status_code == 409
    plan = {
        "id": "p1",
        "title": "x",
        "area": "Mid",
        "side": "CT",
        "purpose": "x",
        "conditions": "x",
        "steps": [{"throw_id": "t2", "role": "a", "time": 1}],
    }
    assert c.put("/api/plans/p1", headers=h, json=plan).status_code == 200
    # a draft plan does not block the decision
    assert c.put("/api/throws/t2/misthrow", headers=h, json=body).status_code == 200


def test_throws_in_a_published_plan_are_protected(library):
    c = TestClient(create_app(library.root, testing=True))
    h = auth(c)
    teaching = {**complete_teaching(library.root), "status": "review"}
    plan = {
        "id": "p1",
        "title": "x",
        "area": "Mid",
        "side": "CT",
        "purpose": "x",
        "conditions": "x",
        "steps": [{"throw_id": t, "role": "a", "time": 1} for t in ("t3", "t10")],
        "status": "published",
    }
    for throw_id in ("t3", "t10"):
        library.save_teaching(throw_id, teaching)
    library.put("plans", "p1", plan)
    # the bounce-back rule matches t10, but a published plan is built on it
    state = c.get("/api/throws/t10").json()["misthrow"]
    assert state["flagged"] is False and state["conflict"] is True
    body = {"decision": "misthrow", "reviewer": "me"}
    assert c.put("/api/throws/t3/misthrow", headers=h, json=body).status_code == 409


def test_marking_the_first_throw_of_a_named_lineup_keeps_its_name(library):
    c = TestClient(create_app(library.root, testing=True))
    h = auth(c)
    named = by_id(c.get("/api/catalog/maps/de_test").json()["throws"])["t1"]["variant_id"]
    label = {"title": "中路窗口烟", "purpose": "封窗口", "reviewed": True, "reviewer": "me"}
    assert c.put(f"/api/variants/{named}", headers=h, json=label).status_code == 200
    body = {"decision": "misthrow", "reviewer": "me"}
    assert c.put("/api/throws/t1/misthrow", headers=h, json=body).status_code == 200
    after = c.get("/api/catalog/maps/de_test").json()
    group = next(v for v in after["variants"] if "t2" in v["members"])
    assert group["members"] == ["t2", "t3"] and group["title"] == "中路窗口烟"
    assert group["reviewed"] is True


def test_export_leaves_out_misthrows_but_keeps_them_on_the_round_timeline(library):
    teaching = complete_teaching(library.root)
    library.save_teaching("t1", teaching)
    library.save_teaching("t2", teaching)
    library.put("misthrows", "t2", {"decision": "misthrow", "note": "", "reviewer": "me"})
    exported = export_bundle(library, library.root / "export")
    catalog = json.loads((exported / "catalog.json").read_text(encoding="utf-8"))
    assert [t["id"] for t in catalog["throws"]] == ["t1"]
    assert [m for v in catalog["variants"] for m in v["members"]] == ["t1"]
    seen = by_id(catalog["rounds"][0]["observed_throws"])
    assert seen["t2"]["misthrow"] is True and seen["t10"]["misthrow"] is True
    assert "misthrow" not in seen["t1"]


def test_library_from_before_misthrows_opens(tmp_path):
    store = seed_many(tmp_path, [throw("t1", "A")])
    with closing(store.connect()) as db, db:
        db.execute("DROP TABLE misthrows")
    assert "misthrow" not in Store(tmp_path).catalog()["throws"][0]
