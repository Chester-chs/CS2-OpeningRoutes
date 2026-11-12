import hashlib
import json

from fastapi.testclient import TestClient

from openingroutes.api import create_app
from openingroutes.publish import export_bundle
from tests.test_profiles import seed_learning
from tests.test_workflow import auth


def test_static_learning_exports_verified_round_evidence_without_teaching_drafts(tmp_path):
    store = seed_learning(tmp_path / "data", matches=2, rounds=2)
    match = store.all("matches")["match1"]
    match["source"]["verified"] = False
    store.save_match(match)
    store.save_teaching("match0-t1-111", {"status": "draft", "title": "PRIVATE TEACHING"})
    store.put(
        "learning_groups", "private-role", {"kind": "role", "confirmed": False, "label": "PRIVATE ROLE"}
    )
    bundle = export_bundle(store, tmp_path / "export")
    catalog = json.loads((bundle / "catalog.json").read_text(encoding="utf-8"))
    assert catalog["schema_version"] == 1 and catalog["learning_index"] == "learning/index.json"
    assert {r["id"] for r in catalog["rounds"]} == {"match0-r1", "match0-r2"}
    assert catalog["throws"] == []
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((bundle / catalog["learning_index"]).read_text(encoding="utf-8"))
    assert index["profiles"] and index["groups"] == {}
    for profile in index["profiles"]:
        path = bundle / f"learning/profiles/{profile['id']}.json"
        detail = json.loads(path.read_text(encoding="utf-8"))
        assert {s["round_id"] for s in detail["samples"]} <= {"match0-r1", "match0-r2"}
        assert all((bundle / f"timelines/{s['round_id']}.json").exists() for s in detail["samples"])
    for name, expected in manifest["files"].items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == expected
        if name.endswith(".json"):
            text = (bundle / name).read_text(encoding="utf-8")
            assert "PRIVATE TEACHING" not in text and "PRIVATE ROLE" not in text


def test_learning_plan_provenance_blocks_cross_round_steps_and_unverified_publication(tmp_path):
    seed_learning(tmp_path)
    client = TestClient(create_app(tmp_path, testing=True))
    plan = {
        "id": "learning-draft",
        "title": "Test learning draft",
        "area": "A",
        "side": "CT",
        "purpose": "Observed sample",
        "conditions": "Pistol",
        "status": "draft",
        "source_round_id": "match0-r1",
        "source_players": ["111"],
        "learning_profile_id": "a" * 24,
        "steps": [{"throw_id": "match0-t1-111", "time": 2, "role": "Same nickname"}],
    }
    assert client.put("/api/plans/learning-draft", json=plan, headers=auth(client)).status_code == 200
    plan["steps"][0]["throw_id"] = "match0-t2-111"
    assert client.put("/api/plans/learning-draft", json=plan, headers=auth(client)).status_code == 422
    plan["steps"][0]["throw_id"] = "match0-t1-111"
    plan["status"] = "published"
    assert client.put("/api/plans/learning-draft", json=plan, headers=auth(client)).status_code == 422
