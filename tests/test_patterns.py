import random

from openingroutes.formations import canonical_teams, finalize_formations
from openingroutes.patterns import (
    CITATION,
    analyze_map,
    draft_name,
    macro_area,
    rule_label,
    setup_string,
)

SPOTS = {
    "BombsiteA": (-300, -1700, -160),
    "BombsiteB": (-1900, 300, -160),
    "Connector": (-700, -900, -100),
    "CTSpawn": (-1200, -2200, -170),
}
SETUPS = [
    ["BombsiteA", "BombsiteA", "Connector", "BombsiteB", "BombsiteB"],
    ["BombsiteA", "BombsiteA", "BombsiteA", "BombsiteA", "BombsiteB"],
    ["Connector", "Connector", "Connector", "BombsiteB", "CTSpawn"],
]


def formation(i, team, setup, rng, winner):
    snaps = []
    for second in (10, 12, 15, 18, 20):
        players = []
        for slot, place in enumerate(SETUPS[setup]):
            x, y, z = SPOTS[place]
            players.append(
                {
                    "player_id": f"{team}-{slot}",
                    "player": f"{team}{slot}",
                    "place": place,
                    "x": x + rng.uniform(-40, 40),
                    "y": y + rng.uniform(-40, 40),
                    "z": z,
                    "alive": True,
                    "equip": 4000,
                }
            )
        snaps.append({"second": second, "ct": players})
    return {
        "round_id": f"m{i // 24}-r{i % 24 + 1}",
        "ct_team": team,
        "winner": winner,
        "complete": True,
        "snapshots": snaps,
        "context": {
            "ct_econ": "long_gun" if i % 5 else "eco",
            "ct_score_before": i % 3,
            "t_score_before": 1,
            "prev_winner_side": "CT" if i % 2 else "T",
            "prev_attack_site": "A" if i % 3 else "B",
        },
    }


def library(n=150, seed=3):
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        team = "Alpha" if i % 2 else "Beta"
        # Alpha mostly plays the 2-1-2 default, Beta mostly stacks A or plays mid.
        setup = rng.choice([0, 0, 0, 1]) if team == "Alpha" else rng.choice([1, 2, 2])
        rows.append(formation(i, team, setup, rng, rng.choice(["CT", "T"])))
    return rows


def test_paper_rules():
    assert macro_area("de_mirage", "Connector") == "Mid"
    assert macro_area("de_mirage", "Connector", {"de_mirage": {"Connector": "A"}}) == "A"
    assert macro_area("de_mirage", None) == "other"
    assert rule_label({"A": 1, "B": 1, "Mid": 2}) == "mid_control"
    assert rule_label({"A": 4, "B": 1}) == "a_heavy"
    assert draft_name({"A": 0.7, "B": 0.1, "Mid": 0.1, "CT": 0.1})[1] == "Aggressive A-Heavy Push"
    assert setup_string({"A": 2, "Mid": 1, "B": 2, "CT": 0, "other": 0}) == "A2 · 中1 · B2"


def test_analyze_map_recovers_setups_and_team_habits():
    result = analyze_map("de_mirage", library(), [])
    assert result["citation"] == CITATION and "10.1109/TG.2026.3745970" in result["citation"]["doi"]
    assert result["rounds"] == 150 and result["k"] >= 3
    top = {p["setups"][0]["setup"] for p in result["patterns"]}
    assert {"A2 · 中1 · B2", "A4 · B1", "中3 · B1 · CT1"} <= top
    assert len({p["name"] for p in result["patterns"]}) == len(result["patterns"])
    assert result["stability_ari"] > 0.9
    assert {t["variable"] for t in result["context_tests"]} >= {"ct_econ", "score_state"}
    habits = {h["team"]: h for h in result["team_habits"]}
    assert set(habits) == {"Alpha", "Beta"}
    assert habits["Alpha"]["differs_from_league"]["p_holm"] < 0.05
    assert habits["Alpha"]["top_setups"][0]["setup"] == "A2 · 中1 · B2"
    roles = {r["player"]: r for r in habits["Alpha"]["roles"]}
    assert roles["Alpha2"]["spots"][0]["spot"].startswith("Connector")
    assert result["spots"] and all("name" in s for s in result["spots"])


def test_small_samples_warn():
    result = analyze_map("de_mirage", library(30), [])
    assert any("论文用了 697 个" in w for w in result["warnings"])
    assert "team_habits" not in result


def test_canonical_teams_and_finalize():
    aliases = canonical_teams(["FLC", "G2.Esports"], "Falcons vs G2 · BLAST")
    assert aliases == {"FLC": "Falcons", "G2.Esports": "G2"}
    assert canonical_teams(["X"], "unknown") == {"X": "X"}
    rounds = [
        {
            "id": f"r{n}",
            "number": n,
            "winner": w,
            "equipment": [{"side": "CT", "team": "FLC"}, {"side": "T", "team": "G2.Esports"}],
        }
        for n, w in ((1, "CT"), (2, "T"), (3, "CT"))
    ]
    forms = {f"r{n}": {"context": {"plant_site": "B" if n == 2 else None}} for n in (1, 2, 3)}
    finalize_formations(forms, rounds, aliases)
    assert forms["r1"]["ct_team"] == "Falcons" and forms["r1"]["context"]["prev_winner_side"] is None
    assert forms["r3"]["context"]["ct_score_before"] == 1 and forms["r3"]["context"]["t_score_before"] == 1
    assert forms["r3"]["context"]["prev_attack_site"] == "B"
    assert forms["r2"]["context"]["prev_attack_site"] == "unknown"


def test_catalog_serves_ct_patterns_and_area_edits_recompute(tmp_path):
    from fastapi.testclient import TestClient

    from openingroutes.api import create_app
    from openingroutes.store import Store
    from tests.test_workflow import auth

    forms = library(60)
    store = Store(tmp_path)
    store.save_match(
        {
            "id": "m1",
            "map": "de_mirage",
            "source": {
                "event": "Synthetic",
                "match": "Alpha vs Beta",
                "date": "2025-01-01",
                "url": "https://example.org/m",
                "verified": True,
                "reviewer": "test",
            },
            "sha256": "c" * 64,
            "rounds": [
                {"id": f["round_id"], "match_id": "m1", "number": i + 1, "is_pistol": False, "complete": True}
                for i, f in enumerate(forms)
            ],
            "throws": [],
            "formations": {f["round_id"]: f for f in forms},
            "formations_version": 1,
            "warnings": [],
        }
    )
    c = TestClient(create_app(tmp_path, testing=True))
    cat = c.get("/api/catalog").json()
    analysis = cat["ct_patterns"]["de_mirage"]
    assert "assignments" not in analysis and analysis["rounds"] == 60
    assert (tmp_path / "cache" / "ct_patterns.json").exists()
    by_id = {r["id"]: r for r in cat["rounds"]}
    assert all("ct_pattern" in by_id[f["round_id"]] for f in forms)
    assert by_id[forms[0]["round_id"]]["formation"]["snapshots"][0]["second"] == 10
    assert cat["place_areas"]["de_mirage"]["Connector"] == "Mid"
    h = auth(c)
    assert c.put("/api/places/de_mirage/Connector", headers=h, json={}).status_code == 422
    assert c.put("/api/places/de_mirage/Connector", headers=h, json={"area": "Z"}).status_code == 422
    saved = c.put("/api/places/de_mirage/Connector", headers=h, json={"label": "连接"})
    assert saved.json()["label"] == "连接"
    saved = c.put("/api/places/de_mirage/Connector", headers=h, json={"area": "A"})
    assert saved.json() == {"map": "de_mirage", "place": "Connector", "label": "连接", "area": "A"}
    cat = c.get("/api/catalog").json()
    assert cat["place_areas"]["de_mirage"]["Connector"] == "A"
    assert cat["places"]["de_mirage"]["Connector"] == "连接"
    setups = {s["setup"] for p in cat["ct_patterns"]["de_mirage"]["patterns"] for s in p["setups"]}
    assert "A3 · B2" in setups and "A2 · 中1 · B2" not in setups
