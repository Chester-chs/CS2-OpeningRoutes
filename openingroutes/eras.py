"""Curated map eras: periods in which a map's layout is treated as unchanged across patches.

CS2 ships a patch almost every week, but a map's geometry rarely changes, and demos carry no
map-revision hash. Learning profiles therefore pool a map's games by era instead of by exact
patch; each sample keeps its own patch so the split stays auditable. A game outside every era
keeps its exact patch. If a real map change is confirmed inside an era, split the entry into
two non-overlapping ranges with new ids.
"""

import re

MAP_ERAS: dict[str, list[dict]] = {
    # A small A-site scaffolding change around 2026-09-22 is reported but unconfirmed.
    "de_mirage": [
        {"id": "de_mirage:2026-09/10", "label": "2026-09/10", "from": "2026-09-01", "to": "2026-10-31"},
    ],
}


ISO_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")


def era_for(map_name: str, date: str | None, game_version: str | None) -> dict | None:
    """The era a game belongs to; games with an unknown or malformed date or patch never pool."""
    day = (date or "")[:10]
    # extract.py stores "unknown" when a demo header has no patch
    if game_version in (None, "", "unknown") or not ISO_DAY.fullmatch(day):
        return None
    return next((e for e in MAP_ERAS.get(map_name, []) if e["from"] <= day <= e["to"]), None)
