import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from openingroutes.api import create_app
from openingroutes.domain import TEACHING_FIELDS
from openingroutes.store import Store, now
from tests.test_workflow import auth, seed


def source():
    return {
        "event": "Synthetic",
        "match": "A v B",
        "date": "2025-01-01",
        "url": "https://example.org",
        "verified": False,
        "reviewer": "",
    }


def test_source_verification_and_unsafe_source(tmp_path):
    seed(tmp_path)
    c = TestClient(create_app(tmp_path, testing=True))
    headers = auth(c)
    assert (
        c.put("/api/sources/m1", headers=headers, json={**source(), "url": "file:///bad"}).status_code == 422
    )
    assert c.put("/api/sources/m1", headers=headers, json={**source(), "verified": True}).status_code == 422
    assert c.put("/api/sources/missing", headers=headers, json=source()).status_code == 404
    assert (
        c.put(
            "/api/sources/m1", headers=headers, json={**source(), "verified": True, "reviewer": "Human"}
        ).status_code
        == 200
    )


def test_media_magic_traversal_and_missing_asset(tmp_path):
    seed(tmp_path)
    c = TestClient(create_app(tmp_path, testing=True))
    headers = auth(c)
    assert c.post("/api/media", headers=headers, files={"asset": ("x.html", b"<script/>")}).status_code == 422
    assert c.post("/api/media", headers=headers, files={"asset": ("x.png", b"bad")}).status_code == 422
    result = c.post(
        "/api/media", headers=headers, files={"asset": ("../../secret.png", b"\x89PNG\r\n\x1a\nabc")}
    )
    assert result.status_code == 200
    assert result.json()["url"].startswith("media/")
    assert ".." not in result.json()["url"]
    assert c.get("/" + result.json()["url"]).status_code == 200
    assert (
        c.put("/api/teachings/t1", headers=headers, json={"stance_image": "media/../bad"}).status_code == 422
    )
    complete = {key: "Confirmed" for key in TEACHING_FIELDS}
    complete.update(
        stance_image="media/missing.png",
        aim_image="https://example.org/a.png",
        pro_video="https://example.org/v.mp4",
        reproduction="verified",
        status="published",
    )
    assert c.put("/api/teachings/t1", headers=headers, json=complete).status_code == 422
    complete["stance_image"] = result.json()["url"]
    assert c.put("/api/teachings/t1", headers=headers, json=complete).status_code == 200
    assert c.put("/api/teachings/missing", headers=headers, json={}).status_code == 404
    exported = c.post("/api/export", headers=headers)
    assert exported.status_code == 200
    assert c.get(exported.json()["download"]).status_code == 200
    assert c.get("/api/exports/not-a-version").status_code == 404
    assert c.get("/api/exports/000000000000").status_code == 404


def test_round_review_and_plan_dependencies(tmp_path):
    store = seed(tmp_path)
    match = store.all("matches")["m1"]
    match["rounds"][0].update(complete=True, review_required=False)
    store.save_match(match)
    c = TestClient(create_app(tmp_path, testing=True))
    headers = auth(c)
    assert c.put("/api/rounds/m1-r1/review", headers=headers, json={"approved": True}).status_code == 422
    assert c.put("/api/rounds/missing/review", headers=headers, json={}).status_code == 404
    assert (
        c.put("/api/rounds/m1-r1/review", headers=headers, json={"pro_video": "javascript:bad"}).status_code
        == 422
    )
    assert (
        c.put(
            "/api/rounds/m1-r1/review",
            headers=headers,
            json={
                "approved": True,
                "pro_video": "https://example.org/v.mp4",
                "reviewer": "Human",
                "description": "Confirmed",
            },
        ).status_code
        == 200
    )
    plan = {
        "id": "p1",
        "title": "Synthetic",
        "area": "Test",
        "side": "CT",
        "purpose": "Test",
        "conditions": "Test",
        "steps": [{"throw_id": "t1", "role": "Anchor", "time": 0}],
    }
    assert c.put("/api/plans/p1", headers=headers, json=plan).status_code == 200
    assert c.put("/api/plans/p1", headers=headers, json={**plan, "status": "published"}).status_code == 422
    assert c.put("/api/plans/p2", headers=headers, json=plan).status_code == 422
    plan["steps"][0]["throw_id"] = "missing"
    assert c.put("/api/plans/p1", headers=headers, json=plan).status_code == 422


def test_task_recovery_timeline_and_request_limits(tmp_path):
    store = seed(tmp_path)
    store.put("jobs", "old", {"id": "old", "status": "parsing", "created_at": now()})
    store.write_timeline("m1-r1", {"players": {}})
    c = TestClient(create_app(tmp_path, testing=True))
    headers = auth(c)
    assert c.get("/api/jobs").json()[0]["status"] == "interrupted"
    assert c.get("/api/timelines/m1-r1").json() == {"players": {}}
    assert c.get("/api/timelines/missing").status_code == 404
    assert c.get("/api/timelines/bad%20id").status_code == 400
    assert (
        c.post("/api/export", headers={**headers, "Content-Length": str(3 * 1024**3)}, json={}).status_code
        == 413
    )
    with pytest.raises(ValueError):
        store.all("arbitrary")
    with pytest.raises(ValueError):
        store.put("arbitrary", "x", {})


def test_import_validation_and_background_failure(tmp_path):
    c = TestClient(create_app(tmp_path, testing=True))
    headers = auth(c)
    fields = {"source": json.dumps(source())}
    assert (
        c.post("/api/import", headers=headers, data=fields, files={"demo": ("bad.zip", b"x")}).status_code
        == 422
    )
    assert (
        c.post("/api/import", headers=headers, data=fields, files={"demo": ("bad.dem", b"x")}).status_code
        == 422
    )
    assert list((tmp_path / "uploads").iterdir()) == []
    assert (
        c.post(
            "/api/import",
            headers=headers,
            data={"source": json.dumps({**source(), "verified": True})},
            files={"demo": ("valid.dem", b"PBDEMS2\x00abc")},
        ).status_code
        == 422
    )
    with patch("openingroutes.api.subprocess.Popen") as process:
        process.return_value.wait.return_value = 1
        result = c.post(
            "/api/import", headers=headers, data=fields, files={"demo": ("valid.dem", b"PBDEMS2\x00abc")}
        )
        assert result.status_code == 202
        import time

        for _ in range(100):
            if Store(tmp_path).all("jobs")[result.json()["id"]]["status"] == "failed":
                break
            time.sleep(0.01)
        assert Store(tmp_path).all("jobs")[result.json()["id"]]["status"] == "failed"


def test_queued_job_can_be_cancelled(tmp_path):
    store = seed(tmp_path)
    c = TestClient(create_app(tmp_path, testing=True))
    store.put("jobs", "queued", {"id": "queued", "status": "queued", "created_at": now()})
    result = c.post("/api/jobs/queued/cancel", headers=auth(c), json={})
    assert result.status_code == 200
    assert store.all("jobs")["queued"]["status"] == "cancelled"
    assert c.post("/api/jobs/queued/cancel", headers=auth(c), json={}).status_code == 409
    assert c.post("/api/jobs/missing/cancel", headers=auth(c), json={}).status_code == 404


def test_worker_persists_complete_and_failure(tmp_path):
    from openingroutes.worker import work

    store = Store(tmp_path)
    for key in ("success", "failure"):
        store.put("jobs", key, {"id": key, "source": source(), "created_at": now(), "status": "queued"})

    def fake_extract(path, source, store, progress):
        progress("routes")
        return {"id": "m"}

    with patch("openingroutes.worker.extract_demo", side_effect=fake_extract):
        work(tmp_path, "success")
    assert store.all("jobs")["success"]["status"] == "complete"
    with patch("openingroutes.worker.extract_demo", side_effect=ValueError("bad format")):
        with pytest.raises(ValueError):
            work(tmp_path, "failure")
    assert store.all("jobs")["failure"]["status"] == "failed"


def test_editing_verified_actions_requires_explicit_reverification(tmp_path):
    store = seed(tmp_path)
    complete = {key: "Confirmed" for key in TEACHING_FIELDS}
    complete.update(
        stance_image="https://example.org/s.png",
        aim_image="https://example.org/a.png",
        pro_video="https://example.org/v.mp4",
        reproduction="verified",
        status="published",
    )
    store.save_teaching("t1", complete)
    c = TestClient(create_app(tmp_path, testing=True))
    changed = {**complete, "operation": "Changed instructions"}
    rejected = c.put("/api/teachings/t1", headers=auth(c), json=changed)
    assert rejected.status_code == 422
    assert "reproduction" in rejected.json()["detail"]["gaps"]
    accepted = c.put("/api/teachings/t1", headers=auth(c), json={**changed, "verification_confirmed": True})
    assert accepted.status_code == 200
