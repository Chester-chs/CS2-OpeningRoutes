"""Prepare a read-only static site, either reviewed publication or explicit local preview."""

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--local-preview", action="store_true")
    args = parser.parse_args()
    from openingroutes.publish import export_bundle
    from openingroutes.store import Store, now

    store = Store(args.data)
    destination = ROOT / ("artifacts/web-preview" if args.local_preview else "artifacts/web")
    if destination.exists():
        if (
            not destination.resolve().is_relative_to((ROOT / "artifacts").resolve())
            or destination.is_symlink()
        ):
            raise ValueError("Refusing to replace an artifact outside the output workspace")
        shutil.rmtree(destination)
    shutil.copytree(ROOT / "web/dist", destination)
    content = destination / "content"
    if not args.local_preview:
        exported = export_bundle(store, store.root / "exports")
        shutil.copytree(exported, content)
    else:
        content.mkdir()
        catalog = store.catalog()
        # Local preview includes observed facts only, never private teaching drafts or personal notes.
        for row in catalog["throws"]:
            row["teaching"] = {}
        catalog["plans"] = []
        for row in catalog["rounds"]:
            row["review"] = {}
        (content / "catalog.json").write_text(json.dumps(catalog, ensure_ascii=False), encoding="utf-8")
        (content / "timelines").mkdir()
        for row in catalog["rounds"]:
            timeline = store.timeline(row["id"])
            if timeline:
                (content / "timelines" / f"{row['id']}.json").write_text(
                    json.dumps(timeline), encoding="utf-8"
                )
        files = {
            p.relative_to(content).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in content.rglob("*")
            if p.is_file()
        }
        manifest = {
            "schema_version": 1,
            "content_version": "local-observations-preview",
            "channel": "local-preview",
            "generated_at": now(),
            "files": files,
        }
        (content / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
