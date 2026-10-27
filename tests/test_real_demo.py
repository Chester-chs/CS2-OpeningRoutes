"""Opt-in real professional-demo acceptance. No raw demo is included in the repository."""

import os
from pathlib import Path

import pytest

from openingroutes.extract import extract_demo
from openingroutes.store import Store


@pytest.mark.skipif(not os.getenv("CS2_TEST_DEMO"), reason="Set CS2_TEST_DEMO to a professional CS2 demo")
def test_real_professional_demo_extraction_and_duplicate_import(tmp_path):
    source = {
        "event": "PGL Bucharest 2025",
        "match": "Falcons vs G2 · Grand final",
        "date": "2025-04-13",
        "url": "https://www.hltv.org/matches/2381332/falcons-vs-g2-pgl-bucharest-2025",
        "verified": True,
        "reviewer": "Verified roster, date and map score",
    }
    path = Path(os.environ["CS2_TEST_DEMO"])
    store = Store(tmp_path)
    match = extract_demo(path, source, store)
    assert match["map"] in ("de_ancient", "de_mirage")
    assert len(match["players"]) == 10
    assert len(match["rounds"]) > 12
    assert sum(r["is_pistol"] for r in match["rounds"]) == 2
    assert {r["number"] for r in match["rounds"] if r["is_pistol"]} == {1, 13}
    assert match["tick_rate"] == 64
    assert len(match["throws"]) > 300
    assert len({t["id"] for t in match["throws"]}) == len(match["throws"])
    assert any(t["time"] > 30 for t in match["throws"])
    assert all(t["trajectory"] for t in match["throws"])
    assert all(t["origin_place"] for t in match["throws"])
    placed = [t for t in match["throws"] if t["effect_place"]]
    assert len(placed) > len(match["throws"]) // 2
    assert all(t["effect_place_basis"]["distance"] <= 300 for t in placed)
    variants = store.catalog()["variants"]
    assert any(len(v["players"]) > 1 for v in variants)
    for r in match["rounds"]:
        assert len(r["equipment"]) == 10
        timeline = store.timeline(r["id"])
        assert len(timeline["players"]) == 10
        assert (
            max(p[0] for player in timeline["players"].values() for p in player["points"])
            > r["freeze_end_tick"]
        )
    again = extract_demo(path, source, store)
    assert again["id"] == match["id"]
    assert len(store.catalog()["throws"]) == len(match["throws"])
