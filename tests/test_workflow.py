"""Local API, publication and provenance integration tests with explicit synthetic data."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from openingroutes.api import create_app
from openingroutes.store import Store


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path, testing=True)
    with TestClient(app) as c:
        yield c


def auth(c):
    return {"X-Session-Token": c.get("/api/session").json()["token"]}


def seed(root):
    store = Store(root)
    source = {"event": "Synthetic test event", "match": "A v B", "date": "2025-01-01",
              "url": "https://example.org/match", "verified": True, "reviewer": "test"}
    match = {"id": "m1", "map": "de_test", "source": source, "sha256": "a" * 64,
             "rounds": [{"id": "m1-r1", "match_id": "m1", "number": 1, "is_pistol": True}],
             "throws": [{"id": "t1", "match_id": "m1", "round_id": "m1-r1", "player": "A",
                         "side": "CT", "kind": "smoke", "tick": 64, "time": 1}],
             "warnings": []}
    store.save_match(match)
    return store


def test_local_api_rejects_cross_origin_and_missing_write_token(client):
    assert client.get("/api/session", headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.post("/api/export", json={}).status_code == 403
    assert client.get("/api/catalog", headers={"Host": "evil.test"}).status_code == 400


def test_import_rejects_invalid_file_and_source(client):
    response = client.post("/api/import", headers=auth(client),
                           files={"demo": ("bad.dem", b"not a demo")},
                           data={"source": json.dumps({"event": "x"})})
    assert response.status_code == 422


def test_catalog_and_draft_teaching_persist(tmp_path):
    store = seed(tmp_path)
    store.save_teaching("t1", {"title": "Synthetic draft", "status": "draft"})
    reopened = Store(tmp_path)
    assert reopened.catalog()["throws"][0]["teaching"]["title"] == "Synthetic draft"
    assert reopened.catalog()["rounds"][0]["is_pistol"] is True
    assert reopened.catalog()["matches"][0]["sha256"] == "a" * 64


def test_incomplete_tutorial_cannot_publish(tmp_path):
    seed(tmp_path)
    c = TestClient(create_app(tmp_path, testing=True))
    result = c.put("/api/teachings/t1", headers=auth(c), json={"title": "Incomplete", "status": "published"})
    assert result.status_code == 422
    assert "pro_video" in result.json()["detail"]["gaps"]


def test_export_does_not_publish_drafts_or_local_notes(tmp_path):
    store = seed(tmp_path)
    store.save_teaching("t1", {"title": "Private draft", "status": "draft"})
    from openingroutes.publish import export_bundle
    exported = export_bundle(store, tmp_path / "export")
    manifest = json.loads((exported / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    catalog = json.loads((exported / "catalog.json").read_text())
    assert catalog["throws"] == []
    assert catalog["rounds"] == []
    assert "Private draft" not in (exported / "catalog.json").read_text()


def test_complete_tutorial_export_copies_only_owned_referenced_media(tmp_path):
    store = seed(tmp_path)
    from openingroutes.domain import TEACHING_FIELDS
    teaching = {key: "Confirmed" for key in TEACHING_FIELDS}
    teaching.update(stance_image="media/stance.png", aim_image="media/aim.png",
                    pro_video="https://example.org/video.mp4", reproduction="verified",
                    status="published")
    (tmp_path / "media").mkdir(exist_ok=True)
    for name in ("stance.png", "aim.png", "private.png"):
        (tmp_path / "media" / name).write_bytes(b"test-image")
    store.save_teaching("t1", teaching)
    from openingroutes.publish import export_bundle
    exported = export_bundle(store, tmp_path / "export")
    catalog = json.loads((exported / "catalog.json").read_text())
    assert len(catalog["throws"]) == 1
    assert len(catalog["rounds"]) == 1
    assert (exported / "media/stance.png").exists()
    assert not (exported / "media/private.png").exists()
    assert str(Path(tmp_path)) not in (exported / "catalog.json").read_text()
