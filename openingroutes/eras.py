"""Curated map eras: periods in which a map's layout is treated as unchanged across patches.

CS2 ships a patch almost every week, but a map's geometry rarely changes, and demos carry no
map-revision hash. Learning profiles therefore pool a map's games by era instead of by exact
patch; each sample keeps its own patch so the split stays auditable. A game outside every era
keeps its exact patch. If a real map change is confirmed inside an era, split the entry into
two non-overlapping ranges with new ids.
"""

MAP_ERAS: dict[str, list[dict]] = {
    # A small A-site scaffolding change around 2026-09-22 is reported but unconfirmed.
    "de_mirage": [
        {"id": "de_mirage:2026-09/10", "label": "2026-09/10", "from": "2026-09-01", "to": "2026-10-31"},
    ],
}


def era_for(map_name: str, date: str, game_version) -> dict | None:
    """The era a game belongs to; games with an unknown date or patch never pool."""
    if not date or not game_version:
        return None
    return next((e for e in MAP_ERAS.get(map_name, []) if e["from"] <= date <= e["to"]), None)
