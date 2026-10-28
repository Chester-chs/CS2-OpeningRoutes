"""Add demo callouts to matches imported before place support.

Usage: python scripts/enrich_places.py DATA_DIR DEMO [DEMO ...]
Only matches already in DATA_DIR are updated; nothing else is imported.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from openingroutes.extract import enrich_places  # noqa: E402
from openingroutes.store import Store  # noqa: E402


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    store = Store(Path(argv[0]))
    for demo in argv[1:]:
        match = enrich_places(Path(demo), store)
        placed = sum(1 for t in match["throws"] if t.get("effect_place"))
        print(f"{match['map']}: {len(match['throws'])} throws, {placed} with an approximate effect area")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
