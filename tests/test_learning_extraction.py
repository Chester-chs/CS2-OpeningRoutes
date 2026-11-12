"""Learning facts keep identity, time and missing evidence explicit."""

import copy

import pandas as pd

from openingroutes import extract
from openingroutes.formations import SNAPSHOT_SECONDS, extract_formations
from openingroutes.store import Store


class Parser:
    def parse_ticks(self, fields, ticks):
        return pd.DataFrame([
            {
                "tick": tick, "steamid": str(pid), "name": f"Player {pid}",
                "X": float(pid), "Y": 20.0, "Z": 0.0,
                "last_place_name": "BombsiteA" if pid < 5 else "TSpawn",
                "team_num": 3 if pid < 5 else 2, "team_clan_name": "Alpha" if pid < 5 else "Beta",
                "is_alive": not (pid == 6 and tick >= 640), "health": 100 if pid != 6 else 0,
                "current_equip_value": 800 if tick == 0 else 400,
                "inventory": [], "armor_value": 0,
            }
            for tick in ticks for pid in range(10)
        ])

    def parse_event(self, name, **kwargs):
        return pd.DataFrame()

    def parse_events(self, names, **kwargs):
        return [(name, []) for name in names]


def round_row(end=2560):
    return {
        "id": "demo-r1", "number": 1, "start_tick": 0, "freeze_end_tick": 0,
        "end_tick": end, "is_pistol": True, "winner": "CT", "complete": True,
        "equipment": [
            {"player_id": str(p), "side": "CT" if p < 5 else "T", "team": "Alpha" if p < 5 else "Beta"}
            for p in range(10)
        ],
    }


def test_t_snapshots_keep_identity_alive_state_and_freeze_equipment():
    result = extract_formations(Parser(), [round_row()], 64)["demo-r1"]
    assert [s["second"] for s in result["snapshots"]] == list(SNAPSHOT_SECONDS)
    assert [s["second"] for s in result["t_snapshots"]] == [0, 5, 10, 15, 20, 25, 30]
    at_ten = result["t_snapshots"][2]["t"]
    assert {p["player_id"] for p in at_ten} == {str(p) for p in range(5, 10)}
    assert next(p for p in at_ten if p["player_id"] == "6")["alive"] is False
    assert result["opening_context"]["t_equip"] == 4000
    assert result["opening_context"]["ct_equip"] == 4000


def test_short_round_never_samples_past_end():
    result = extract_formations(Parser(), [round_row(640)], 64)["demo-r1"]
    assert [s["second"] for s in result["t_snapshots"]] == [0, 5]
    assert result["snapshots"] == []


def test_timeline_places_align_after_sorting_and_missing_coordinate_removal():
    frame = Parser().parse_ticks([], [32, 0, 16])
    frame.loc[(frame.steamid == "0") & (frame.tick == 16), "X"] = None
    frame.loc[(frame.steamid == "0") & (frame.tick == 0), "last_place_name"] = None
    data = extract.make_timeline(frame, {}, "demo-r1", 64, 16)
    player = data["players"]["0"]
    assert [p[0] for p in player["points"]] == [0, 32]
    assert player["places"] == [None, "BombsiteA"]
    assert all(len(p) == 6 for p in player["points"])
    assert data["point_fields"] == ["tick", "x", "y", "z", "side", "alive"]
    assert data["sample_hz"] == 4


def test_contacts_use_ids_and_enemy_damage_only_in_round():
    event = {
        "tick": 100, "attacker_steamid": "5", "user_steamid": "0",
        "attacker_team_num": 2, "user_team_num": 3,
        "attacker_name": "same nickname", "user_name": "same nickname",
        "user_X": 1, "user_Y": 2, "user_Z": 3, "user_last_place_name": "BombsiteA",
    }
    events = {"player_hurt": [event, {**event, "tick": 3000}, {**event, "attacker_team_num": 3}],
              "player_death": [{**event, "tick": 110}]}
    contacts = extract.learning_events(events, round_row())
    assert [(e["kind"], e["tick"]) for e in contacts] == [("hurt", 100), ("death", 110)]
    assert contacts[0]["attacker_id"] == "5" and contacts[0]["victim_id"] == "0"
    assert contacts[0]["victim_position"] == [1, 2, 3]
    assert contacts[0]["victim_place"] == "BombsiteA"


def test_reimport_backfills_learning_without_replacing_source_or_reviews(tmp_path, monkeypatch):
    path = tmp_path / "test.dem"
    path.write_bytes(b"synthetic parser fixture")
    key = extract.file_hash(path)[:20]
    store = Store(tmp_path / "library")
    row = round_row()
    row["id"] = f"{key}-r1"
    source = {"verified": True, "match": "Alpha vs Beta", "reviewer": "curator"}
    original = {
        "id": key, "source": source, "tick_rate": 64, "rounds": [row], "throws": [],
        "players": [], "formations_version": 0, "places_version": extract.PLACES_VERSION,
    }
    store.save_match(copy.deepcopy(original))
    store.put("round_reviews", row["id"], {"resolution": "confirmed", "pistol_override": True})
    monkeypatch.setattr(extract, "DemoParser", lambda _: Parser())
    updated = extract.extract_demo(path, {"verified": False}, store)
    assert updated["source"] == source
    assert updated["learning_version"] == extract.LEARNING_VERSION
    assert store.timeline(row["id"])["players"]["5"]["places"]
    assert updated["rounds"][0]["equipment"][0]["equip"] == 800
    assert store.all("round_reviews")[row["id"]]["pistol_override"] is True
    revision = store.revision()
    assert extract.extract_demo(path, {}, store) == updated
    assert len(store.all("matches")) == 1 and store.revision() == revision
