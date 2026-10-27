"""Export only reviewed learning content and its explicit dependencies."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from .domain import teaching_gaps
from .store import Store, now


def export_bundle(store: Store, output: Path) -> Path:
    catalog = store.catalog()
    verified = {m["id"] for m in catalog["matches"] if m["source"]["verified"]}
    throws = [
        t
        for t in catalog["throws"]
        if t["match_id"] in verified
        and t["teaching"].get("status") == "published"
        and not teaching_gaps(t["teaching"], source_verified=True)
    ]
    round_ids = {t["round_id"] for t in throws}
    round_ids.update(
        r["id"]
        for r in catalog["rounds"]
        if r["match_id"] in verified
        and r.get("review", {}).get("approved")
        and r.get("review", {}).get("pro_video")
    )
    rounds = [r for r in catalog["rounds"] if r["id"] in round_ids]
    match_ids = {r["match_id"] for r in rounds}
    matches = [m for m in catalog["matches"] if m["id"] in match_ids]
    throw_ids = {t["id"] for t in throws}
    plans = [
        p
        for p in catalog["plans"]
        if p.get("status") == "published"
        and p.get("steps")
        and all(s["throw_id"] in throw_ids for s in p["steps"])
    ]
    plan_ids = {p["id"] for p in plans}
    plans = [{**p, "counter_ids": [x for x in p.get("counter_ids", []) if x in plan_ids]} for p in plans]
    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".staging-", dir=output))
    try:
        for row in rounds:
            timeline = store.timeline(row["id"])
            if timeline:
                directory = staging / "timelines"
                directory.mkdir(exist_ok=True)
                (directory / f"{row['id']}.json").write_text(json.dumps(timeline), encoding="utf-8")
        for t in throws:
            for key in ("stance_image", "aim_image", "pro_video", "recreation_video"):
                asset = t["teaching"].get(key, "")
                if asset.startswith("media/"):
                    original = (store.root / asset).resolve()
                    if (
                        not original.is_relative_to((store.root / "media").resolve())
                        or not original.is_file()
                    ):
                        raise ValueError(f"Missing media asset: {key}")
                    (staging / "media").mkdir(exist_ok=True)
                    shutil.copyfile(original, staging / asset)
        bundle = {"schema_version": 1, "matches": matches, "rounds": rounds, "throws": throws, "plans": plans}
        (staging / "catalog.json").write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
        checksums = {
            p.relative_to(staging).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in staging.rglob("*")
            if p.is_file()
        }
        version = uuid4().hex[:12]
        manifest = {
            "schema_version": 1,
            "content_version": version,
            "generated_at": now(),
            "counts": {k: len(v) for k, v in bundle.items() if isinstance(v, list)},
            "files": checksums,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        destination = output / version
        staging.replace(destination)
        return destination
    except Exception:
        shutil.rmtree(staging)
        raise
