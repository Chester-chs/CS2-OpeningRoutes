"""Synthetic records test invariants; these are never shipped as professional examples."""
import pytest

from openingroutes.domain import build_rounds, teaching_gaps, safe_url


def test_official_pistols_exclude_warmup_and_overtime():
    freeze = [
        {"tick": 100, "total_rounds_played": 0, "is_warmup_period": True},
        {"tick": 1000, "total_rounds_played": 0, "is_warmup_period": False},
        {"tick": 9000, "total_rounds_played": 12, "is_warmup_period": False},
        {"tick": 19000, "total_rounds_played": 24, "is_warmup_period": False},
    ]
    ends = [{"tick": tick, "total_rounds_played": played, "winner": 2}
            for tick, played in [(2000, 0), (10000, 12), (20000, 24)]]
    rounds = build_rounds("m", freeze, ends, regulation_half=12)
    assert len(rounds) == 3
    assert [r["is_pistol"] for r in rounds] == [True, True, False]
    assert rounds[0]["freeze_end_tick"] == 1000
    assert rounds[1]["number"] == 13


def test_restart_keeps_last_completed_attempt():
    freezes = [{"tick": t, "total_rounds_played": 0, "is_warmup_period": False}
               for t in [100, 1000]]
    rounds = build_rounds("m", freezes, [{"tick": 1500, "total_rounds_played": 0, "winner": 3}])
    assert len(rounds) == 1
    assert rounds[0]["freeze_end_tick"] == 1000
    assert rounds[0]["review_required"] is True


def test_incomplete_round_is_preserved_and_not_official_pistol():
    rounds = build_rounds("m", [{"tick": 100, "total_rounds_played": 0,
                               "is_warmup_period": False}], [])
    assert rounds[0]["complete"] is False
    assert rounds[0]["is_pistol"] is False


def test_complete_tutorial_requires_visuals_video_reproduction_and_source():
    gaps = teaching_gaps({}, source_verified=False)
    assert "source" in gaps
    assert "stance_image" in gaps
    assert "aim_image" in gaps
    assert "reproduction" in gaps
    assert "pro_video" in gaps
    complete = {key: "Confirmed" for key in gaps}
    complete.update(pro_video="https://example.org/v.mp4", stance_image="media/s.png",
                    aim_image="media/a.png", reproduction="verified", verified_by="reviewer",
                    verified_on="2026-10-27", map_version="14074")
    assert teaching_gaps(complete, source_verified=True) == []


@pytest.mark.parametrize("url", ["javascript:alert(1)", "file:///C:/private", "//evil.test/x", "http://evil.test"])
def test_unsafe_links_are_rejected(url):
    assert safe_url(url) is False


def test_https_links_and_owned_media_are_allowed():
    assert safe_url("https://example.org/watch?v=1")
    assert safe_url("media/abc.mp4")
    assert not safe_url("media/../private.mp4")
