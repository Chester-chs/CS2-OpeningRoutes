"""Chinese labels for demo place names (``last_place_name``).

Only generic, unambiguous callouts get a default label. Community nicknames
(for example Ancient "黑屋") are never guessed: the curator records them per
map through the local API, and unknown names are shown unchanged.
"""

import re

GENERIC = {
    "CTSpawn": "CT 出生点",
    "TSpawn": "T 出生点",
    "BombsiteA": "A 包点",
    "BombsiteB": "B 包点",
    "Middle": "中路",
}
PLACE = r"^[A-Za-z0-9_]{1,64}$"
MAP = r"^[a-z0-9_]{1,64}$"


def valid_place(map_name: str, place: str) -> bool:
    return bool(re.fullmatch(MAP, map_name or "") and re.fullmatch(PLACE, place or ""))


def place_label(map_name: str, place: str | None, overrides: dict) -> str:
    if not place:
        return ""
    custom = overrides.get(map_name, {}).get(place)
    return custom or GENERIC.get(place, place)
