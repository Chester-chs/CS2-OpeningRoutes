"""Time the studio catalog endpoints and report where the payload bytes go.

Usage: python scripts/bench_catalog.py DATA_DIR
Run it on a copy: it writes derived caches under DATA_DIR/cache. The working
library .local/data is refused.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from openingroutes.store import Store  # noqa: E402


def size(value) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def timed(label, fn):
    start = time.perf_counter()
    result = fn()
    print(f"{label}: {time.perf_counter() - start:.2f} s")
    return result


def report(label, rows, fields):
    total = size(rows)
    parts = {f: sum(size(r.get(f)) for r in rows if f in r) for f in fields}
    detail = ", ".join(f"{f} {v / 1e6:.1f}" for f, v in sorted(parts.items(), key=lambda x: -x[1]))
    print(f"  {label}: {total / 1e6:.1f} MB ({detail})")


def main(argv):
    if len(argv) != 1:
        print(__doc__)
        return 2
    data = Path(argv[0]).resolve()
    if data == (ROOT / ".local" / "data").resolve():
        print("Refusing to benchmark the working library; copy it first.")
        return 2
    store = Store(data)
    catalog = timed("catalog", store.catalog)
    timed("catalog (warm)", store.catalog)
    print(f"catalog payload: {size(catalog) / 1e6:.1f} MB")
    for key in ("matches", "rounds", "throws", "variants", "ct_patterns", "plans", "places"):
        print(f"  {key}: {size(catalog.get(key)) / 1e6:.1f} MB")
    report("throws", catalog["throws"], ["trajectory", "teaching", "gaps", "view", "position"])
    report("rounds", catalog["rounds"], ["formation", "ct_pattern", "equipment", "events", "players"])
    if hasattr(store, "summary"):
        summary = timed("summary", store.summary)
        print(f"summary payload: {size(summary) / 1e6:.1f} MB")
        for row in summary["maps"]:
            map_slice = timed(f"map {row['map']}", lambda m=row["map"]: store.map_slice(m))
            print(f"  {row['map']} payload: {size(map_slice) / 1e6:.1f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
