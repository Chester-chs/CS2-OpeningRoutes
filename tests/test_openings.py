"""Opening defaults: T defaults x CT setups per map era (synthetic data, clearly labelled)."""

from openingroutes import openings

SECONDS = (0, 5, 10, 15, 20, 25, 30)


def t_snapshot(second, places, dead=()):
    return {
        "second": second,
        "t": [
            {"player_id": f"t{i}", "player": f"T{i}", "place": place, "alive": i not in dead}
            for i, place in enumerate(places)
        ],
    }


def ct_places(round_id, plan):
    """Two CT setups, with one player varying by round so the setups are not identical points."""
    stack = ["BombsiteA"] * 3 + ["BombsiteB"] if plan == "a_rush" else ["BombsiteA"] + ["BombsiteB"] * 3
    return stack + [("CTSpawn", "TopofMid", "Apartments")[int(round_id.rsplit("-r", 1)[1]) % 3]]


def formation(round_id, plan, winner="T", *, t_team="Alpha", ct_team="Beta", dead=(), plant="A"):
    """plan: "a_rush" sends all five to A by 15 s; "b_split" puts three in B and two in mid."""
    spawn = ["TSpawn"] * 5
    late = ["BombsiteA"] * 5 if plan == "a_rush" else ["BombsiteB"] * 3 + ["TopofMid"] * 2
    return {
        "round_id": round_id,
        "complete": True,
        "winner": winner,
        "t_team": t_team,
        "ct_team": ct_team,
        "context": {
            "t_econ": "long_gun",
            "ct_econ": "long_gun",
            "t_score_before": 0,
            "ct_score_before": 0,
            "prev_winner_side": None,
            "plant_site": plant,
        },
        "opening_context": {"t_econ": "long_gun"},
        "snapshots": [
            {
                "second": s,
                "ct": [
                    {"player_id": f"c{i}", "player": f"C{i}", "place": place, "alive": True}
                    for i, place in enumerate(ct_places(round_id, plan))
                ],
            }
            for s in (10, 12, 15, 18, 20)
        ],
        "t_snapshots": [t_snapshot(s, spawn if s < 10 else late, dead if s >= 15 else ()) for s in SECONDS],
    }


def test_t_counts_keep_dead_players_and_carry_missing_seconds():
    f = formation("m-r1", "a_rush", dead={0, 1})
    counts = openings.t_counts(f, "de_mirage")
    assert counts[SECONDS.index(15)]["A"] == 5  # the two dead players still count where they fell
    f["t_snapshots"] = [s for s in f["t_snapshots"] if s["second"] != 20]
    assert openings.t_counts(f, "de_mirage")[SECONDS.index(20)] == counts[SECONDS.index(15)]
    f["t_snapshots"][0]["t"] = f["t_snapshots"][0]["t"][:4]
    assert openings.t_counts(f, "de_mirage") is None


def library(matches=4, per_plan=3):
    rounds = []
    for m in range(matches):
        for i in range(per_plan):
            rounds.append(formation(f"m{m}-r{i}", "a_rush", "T" if i else "CT", dead={0} if i == 2 else ()))
            rounds.append(formation(f"m{m}-r{i + 10}", "b_split", "CT", plant="B"))
    return rounds


def test_t_defaults_cluster_with_rule_names_win_rates_and_utility_timing():
    rounds = library()
    throws = [
        {"round_id": "m0-r1", "side": "T", "kind": "smoke", "time": 4.0, "effect_area": "A 区"},
        {"round_id": "m1-r1", "side": "T", "kind": "smoke", "time": 6.0, "effect_area": "A 区"},
        {"round_id": "m1-r1", "side": "T", "kind": "flash", "time": 40.0, "effect_area": "A 区"},
    ]
    result = openings.cluster_t("de_mirage", rounds, throws, min_cluster=3, max_k=2)
    assert result["rounds"] == 24 and result["excluded_rounds"] == 0
    a, b = sorted(result["patterns"], key=lambda p: p["shares"][20]["A"], reverse=True)
    assert a["name"] != b["name"] and "A" in a["name"] and "B" in b["name"]
    assert a["decided"] == 12 and a["t_wins"] == 8 and a["t_win_rate"] == round(8 / 12, 3)
    assert b["t_wins"] == 0
    assert a["utility_timing"] == [{"kind": "smoke", "area": "A 区", "count": 2, "median": 5.0}]
    assert a["representative"] in a["round_ids"]
    assert set(result["assignments"]) == {f["round_id"] for f in rounds}


def test_first_contact_is_the_first_cross_side_damage():
    row = {
        "freeze_end_tick": 1000,
        "learning_events": [
            {
                "kind": "hurt",
                "tick": 1200,
                "attacker_side": "T",
                "victim_side": "T",
                "victim_place": "TSpawn",
            },
            {
                "kind": "hurt",
                "tick": 1640,
                "attacker_side": "CT",
                "victim_side": "T",
                "victim_place": "TopofMid",
            },
            {
                "kind": "death",
                "tick": 1700,
                "attacker_side": "CT",
                "victim_side": "T",
                "victim_place": "TopofMid",
            },
        ],
    }
    assert openings.first_contact(row, 64) == {"second": 10.0, "place": "TopofMid", "by": "CT"}
    assert openings.first_contact({"freeze_end_tick": 0, "learning_events": []}, 64) is None


def matchup_rounds(cells):
    rows = []
    for (t_label, ct_label), (count, matches, t_wins) in cells.items():
        for i in range(count):
            rows.append(
                {
                    "round_id": f"{t_label}-{ct_label}-{i}",
                    "match_id": f"m{i % matches}",
                    "t_label": t_label,
                    "ct_label": ct_label,
                    "winner": "T" if i < t_wins else "CT",
                    "plant": "A" if i % 2 else None,
                    "contact": {"second": 8.0 + i, "place": "TopofMid", "by": "CT"},
                }
            )
    return rows


def test_matchups_hide_rates_below_the_minimum_but_always_count():
    rows = matchup_rounds({(0, 1): (12, 4, 9), (1, 1): (9, 4, 9), (0, None): (3, 2, 1)})
    cells = {(c["t"], c["ct"]): c for c in openings.matchup_table(rows, min_rounds=10, min_matches=3)}
    big, small, unlabelled = cells[(0, 1)], cells[(1, 1)], cells[(0, None)]
    assert big["rounds"] == 12 and big["matches"] == 4 and big["t_win_rate"] == 0.75
    assert big["interval"] is not None and big["interval"][0] <= 0.75 <= big["interval"][1]
    assert big["plants"] == {"A": 6, "none": 6} and big["contact"]["place"] == "TopofMid"
    assert small["rounds"] == 9 and small["t_wins"] == 9 and small["t_win_rate"] is None
    assert small["interval"] is None and small["status"] == "insufficient"
    assert unlabelled["rounds"] == 3


def match(match_id, date, version, rounds, *, verified=True, t_team="Alpha", ct_team="Beta"):
    return {
        "id": match_id,
        "map": "de_mirage",
        "game_version": version,
        "tick_rate": 64,
        "source": {"verified": verified, "date": date, "match": f"{t_team} vs {ct_team}"},
        "rounds": [
            {
                "id": f["round_id"],
                "match_id": match_id,
                "number": int(f["round_id"].rsplit("-r", 1)[1]),
                "complete": True,
                "winner": f["winner"],
                "freeze_end_tick": 0,
                "learning_events": [],
            }
            for f in rounds
        ],
        "formations": {f["round_id"]: {**f, "t_team": t_team, "ct_team": ct_team} for f in rounds},
    }


def era_library():
    rounds = library()
    by_match = {}
    for f in rounds:
        by_match.setdefault(f["round_id"].rsplit("-r", 1)[0], []).append(f)
    versions = ["14180", "14181", "14188", "14190"]
    matches = [
        match(mid, f"2026-10-0{i + 1}", versions[i], fs, t_team="Alpha" if i % 2 else "Gamma")
        for i, (mid, fs) in enumerate(sorted(by_match.items()))
    ]
    outside = match("old", "2026-06-01", "14165", library(1, 3)[:6])
    unverified = match("unverified", "2026-10-09", "14190", library(1, 3)[:6], verified=False)
    ct = {"assignments": {f["round_id"]: 1 for f in rounds}, "patterns": [{"id": 1, "name": "B 区加人"}]}
    return [*matches, outside, unverified], ct


def test_build_pools_the_era_across_patches_and_scouts_each_team():
    matches, ct = era_library()
    built = openings.build("de_mirage", matches, ct, min_cluster=3, max_k=2)
    [era] = [b for b in built["buckets"] if b["era"]]
    assert era["id"] == "de_mirage:2026-09/10" and era["rounds"] == 24
    assert sorted(era["patches"]) == ["14180", "14181", "14188", "14190"]
    assert all(b["id"] != "de_mirage:2026-09/10" for b in built["buckets"] if not b["era"])
    assert "unverified" not in {r.split("-r")[0] for b in built["buckets"] for r in b["t"]["assignments"]}
    assert {c["ct"] for c in era["matchups"]} == {1}
    scout = era["teams"]["Alpha"]
    assert scout["T"]["rounds"] == 12 and scout["T"]["matches"] == 2
    assert sum(d["rounds"] for d in scout["T"]["defaults"]) == 12
    assert all(len(d["examples"]) <= 3 for d in scout["T"]["defaults"])
    assert scout["T"]["opponents"] == {"Beta": 12}


def seed_openings(root):
    from openingroutes.store import Store

    matches, _ = era_library()
    store = Store(root)
    for m in matches:
        store.save_match({**m, "throws": [], "warnings": [], "sha256": m["id"], "learning_version": 1})
    return store


def test_store_caches_openings_until_the_library_changes(tmp_path, monkeypatch):
    store = seed_openings(tmp_path)
    calls = []
    real = openings.build
    monkeypatch.setattr(openings, "build", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = store.openings("de_mirage")
    assert first["map"] == "de_mirage" and first["buckets"]
    assert all("rows" not in b for b in first["buckets"])
    store.openings("de_mirage")
    assert len(calls) == 1
    store.put("round_reviews", "m0-r0", {"resolution": "excluded"})
    store.openings("de_mirage")
    assert len(calls) == 2
    assert store.openings("de_missing") is None


def test_openings_api_serves_one_map_and_validates_the_name(tmp_path):
    from fastapi.testclient import TestClient

    from openingroutes.api import create_app

    seed_openings(tmp_path)
    client = TestClient(create_app(tmp_path, testing=True))
    body = client.get("/api/openings/de_mirage").json()
    assert body["map"] == "de_mirage" and body["buckets"][0]["matchups"]
    assert client.get("/api/openings/de_missing").status_code == 404
    assert client.get("/api/openings/DE%20MIRAGE").status_code == 422


def test_export_writes_verified_openings_without_round_lists(tmp_path):
    import json

    from openingroutes.publish import export_bundle

    store = seed_openings(tmp_path)
    exported = export_bundle(store, tmp_path / "export", include_pistols=True)
    manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
    assert "openings/de_mirage.json" in manifest["files"]
    path = exported / "openings/de_mirage.json"
    assert path.stat().st_size < 2_000_000
    data = json.loads(path.read_text(encoding="utf-8"))
    rounds = {r["id"] for r in json.loads((exported / "catalog.json").read_text(encoding="utf-8"))["rounds"]}
    for bucket in data["buckets"]:
        assert "assignments" not in bucket["t"]
        assert all("round_ids" not in p for p in bucket["t"]["patterns"])
        assert all(p["representative"] in rounds | {""} for p in bucket["t"]["patterns"])
        for scout in bucket["teams"].values():
            assert all(e in rounds for side in scout.values() for d in side["defaults"] for e in d["examples"])
