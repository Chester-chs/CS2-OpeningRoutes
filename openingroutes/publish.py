"""Export only reviewed learning content and its explicit dependencies."""

import hashlib
import json
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

from .domain import teaching_gaps
from .store import Store, now


def export_bundle(store: Store, output: Path, *, include_pistols: bool = False) -> Path:
    catalog = store.catalog()
    learning = store.learning_index(wait=True)
    if learning["state"] != "ready":
        raise ValueError("Learning data changed during export; retry after imports finish")
    learning_key = store._profile_key()
    verified = {m["id"] for m in catalog["matches"] if m["source"]["verified"]}

    def misthrow(t):
        return (t.get("misthrow") or {}).get("flagged")

    # The curator's misthrow notes stay in the studio.
    throws = [
        {k: v for k, v in t.items() if k != "misthrow"}
        for t in catalog["throws"]
        if t["match_id"] in verified
        and t["teaching"].get("status") == "published"
        and not teaching_gaps(t["teaching"], source_verified=True)
        and not misthrow(t)
    ]
    excluded = {r["id"] for r in catalog["rounds"] if r.get("excluded")}
    throws = [t for t in throws if t["round_id"] not in excluded]
    round_ids = {t["round_id"] for t in throws}
    round_ids.update(
        r["id"]
        for r in catalog["rounds"]
        if r["match_id"] in verified
        and r.get("review", {}).get("approved")
        and r.get("review", {}).get("pro_video")
        and not r.get("excluded")
    )
    if include_pistols:
        round_ids.update(
            r["id"]
            for r in catalog["rounds"]
            if r["match_id"] in verified
            and r["is_pistol"]
            and r.get("complete")
            and not r.get("excluded")
            and not r.get("review_required")
        )
    learning_matches = {
        m["id"] for m in catalog["matches"] if m["id"] in verified and m.get("learning_version") == 1
    }
    if learning["profiles"]:
        round_ids.update(
            r["id"]
            for r in catalog["rounds"]
            if r["match_id"] in learning_matches
            and r.get("complete")
            and not r.get("excluded")
            and not r.get("review_required")
        )
    events: dict[str, list] = {key: [] for key in round_ids}
    for t in catalog["throws"]:
        if t["round_id"] in events:
            event = {k: t[k] for k in ("id", "tick", "player_id", "player", "kind", "side") if k in t}
            # Still shown on the round timeline, labelled as a misthrow.
            events[t["round_id"]].append({**event, "misthrow": True} if misthrow(t) else event)
    rounds = [
        {
            **r,
            "observed_throws": sorted(events[r["id"]], key=lambda t: t["tick"]),
            "review": r["review"] if r["review"].get("approved") else {},
        }
        for r in catalog["rounds"]
        if r["id"] in round_ids
    ]
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
        learning_dir = staging / "learning"
        (learning_dir / "profiles").mkdir(parents=True)
        for entry in learning["profiles"]:
            profile = store.learning_profile(entry["id"])
            if profile is None or any(s["round_id"] not in round_ids for s in profile["samples"]):
                raise ValueError("Learning profile has missing round evidence")
            (learning_dir / "profiles" / f"{entry['id']}.json").write_text(
                json.dumps(profile, ensure_ascii=False, allow_nan=False), encoding="utf-8"
            )
        public_learning = {
            **learning,
            "groups": {},
            "coverage": {
                **learning["coverage"],
                "library_rounds": learning["coverage"]["eligible_rounds"],
            },
        }
        (learning_dir / "index.json").write_text(
            json.dumps(public_learning, ensure_ascii=False), encoding="utf-8"
        )
        for row in rounds:
            timeline = store.timeline(row["id"])
            if timeline is None:
                raise ValueError("A selected round has no timeline; reimport its demo before exporting")
            if timeline:
                directory = staging / "timelines"
                directory.mkdir(exist_ok=True)
                (directory / f"{row['id']}.json").write_text(json.dumps(timeline), encoding="utf-8")
        media_refs = [t["teaching"] for t in throws] + [r.get("review", {}) for r in rounds]
        for refs in media_refs:
            for key in ("stance_image", "aim_image", "pro_video", "recreation_video"):
                asset = refs.get(key, "")
                if asset.startswith("media/"):
                    original = (store.root / asset).resolve()
                    if (
                        not original.is_relative_to((store.root / "media").resolve())
                        or not original.is_file()
                    ):
                        raise ValueError(f"Missing media asset: {key}")
                    (staging / "media").mkdir(exist_ok=True)
                    shutil.copyfile(original, staging / asset)
        variants = [
            {**v, "members": [m for m in v["members"] if m in throw_ids]}
            for v in catalog.get("variants", [])
            if any(m in throw_ids for m in v["members"])
        ]
        # CT research is aggregated from source-verified matches only (Store.ct_patterns). The
        # per-round lists stay in the studio; a representative round is linked only if exported.
        exported_rounds = {r["id"] for r in rounds}
        ct_patterns = {
            map_name: {
                **{k: v for k, v in analysis.items() if k != "assignments"},
                "patterns": [
                    {
                        **{k: v for k, v in pattern.items() if k != "round_ids"},
                        "representative": pattern.get("representative")
                        if pattern.get("representative") in exported_rounds
                        else "",
                    }
                    for pattern in analysis.get("patterns", [])
                ],
            }
            for map_name, analysis in (catalog.get("ct_patterns") or {}).items()
        }
        used_maps = {m["map"] for m in matches} | set(ct_patterns)
        places = {k: v for k, v in catalog.get("places", {}).items() if k in used_maps}
        bundle = {
            "schema_version": 1,
            "matches": matches,
            "rounds": rounds,
            "throws": throws,
            "plans": plans,
            "variants": variants,
            "places": places,
            "ct_patterns": ct_patterns,
            "learning_index": "learning/index.json",
        }
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
        if store._profile_key() != learning_key:
            raise ValueError("Learning sources changed during export; retry after the update finishes")
        staging.replace(destination)
        return destination
    except Exception:
        shutil.rmtree(staging)
        raise
